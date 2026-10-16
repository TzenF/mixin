"""Routes des morceaux : catalogue, suggestions, demande d'analyse (utilisateurs connectés seulement)."""

from dataclasses import asdict
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.adapters.db import Database
from app.adapters.queue import TaskQueue
from app.adapters.track_repository import CatalogFilters, CatalogSort, TrackRepository
from app.api.deps import get_current_user_id, get_db, get_queue, get_track_repository
from app.domain.camelot import CamelotKey
from app.services.key_correction import NoKeyToFlipError, flip_mode

router = APIRouter(prefix="/tracks", tags=["tracks"])

Tracks = Annotated[TrackRepository, Depends(get_track_repository)]
CurrentUser = Annotated[UUID, Depends(get_current_user_id)]
AnalysisStatus = Literal["pending", "done", "no_preview", "failed"]


class CatalogTrack(BaseModel):
    """Un morceau du catalogue ; bpm et camelot sont None tant qu'aucune source n'en donne."""

    id: UUID
    title: str
    artists: list[str]
    bpm: float | None
    camelot: str | None
    bpm_source: str | None
    key_source: str | None
    key_confidence: float | None
    analysis_status: AnalysisStatus


class Catalog(BaseModel):
    """Une page du catalogue ; total = nombre de morceaux qui passent les filtres."""

    total: int
    items: list[CatalogTrack]


@router.get("")
async def catalog(
    tracks: Tracks,
    user_id: CurrentUser,
    scope: Literal["mine", "all"] = "mine",
    q: Annotated[str | None, Query(max_length=100)] = None,
    bpm_min: Annotated[float | None, Query(ge=0, le=300)] = None,
    bpm_max: Annotated[float | None, Query(ge=0, le=300)] = None,
    key: Annotated[str | None, Query(max_length=10, description="Ex. 8A, 11B, Am, F#m")] = None,
    analysis_status: Annotated[AnalysisStatus | None, Query(alias="status")] = None,
    sort: CatalogSort = "title",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Catalog:
    """Liste les morceaux (les miens, ou tous avec scope=all), filtrés et triés, page par page."""
    try:
        camelot = CamelotKey.parse(key) if key else None
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    page = await tracks.catalog(
        user_id,
        CatalogFilters(
            only_mine=scope == "mine",
            text=(q or "").strip() or None,
            bpm_min=bpm_min,
            bpm_max=bpm_max,
            key=camelot,
            status=analysis_status,
            sort=sort,
            limit=limit,
            offset=offset,
        ),
    )
    return Catalog(total=page.total, items=[CatalogTrack(**asdict(r)) for r in page.items])


class Suggestion(BaseModel):
    """Un morceau compatible avec le morceau de départ, et pourquoi."""

    track_id: UUID
    title: str
    artists: list[str]
    bpm: float
    camelot: str
    key_move: str
    half_double: bool
    bpm_diff_pct: float
    score: float


async def _ensure_exists(tracks: TrackRepository, track_id: UUID) -> None:
    """Lève une erreur 404 si le morceau n'existe pas."""
    if not await tracks.exists(track_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Morceau inconnu")


@router.get("/{track_id}/suggestions")
async def suggestions(
    track_id: UUID,
    tracks: Tracks,
    user_id: CurrentUser,
    scope: Literal["mine", "all"] = "mine",
    bpm_tolerance: Annotated[float, Query(gt=0, le=0.2)] = 0.06,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[Suggestion]:
    """Liste les morceaux (les miens, ou tous avec scope=all) qui s'enchaînent bien après `track_id`."""
    await _ensure_exists(tracks, track_id)
    # Avec l'utilisateur : ses valeurs rekordbox et ses corrections passent avant Essentia.
    rows = await tracks.suggestions(
        track_id, user_id=user_id, bpm_tolerance=bpm_tolerance, limit=limit, only_mine=scope == "mine"
    )
    return [Suggestion(**asdict(r)) for r in rows]


@router.get("/{track_id}")
async def get_track(track_id: UUID, tracks: Tracks, user_id: CurrentUser) -> CatalogTrack:
    """Un morceau et ses valeurs affichées, même hors de mes playlists ; 404 s'il n'existe pas."""
    page = await tracks.catalog(user_id, CatalogFilters(only_mine=False, track_id=track_id, limit=1))
    if not page.items:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Morceau inconnu")
    return CatalogTrack(**asdict(page.items[0]))


class AnalysisRequested(BaseModel):
    """Identifiant de la tâche créée, ou None si une analyse était déjà en file."""

    job_id: str | None


@router.post("/{track_id}/analysis", status_code=status.HTTP_202_ACCEPTED)
async def request_analysis(
    track_id: UUID,
    tracks: Tracks,
    queue: Annotated[TaskQueue, Depends(get_queue)],
    _user_id: CurrentUser,
) -> AnalysisRequested:
    """Demande l'analyse audio d'un morceau ; elle sera faite par le worker."""
    await _ensure_exists(tracks, track_id)
    return AnalysisRequested(job_id=await queue.enqueue_analysis(str(track_id)))


class KeyCorrected(BaseModel):
    """Tonalité affichée après correction ; elle vient désormais de la correction perso."""

    camelot: str
    key_source: Literal["manual"] = "manual"


@router.post("/{track_id}/key/flip-mode")
async def flip_key_mode(
    track_id: UUID,
    tracks: Tracks,
    user_id: CurrentUser,
    db: Annotated[Database, Depends(get_db)],
) -> KeyCorrected:
    """Inverse majeur/mineur de la tonalité affichée (8A -> 11B), pour moi seulement ; 409 sans tonalité."""
    await _ensure_exists(tracks, track_id)
    try:
        key = await flip_mode(db, user_id, track_id)
    except NoKeyToFlipError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    return KeyCorrected(camelot=str(key))
