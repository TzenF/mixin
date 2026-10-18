"""Routes de l'Explorer : sources de découverte (tops et playlists éditoriales Deezer), partagées par tous.

Les morceaux d'une source passent par le catalogue : `GET /tracks?source={id}&scope=all&sort=rank`.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.adapters.explore_repository import ExploreRepository, ExploreSourceRow
from app.adapters.queue import TaskQueue
from app.api.deps import get_current_user_id, get_explore_repository, get_explore_sync, get_queue
from app.services.explore import ExploreSync

router = APIRouter(prefix="/explore", tags=["explore"])

CurrentUser = Annotated[UUID, Depends(get_current_user_id)]
Sources = Annotated[ExploreRepository, Depends(get_explore_repository)]
Queue = Annotated[TaskQueue, Depends(get_queue)]


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


class NewSource(BaseModel):
    """Lien d'une playlist Deezer : site, lien court de l'app (link.deezer.com) ou identifiant seul."""

    link: str = Field(min_length=1, max_length=500)


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


@router.post("/sources")
async def add_source(
    body: NewSource,
    explore: Annotated[ExploreSync, Depends(get_explore_sync)],
    sources: Sources,
    queue: Queue,
    user_id: CurrentUser,
) -> ExploreSource:
    """Ajoute une playlist Deezer à l'Explorer de tous (ou renvoie la source si elle y est déjà)."""
    source_id = await explore.add_source(user_id, body.link)
    source = await sources.get(source_id)
    assert source is not None
    if source.last_synced_at is None:
        await queue.enqueue_explore_sync(str(source_id))
    return _out(source, user_id)


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_source(source_id: UUID, sources: Sources, user_id: CurrentUser) -> Response:
    """Retire une source que j'ai ajoutée ; 404 si c'est une source par défaut ou celle d'un autre."""
    if not await sources.remove(source_id, user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source inconnue")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sources/{source_id}/refresh", status_code=status.HTTP_202_ACCEPTED)
async def refresh_source(
    source_id: UUID,
    sources: Sources,
    queue: Queue,
    _user_id: CurrentUser,
) -> RefreshQueued:
    """Met à jour la source depuis Deezer (par le worker, en priorité sur les analyses)."""
    if await sources.get(source_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source inconnue")
    return RefreshQueued(queued=await queue.enqueue_explore_sync(str(source_id)) is not None)
