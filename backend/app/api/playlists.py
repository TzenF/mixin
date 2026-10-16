"""Routes des playlists de l'utilisateur connecté : lecture (avec les enchaînements) et modification."""

from dataclasses import asdict
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, StringConstraints

from app.adapters.playlist_repository import PlaylistRepository
from app.adapters.spotify_provider import SpotifyProvider
from app.api.deps import (
    get_current_user_id,
    get_playlist_editor,
    get_playlist_exporter,
    get_playlist_repository,
    get_spotify_connection,
    get_spotify_provider,
)
from app.api.tracks import DEFAULT_BPM_TOLERANCE, CatalogTrack
from app.services.playlist_editor import PlaylistEditor
from app.services.playlist_export import PlaylistExporter
from app.services.spotify_connection import SpotifyConnection

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


class SpotifyExport(BaseModel):
    """Dernier export de la playlist vers Spotify."""

    url: str
    exported_at: datetime


class PlaylistDetail(PlaylistSummary):
    """Une playlist avec ses morceaux dans l'ordre ; spotify_export null = jamais exportée."""

    items: list[PlaylistItem]
    spotify_export: SpotifyExport | None


@router.get("")
async def list_playlists(playlists: Playlists, user_id: CurrentUser) -> list[PlaylistSummary]:
    """Mes playlists (créées ici ou importées), les plus récemment modifiées d'abord."""
    return [PlaylistSummary(**asdict(p)) for p in await playlists.list_for_owner(user_id)]


@router.get("/{playlist_id}")
async def get_playlist(
    playlist_id: UUID,
    playlists: Playlists,
    user_id: CurrentUser,
    spotify: Annotated[SpotifyProvider, Depends(get_spotify_provider)],
) -> PlaylistDetail:
    """Une de mes playlists, avec l'enchaînement entre chaque morceau ; 404 si elle n'est pas à moi."""
    playlist = await playlists.get_for_owner(user_id, playlist_id)
    if playlist is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Playlist inconnue")
    items = await playlists.items_with_transitions(user_id, playlist_id, DEFAULT_BPM_TOLERANCE)
    export = await playlists.get_export(playlist_id, spotify.name)
    return PlaylistDetail(
        **asdict(playlist),
        items=[PlaylistItem(**asdict(i)) for i in items],
        spotify_export=(
            SpotifyExport(
                url=spotify.playlist_url(export.external_playlist_id), exported_at=export.last_synced_at
            )
            if export
            else None
        ),
    )


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


class NewOrder(BaseModel):
    """Tous les éléments de la playlist (item_id), dans le nouvel ordre."""

    item_ids: list[int]


@router.put("/{playlist_id}/order", status_code=status.HTTP_204_NO_CONTENT)
async def reorder_playlist(
    playlist_id: UUID, body: NewOrder, editor: Editor, user_id: CurrentUser
) -> Response:
    """Change l'ordre des morceaux ; 422 si la liste ne correspond plus au contenu (page à recharger)."""
    await editor.reorder(user_id, playlist_id, body.item_ids)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{playlist_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_item(playlist_id: UUID, item_id: int, editor: Editor, user_id: CurrentUser) -> Response:
    """Retire un morceau de la playlist ; 404 s'il n'y est pas."""
    await editor.remove_item(user_id, playlist_id, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class ExportOutcome(BaseModel):
    """Bilan d'un export : created = nouvelle playlist chez Spotify (sinon : mise à jour de la précédente)."""

    url: str
    created: bool
    exported: int
    skipped: int
    exported_at: datetime


@router.post("/{playlist_id}/export/spotify")
async def export_to_spotify(
    playlist_id: UUID,
    user_id: CurrentUser,
    connection: Annotated[SpotifyConnection, Depends(get_spotify_connection)],
    exporter: Annotated[PlaylistExporter, Depends(get_playlist_exporter)],
) -> ExportOutcome:
    """Exporte la playlist vers Spotify (privée) ou met à jour l'export précédent ; 409 si importée."""
    result = await exporter.export(user_id, playlist_id, await connection.access_token(user_id))
    return ExportOutcome(
        url=result.url,
        created=result.created,
        exported=result.exported,
        skipped=result.skipped,
        exported_at=result.exported_at,
    )
