"""Routes des morceaux : catalogue, suggestions, demande d'analyse (utilisateurs connectés seulement)."""

from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from app.adapters.db import Database
from app.adapters.playlist_repository import PlaylistRepository
from app.adapters.queue import TaskQueue
from app.adapters.track_repository import CatalogFilters, CatalogSort, TrackRepository
from app.api.deps import (
    get_current_user_id,
    get_db,
    get_playlist_repository,
    get_preview_service,
    get_queue,
    get_track_repository,
)
from app.api.transitions import RatingOut, Transition
from app.domain.camelot import CamelotKey
from app.services.preview import PreviewService
from app.services.set_path import PathFinder
from app.services.track_correction import (
    BPM_MAX,
    BPM_MIN,
    CorrectionChanges,
    NoKeyToFlipError,
    correct,
    flip_mode,
)

router = APIRouter(prefix="/tracks", tags=["tracks"])

Tracks = Annotated[TrackRepository, Depends(get_track_repository)]
CurrentUser = Annotated[UUID, Depends(get_current_user_id)]
AnalysisStatus = Literal["pending", "done", "no_preview", "failed"]
# Écart de BPM accepté par défaut entre deux morceaux (±6 %), comme la fonction SQL suggest_tracks.
DEFAULT_BPM_TOLERANCE = 0.06


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
    favorite: bool
    mine: bool
    rank: int | None = None
    fit_count: int | None = None


class Catalog(BaseModel):
    """Une page du catalogue ; total = nombre de morceaux qui passent les filtres."""

    total: int
    items: list[CatalogTrack]


