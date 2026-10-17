"""Cas d'usage « Explorer » : copier les tops et playlists éditoriales Deezer dans le catalogue.

Chaque synchronisation enregistre les morceaux (dédoublonnés par ISRC), remplace le classement de la source et
met les nouveaux morceaux en file d'analyse. Un morceau sorti d'un top reste dans le catalogue.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.adapters.db import Database
from app.adapters.deezer_client import DeezerUnavailableError
from app.adapters.explore_repository import ExploreRepository
from app.adapters.track_repository import TrackRepository
from app.domain.music_provider import ProviderTrack
from app.services.playlist_import import AnalysisQueue
from app.services.track_import import save_provider_tracks

log = logging.getLogger(__name__)


class ExploreSourceMissingError(Exception):
    """La source de l'Explorer n'existe pas."""


class PlaylistSource(Protocol):
    """Ce dont la synchronisation a besoin de Deezer."""

    async def playlist_tracks(self, playlist_id: str) -> list[ProviderTrack] | None:
        """Morceaux d'une playlist publique, dans l'ordre ; None si elle n'existe pas."""
        ...


@dataclass(frozen=True, slots=True)
class SyncResult:
    """Bilan d'une synchronisation : morceaux dans la source, dont nouveaux dans le catalogue."""

    total: int
    new: int


class ExploreSync:
    """Synchronise les sources de l'Explorer avec Deezer."""

    def __init__(self, db: Database, deezer: PlaylistSource, queue: AnalysisQueue) -> None:
        self._db = db
        self._deezer = deezer
        self._queue = queue

    async def sync(self, source_id: UUID) -> SyncResult:
        """Recopie la source ; en cas d'échec, l'erreur est notée et l'ancien classement reste en place."""
        repo = ExploreRepository(self._db)
        source = await repo.get(source_id)
        if source is None:
            raise ExploreSourceMissingError("Source inconnue")
        try:
            tracks = await self._deezer.playlist_tracks(source.external_id)
        except DeezerUnavailableError as e:
            await repo.mark_failed(source_id, f"Deezer indisponible : {e}")
            raise
        if tracks is None:
            await repo.mark_failed(source_id, "Playlist introuvable chez Deezer")
            return SyncResult(total=0, new=0)

        try:
            async with self._db.transaction() as tx:
                explore = ExploreRepository(tx)
                await explore.lock_sync()
                ordered, new = await save_provider_tracks(TrackRepository(tx), source.provider, tracks)
                unique = list(dict.fromkeys(ordered))  # un morceau présent deux fois garde sa première place
                await explore.replace_items(source_id, unique)
                await explore.mark_synced(source_id)
        except Exception as e:
            await repo.mark_failed(source_id, f"Enregistrement impossible : {e.__class__.__name__}")
            raise

        # Après la validation : sinon le worker pourrait chercher un morceau pas encore visible.
        for track_id in new:
            try:
                await self._queue.enqueue_analysis(str(track_id))
            except Exception:
                log.exception("Mise en file impossible pour %s", track_id)
        return SyncResult(total=len(unique), new=len(new))
