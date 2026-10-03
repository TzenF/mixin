"""Playlists Spotify de l'utilisateur connecté : liste et import dans notre base."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.adapters.db import Database
from app.adapters.playlist_repository import PlaylistRepository
from app.adapters.spotify_provider import SpotifyProvider
from app.api.deps import (
    get_current_user_id,
    get_db,
    get_playlist_importer,
    get_spotify_connection,
    get_spotify_provider,
)
from app.services.playlist_import import PlaylistImporter
from app.services.spotify_connection import SpotifyConnection

router = APIRouter(prefix="/spotify", tags=["spotify"])

CurrentUser = Annotated[UUID, Depends(get_current_user_id)]
Connection = Annotated[SpotifyConnection, Depends(get_spotify_connection)]


class SpotifyPlaylist(BaseModel):
    """Une playlist Spotify de l'utilisateur, et si elle a déjà été importée."""

    id: str
    name: str
    track_count: int
    imported: bool


@router.get("/playlists")
async def list_playlists(
    user_id: CurrentUser,
    connection: Connection,
    provider: Annotated[SpotifyProvider, Depends(get_spotify_provider)],
    db: Annotated[Database, Depends(get_db)],
) -> list[SpotifyPlaylist]:
    """Liste les playlists Spotify dont l'utilisateur est propriétaire."""
    playlists = await provider.get_user_playlists(await connection.access_token(user_id))
    imported = await PlaylistRepository(db).imported_sources(user_id, provider.name)
    return [
        SpotifyPlaylist(
            id=p.external_id, name=p.name, track_count=p.track_count, imported=p.external_id in imported
        )
        for p in playlists
    ]


class ImportOutcome(BaseModel):
    """Bilan d'un import : total = nouveaux + déjà connus + ignorés."""

    import_job_id: UUID
    playlist_id: UUID
    name: str
    created: bool
    total: int
    new: int
    known: int
    skipped: int
    queued: int


@router.post("/playlists/{playlist_id}/import")
async def import_playlist(
    playlist_id: str,
    user_id: CurrentUser,
    connection: Connection,
    importer: Annotated[PlaylistImporter, Depends(get_playlist_importer)],
) -> ImportOutcome:
    """Importe (ou réimporte) une playlist Spotify dans notre base."""
    result = await importer.import_playlist(user_id, await connection.access_token(user_id), playlist_id)
    s = result.stats
    return ImportOutcome(
        import_job_id=result.import_job_id,
        playlist_id=result.playlist_id,
        name=result.name,
        created=result.created,
        total=s.total,
        new=s.new,
        known=s.known,
        skipped=s.skipped,
        queued=s.queued,
    )
