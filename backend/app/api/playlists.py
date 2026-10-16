"""Routes des playlists de l'utilisateur connecté : lecture (avec les enchaînements) et modification."""

from dataclasses import asdict
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, StringConstraints

from app.adapters.playlist_repository import PlaylistRepository
from app.api.deps import get_current_user_id, get_playlist_editor, get_playlist_repository
from app.api.tracks import DEFAULT_BPM_TOLERANCE, CatalogTrack
from app.services.playlist_editor import PlaylistEditor

router = APIRouter(prefix="/playlists", tags=["playlists"])

CurrentUser = Annotated[UUID, Depends(get_current_user_id)]


Playlists = Annotated[PlaylistRepository, Depends(get_playlist_repository)]
Editor = Annotated[PlaylistEditor, Depends(get_playlist_editor)]
PlaylistName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


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


class PlaylistNameIn(BaseModel):
    """Nom d'une playlist (espaces de début et de fin retirés, 1 à 100 caractères)."""

    name: PlaylistName


class TrackToAdd(BaseModel):
    """Morceau à ajouter en fin de playlist."""

    track_id: UUID


class AddedItem(BaseModel):
    """Élément ajouté : son identifiant et sa position dans la playlist."""

    item_id: int
    position: int


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_playlist(body: PlaylistNameIn, editor: Editor, user_id: CurrentUser) -> PlaylistSummary:
    """Crée une playlist vide."""
    return PlaylistSummary(**asdict(await editor.create(user_id, body.name)))


@router.patch("/{playlist_id}")
async def rename_playlist(
    playlist_id: UUID, body: PlaylistNameIn, editor: Editor, user_id: CurrentUser
) -> PlaylistSummary:
    """Renomme une de mes playlists ; 409 si elle est importée."""
    return PlaylistSummary(**asdict(await editor.rename(user_id, playlist_id, body.name)))


@router.delete("/{playlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_playlist(playlist_id: UUID, editor: Editor, user_id: CurrentUser) -> Response:
    """Supprime une de mes playlists (les morceaux restent dans le catalogue)."""
    await editor.delete(user_id, playlist_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{playlist_id}/items", status_code=status.HTTP_201_CREATED)
async def add_track(playlist_id: UUID, body: TrackToAdd, editor: Editor, user_id: CurrentUser) -> AddedItem:
    """Ajoute un morceau en fin de playlist ; 409 si elle est importée, 404 si le morceau n'existe pas."""
    item_id, position = await editor.add_track(user_id, playlist_id, body.track_id)
    return AddedItem(item_id=item_id, position=position)


@router.post("/{playlist_id}/copy", status_code=status.HTTP_201_CREATED)
async def copy_playlist(playlist_id: UUID, editor: Editor, user_id: CurrentUser) -> PlaylistSummary:
    """Duplique une de mes playlists (même importée) en une playlist modifiable « X (copie) »."""
    return PlaylistSummary(**asdict(await editor.copy(user_id, playlist_id)))
