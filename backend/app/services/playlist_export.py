"""Cas d'usage « exporter une playlist » vers un service musical (Spotify aujourd'hui).

Réexporter met à jour la même playlist chez le service. Si l'utilisateur l'y a supprimée (pour Spotify :
ne plus la suivre ; elle reste modifiable mais invisible), on en crée une nouvelle.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.adapters.db import Database
from app.adapters.playlist_repository import PlaylistRepository
from app.domain.music_provider import MusicProvider
from app.services.playlist_editor import PlaylistReadOnlyError, owned_playlist


@dataclass(frozen=True, slots=True)
class ExportResult:
    """Bilan d'un export : la playlist chez le service, et combien de morceaux y sont partis."""

    external_playlist_id: str
    url: str
    created: bool  # False : une playlist déjà exportée a été mise à jour
    exported: int
    skipped: int  # morceaux sans identifiant chez ce service
    exported_at: datetime


class PlaylistExporter:
    """Exporte mes playlists vers un service musical."""

    def __init__(self, db: Database, provider: MusicProvider) -> None:
        self._db = db
        self._provider = provider

    async def export(self, owner_id: UUID, playlist_id: UUID, access_token: str) -> ExportResult:
        """Crée la playlist chez le service, ou met à jour celle déjà exportée ; renvoie le bilan."""
        repo = PlaylistRepository(self._db)
        playlist = await owned_playlist(repo, owner_id, playlist_id)
        if playlist.source_provider is not None:
            raise PlaylistReadOnlyError(
                "Playlist importée : elle est déjà sur ce service (exporte plutôt une copie)"
            )

        ids = await repo.external_track_ids(playlist_id, self._provider.name)
        track_ids = [i for i in ids if i is not None]
        previous = await repo.get_export(playlist_id, self._provider.name)

        if previous is not None and await self._still_there(access_token, previous.external_playlist_id):
            external_id = previous.external_playlist_id
            await self._provider.replace_playlist_items(access_token, external_id, track_ids)
            created = False
        else:
            description = f"Exportée depuis DJ Platform le {datetime.now(UTC):%d/%m/%Y}"
            external_id = await self._provider.create_playlist(
                access_token, playlist.name, description, track_ids
            )
            created = True

        saved = await repo.save_export(playlist_id, self._provider.name, external_id)
        return ExportResult(
            external_playlist_id=external_id,
            url=self._provider.playlist_url(external_id),
            created=created,
            exported=len(track_ids),
            skipped=len(ids) - len(track_ids),
            exported_at=saved.last_synced_at,
        )

    async def _still_there(self, access_token: str, external_id: str) -> bool:
        """Indique si la playlist exportée figure encore parmi celles de l'utilisateur chez le service."""
        return any(
            p.external_id == external_id for p in await self._provider.get_user_playlists(access_token)
        )
