"""Routes de l'Explorer : sources de découverte (tops et playlists éditoriales Deezer), partagées par tous.

Les morceaux d'une source passent par le catalogue : `GET /tracks?source={id}&scope=all&sort=rank`.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.adapters.explore_repository import ExploreRepository, ExploreSourceRow
from app.adapters.queue import TaskQueue
from app.api.deps import get_current_user_id, get_explore_repository, get_queue

router = APIRouter(prefix="/explore", tags=["explore"])

CurrentUser = Annotated[UUID, Depends(get_current_user_id)]
Sources = Annotated[ExploreRepository, Depends(get_explore_repository)]


class ExploreSource(BaseModel):
    """Une source de l'Explorer ; removable : je l'ai ajoutée (les sources par défaut ne se retirent pas)."""

    id: UUID
    title: str
    curator: str | None
    track_count: int
    analysed_count: int
    pending_count: int
    last_synced_at: datetime | None
    last_error: str | None
    removable: bool


class RefreshQueued(BaseModel):
    """La synchronisation est en file ; queued faux : elle l'était déjà."""

    queued: bool


def _out(source: ExploreSourceRow, user_id: UUID) -> ExploreSource:
    """Source telle que la voit cet utilisateur."""
    return ExploreSource(
        id=source.id,
        title=source.title,
        curator=source.curator,
        track_count=source.track_count,
        analysed_count=source.analysed_count,
        pending_count=source.pending_count,
        last_synced_at=source.last_synced_at,
        last_error=source.last_error,
        removable=source.added_by == user_id,
    )


@router.get("/sources")
async def list_sources(sources: Sources, user_id: CurrentUser) -> list[ExploreSource]:
    """Les sources de l'Explorer, avec l'avancement de leur synchronisation et de l'analyse."""
    return [_out(s, user_id) for s in await sources.list()]


@router.post("/sources/{source_id}/refresh", status_code=status.HTTP_202_ACCEPTED)
async def refresh_source(
    source_id: UUID,
    sources: Sources,
    queue: Annotated[TaskQueue, Depends(get_queue)],
    _user_id: CurrentUser,
) -> RefreshQueued:
    """Met à jour la source depuis Deezer (par le worker, en priorité sur les analyses)."""
    if await sources.get(source_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source inconnue")
    return RefreshQueued(queued=await queue.enqueue_explore_sync(str(source_id)) is not None)
