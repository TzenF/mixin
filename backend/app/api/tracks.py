"""Premières routes métier : suggestions et demande d'analyse.

Sert d'exemple de bout en bout (route -> dépôt -> fonction SQL) pour le reste du V1.
"""

from dataclasses import asdict
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.adapters.queue import TaskQueue
from app.adapters.track_repository import TrackRepository
from app.api.deps import get_queue, get_track_repository

router = APIRouter(prefix="/tracks", tags=["tracks"])

Tracks = Annotated[TrackRepository, Depends(get_track_repository)]


class Suggestion(BaseModel):
    """Un morceau compatible avec le morceau de départ, et pourquoi."""

    track_id: UUID
    title: str
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
    bpm_tolerance: Annotated[float, Query(gt=0, le=0.2)] = 0.06,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[Suggestion]:
    """Liste les morceaux qui s'enchaînent bien après `track_id`, du meilleur au moins bon."""
    await _ensure_exists(tracks, track_id)
    # TODO(auth) : passer l'utilisateur connecté pour appliquer ses corrections personnelles
    rows = await tracks.suggestions(track_id, user_id=None, bpm_tolerance=bpm_tolerance, limit=limit)
    return [Suggestion(**asdict(r)) for r in rows]


class AnalysisRequested(BaseModel):
    """Identifiant de la tâche créée, ou None si une analyse était déjà en file."""

    job_id: str | None


@router.post("/{track_id}/analysis", status_code=status.HTTP_202_ACCEPTED)
async def request_analysis(
    track_id: UUID,
    tracks: Tracks,
    queue: Annotated[TaskQueue, Depends(get_queue)],
) -> AnalysisRequested:
    """Demande l'analyse audio d'un morceau ; elle sera faite par le worker."""
    await _ensure_exists(tracks, track_id)
    return AnalysisRequested(job_id=await queue.enqueue_analysis(str(track_id)))
