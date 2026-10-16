"""Routes des playlists de l'utilisateur connecté : liste et détail avec la qualité des enchaînements."""

from dataclasses import asdict
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.adapters.playlist_repository import PlaylistRepository
from app.api.deps import get_current_user_id, get_playlist_repository
from app.api.tracks import DEFAULT_BPM_TOLERANCE, CatalogTrack

router = APIRouter(prefix="/playlists", tags=["playlists"])

CurrentUser = Annotated[UUID, Depends(get_current_user_id)]


Playlists = Annotated[PlaylistRepository, Depends(get_playlist_repository)]


class PlaylistSummary(BaseModel):
    """Une playlist ; source_provider null = créée ici, sinon importée (lecture seule)."""

    id: UUID
    name: str
    source_provider: str | None
    track_count: int
    updated_at: datetime


class Transition(BaseModel):
    """Enchaînement vers le morceau suivant ; key_move null = tonalité incompatible (voir key_distance)."""

    key_move: str | None
    key_distance: int
    half_double: bool
    bpm_diff: float
    bpm_change: float
    tempo_ok: bool
    same_mode: bool
    compatible: bool


class PlaylistItem(BaseModel):
    """Un morceau de la playlist ; transition_to_next null = dernier morceau, ou l'un des deux non analysé."""

    item_id: int
    position: int
    track: CatalogTrack
    transition_to_next: Transition | None


class PlaylistDetail(PlaylistSummary):
    """Une playlist avec ses morceaux dans l'ordre."""

    items: list[PlaylistItem]


@router.get("")
async def list_playlists(playlists: Playlists, user_id: CurrentUser) -> list[PlaylistSummary]:
    """Mes playlists (créées ici ou importées), les plus récemment modifiées d'abord."""
    return [PlaylistSummary(**asdict(p)) for p in await playlists.list_for_owner(user_id)]


@router.get("/{playlist_id}")
async def get_playlist(playlist_id: UUID, playlists: Playlists, user_id: CurrentUser) -> PlaylistDetail:
    """Une de mes playlists, avec l'enchaînement entre chaque morceau ; 404 si elle n'est pas à moi."""
    playlist = await playlists.get_for_owner(user_id, playlist_id)
    if playlist is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Playlist inconnue")
    items = await playlists.items_with_transitions(user_id, playlist_id, DEFAULT_BPM_TOLERANCE)
    return PlaylistDetail(**asdict(playlist), items=[PlaylistItem(**asdict(i)) for i in items])
