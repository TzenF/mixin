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
from app.adapters.deezer_client import MAX_PLAYLIST_TRACKS, DeezerPlaylist, DeezerUnavailableError
from app.adapters.explore_repository import ExploreRepository
from app.adapters.track_repository import TrackRepository
from app.domain.deezer_link import is_short_link, playlist_id_from_link
from app.domain.music_provider import ProviderTrack
from app.services.playlist_import import AnalysisQueue
from app.services.track_import import save_provider_tracks

log = logging.getLogger(__name__)


class ExploreSourceMissingError(Exception):
    """La source de l'Explorer n'existe pas (chez nous ou chez Deezer)."""


class InvalidSourceError(Exception):
    """Le lien collé ne peut pas devenir une source : pas une playlist Deezer, privée, ou trop grande."""


class PlaylistSource(Protocol):
    """Ce dont l'Explorer a besoin de Deezer."""

    async def playlist(self, playlist_id: str) -> DeezerPlaylist | None:
        """Titre, créateur et taille d'une playlist publique ; None si elle n'existe pas."""
        ...

    async def playlist_tracks(self, playlist_id: str) -> list[ProviderTrack] | None:
        """Morceaux d'une playlist publique, dans l'ordre ; None si elle n'existe pas."""
        ...

    async def resolve_short_link(self, url: str) -> str | None:
        """URL vers laquelle mène un lien court de l'app ; None s'il ne mène nulle part."""
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

    async def add_source(self, user_id: UUID, link: str) -> UUID:
        """Ajoute la playlist Deezer du lien aux sources (ou retrouve l'existante) ; renvoie son identifiant.

        La synchronisation n'est pas lancée ici : le worker s'en charge (`TaskQueue.enqueue_explore_sync`).
        """
        url = await self._deezer.resolve_short_link(link.strip()) if is_short_link(link) else link
        playlist_id = playlist_id_from_link(url) if url else None
        if playlist_id is None:
            raise InvalidSourceError("Ce n'est pas un lien de playlist Deezer (ou le lien a expiré)")
        playlist = await self._deezer.playlist(playlist_id)
        if playlist is None:
            raise ExploreSourceMissingError("Playlist introuvable chez Deezer")
        if not playlist.public:
            raise InvalidSourceError("Cette playlist est privée : rends-la publique dans Deezer")
        # Au-delà, playlist_tracks couperait la playlist sans prévenir.
        if playlist.track_count > MAX_PLAYLIST_TRACKS:
            raise InvalidSourceError(f"Playlist trop grande : {MAX_PLAYLIST_TRACKS} titres maximum")
        return await ExploreRepository(self._db).add(
            "deezer", playlist.deezer_id, playlist.title or "Playlist Deezer", playlist.curator, user_id
        )

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