@router.get("")
async def catalog(
    tracks: Tracks,
    playlists: Annotated[PlaylistRepository, Depends(get_playlist_repository)],
    user_id: CurrentUser,
    scope: Literal["mine", "all", "new"] = "mine",
    q: Annotated[str | None, Query(max_length=100)] = None,
    bpm_min: Annotated[float | None, Query(ge=0, le=300)] = None,
    bpm_max: Annotated[float | None, Query(ge=0, le=300)] = None,
    key: Annotated[str | None, Query(max_length=10, description="Ex. 8A, 11B, Am, F#m")] = None,
    analysis_status: Annotated[AnalysisStatus | None, Query(alias="status")] = None,
    sort: CatalogSort = "title",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    favorites: bool = False,
    source: Annotated[UUID | None, Query(description="Source de l'Explorer")] = None,
    fits: Annotated[UUID | None, Query(description="Ma playlist : liens de chaque morceau avec elle")] = None,
    fits_only: bool = False,
) -> Catalog:
    """Liste les morceaux (les miens, tous, ou les nouveaux pour moi), filtrés et triés, page par page.

    Avec `fits` (une de mes playlists), chaque morceau reçoit `fit_count` : avec combien de ses morceaux il
    s'enchaîne ; `fits_only` ne garde que ceux qui s'enchaînent avec au moins un.
    """
    if fits_only and fits is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "fits_only demande une playlist (fits)")
    if fits is not None and await playlists.get_for_owner(user_id, fits) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Playlist inconnue")
    try:
        camelot = CamelotKey.parse(key) if key else None
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    page = await tracks.catalog(
        user_id,
        CatalogFilters(
            only_mine=scope == "mine",
            only_new=scope == "new",
            source_id=source,
            text=(q or "").strip() or None,
            bpm_min=bpm_min,
            bpm_max=bpm_max,
            key=camelot,
            status=analysis_status,
            sort=sort,
            limit=limit,
            offset=offset,
            favorites_only=favorites,
            fits_playlist=fits,
            fits_only=fits_only,
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
    favorite: bool
    my_rating: RatingOut | None


class Bridge(BaseModel):
    """Un morceau qui fait le pont entre A et B ; score = le plus faible des deux enchaînements."""

    track_id: UUID
    title: str
    artists: list[str]
    bpm: float
    camelot: str
    score: float
    favorite: bool
    mine: bool
    incoming: Transition
    incoming_score: float
    outgoing: Transition
    outgoing_score: float


class SetPathStep(BaseModel):
    """Un enchaînement d'un chemin, et son score."""

    transition: Transition
    score: float


class SetPathOut(BaseModel):
    """Un chemin de A à B : les morceaux entre les deux, chaque enchaînement et le plus faible des scores."""

    tracks: list[CatalogTrack]
    steps: list[SetPathStep]
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
    bpm_tolerance: Annotated[float, Query(gt=0, le=0.2)] = DEFAULT_BPM_TOLERANCE,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    favorites: bool = False,
) -> list[Suggestion]:
    """Liste les morceaux (les miens, ou tous avec scope=all) qui s'enchaînent bien après `track_id`."""
    await _ensure_exists(tracks, track_id)
    # Avec l'utilisateur : ses valeurs rekordbox et ses corrections passent avant Essentia.
    rows = await tracks.suggestions(
        track_id,
        user_id=user_id,
        bpm_tolerance=bpm_tolerance,
        limit=limit,
        only_mine=scope == "mine",
        favorites_only=favorites,
    )
    return [
        Suggestion(
            **{k: v for k, v in asdict(r).items() if k not in ("my_rating", "my_comment")},
            my_rating=RatingOut(rating=r.my_rating, comment=r.my_comment)
            if r.my_rating is not None
            else None,
        )
        for r in rows
    ]


@router.get("/{from_id}/bridges/{to_id}")
async def bridges(
    from_id: UUID,
    to_id: UUID,
    tracks: Tracks,
    user_id: CurrentUser,
    scope: Literal["mine", "all"] = "mine",
    bpm_tolerance: Annotated[float, Query(gt=0, le=0.2)] = DEFAULT_BPM_TOLERANCE,
    limit: Annotated[int, Query(ge=1, le=50)] = 5,
) -> list[Bridge]:
    """Morceaux (les miens, ou tous avec scope=all) qui s'enchaînent après `from_id` et avant `to_id`."""
    await _ensure_exists(tracks, from_id)
    await _ensure_exists(tracks, to_id)
    rows = await tracks.bridges(
        from_id, to_id, user_id=user_id, bpm_tolerance=bpm_tolerance, limit=limit, only_mine=scope == "mine"
    )
    return [Bridge.model_validate(asdict(r)) for r in rows]


@router.get("/{from_id}/paths/{to_id}")
async def paths(
    from_id: UUID,
    to_id: UUID,
    tracks: Tracks,
    user_id: CurrentUser,
    scope: Literal["mine", "all"] = "mine",
    bpm_tolerance: Annotated[float, Query(gt=0, le=0.2)] = DEFAULT_BPM_TOLERANCE,
) -> list[SetPathOut]:
    """Jusqu'à 3 chemins de 1 à 4 morceaux (les miens, ou tous avec scope=all) pour aller de A à B."""
    await _ensure_exists(tracks, from_id)
    await _ensure_exists(tracks, to_id)
    found = await PathFinder(tracks).paths(user_id, from_id, to_id, bpm_tolerance, only_mine=scope == "mine")
    return [
        SetPathOut(
            tracks=[CatalogTrack(**asdict(t)) for t in p.tracks],
            steps=[
                SetPathStep(transition=Transition(**asdict(s.transition)), score=s.score)
                for s in p.transitions
            ],
            score=p.score,
        )
        for p in found
    ]


@router.get("/{track_id}")
async def get_track(track_id: UUID, tracks: Tracks, user_id: CurrentUser) -> CatalogTrack:
    """Un morceau et ses valeurs affichées, même hors de mes playlists ; 404 s'il n'existe pas."""
    return await _track_view(tracks, user_id, track_id)


async def _track_view(tracks: TrackRepository, user_id: UUID, track_id: UUID) -> CatalogTrack:
    """Le morceau tel que le voit l'utilisateur (ses corrections comprises) ; 404 s'il n'existe pas."""
    page = await tracks.catalog(user_id, CatalogFilters(only_mine=False, track_id=track_id, limit=1))
    if not page.items:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Morceau inconnu")
    return CatalogTrack(**asdict(page.items[0]))


class CorrectionIn(BaseModel):
    """Champs à corriger : un champ absent reste tel quel ; à null, ma correction de ce champ est annulée."""

    bpm: Annotated[float, Field(ge=BPM_MIN, le=BPM_MAX)] | None = None
    key: Annotated[str, Field(min_length=1, max_length=10, description="Ex. 8A, Am, F#m")] | None = None


@router.patch("/{track_id}/correction")
async def correct_track(
    track_id: UUID,
    body: CorrectionIn,
    tracks: Tracks,
    user_id: CurrentUser,
    db: Annotated[Database, Depends(get_db)],
) -> CatalogTrack:
    """Corrige le BPM et/ou la tonalité (pour moi seulement) ; renvoie le morceau mis à jour."""
    await _ensure_exists(tracks, track_id)
    try:
        key = CamelotKey.parse(body.key) if body.key is not None else None
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    changes = CorrectionChanges(
        fields=frozenset(body.model_fields_set),
        bpm=round(body.bpm, 1) if body.bpm is not None else None,
        key=key,
    )
    await correct(db, user_id, track_id, changes)
    return await _track_view(tracks, user_id, track_id)


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


@router.put("/{track_id}/favorite", status_code=status.HTTP_204_NO_CONTENT)
async def add_favorite(track_id: UUID, tracks: Tracks, user_id: CurrentUser) -> Response:
    """Met le morceau dans mes favoris (sans effet s'il y est déjà) ; 404 s'il n'existe pas."""
    await _ensure_exists(tracks, track_id)
    await tracks.set_favorite(user_id, track_id, favorite=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{track_id}/favorite", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favorite(track_id: UUID, tracks: Tracks, user_id: CurrentUser) -> Response:
    """Retire le morceau de mes favoris (sans effet s'il n'y est pas)."""
    await tracks.set_favorite(user_id, track_id, favorite=False)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class PreviewOut(BaseModel):
    """URL de l'extrait Deezer, à lire tout de suite par le navigateur ; expires_at null = inconnue."""

    url: str
    expires_at: datetime | None


@router.get("/{track_id}/preview")
async def track_preview(
    track_id: UUID,
    tracks: Tracks,
    _user_id: CurrentUser,
    previews: Annotated[PreviewService, Depends(get_preview_service)],
    response: Response,
) -> PreviewOut:
    """URL neuve de l'extrait (~15 min) ; 404 avec la raison s'il n'y en a pas ; 503 si Deezer flanche."""
    await _ensure_exists(tracks, track_id)
    preview = await previews.preview(track_id)
    # L'URL va expirer : le navigateur ne doit pas garder cette réponse.
    response.headers["Cache-Control"] = "no-store"
    return PreviewOut(url=preview.url, expires_at=preview.expires_at)
