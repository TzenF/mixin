"""Cas d'usage « importer une playlist » : copie une playlist d'un service musical dans notre base.

Les morceaux sont dédoublonnés par ISRC puis par identifiant externe ; seuls les nouveaux sont mis en file
d'analyse. Réimporter la même playlist met à jour la playlist déjà importée, sans dupliquer de morceau.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Protocol
from uuid import UUID

from app.adapters.db import Database, Queryable
from app.adapters.import_job_repository import ImportJobRepository
from app.adapters.playlist_repository import PlaylistRepository
from app.adapters.track_repository import TrackRepository
from app.domain.music_provider import MusicProvider, ProviderTrack

log = logging.getLogger(__name__)


class AnalysisQueue(Protocol):
    """Ce dont l'import a besoin de la file de tâches."""

    async def enqueue_analysis(self, track_id: str) -> str | None:
        """Met l'analyse d'un morceau en file."""
        ...


@dataclass(frozen=True, slots=True)
class ImportStats:
    """Bilan d'un import : total = nouveaux + déjà connus + ignorés."""

    total: int
    new: int
    known: int
    skipped: int
    queued: int


@dataclass(frozen=True, slots=True)
class ImportResult:
    """Résultat d'un import : la playlist de notre base et le bilan."""

    import_job_id: UUID
    playlist_id: UUID
    name: str
    created: bool  # False : la playlist existait déjà et a été mise à jour
    stats: ImportStats


class PlaylistImporter:
    """Importe une playlist d'un service musical dans notre base."""

    def __init__(self, db: Database, provider: MusicProvider, queue: AnalysisQueue) -> None:
        self._db = db
        self._provider = provider
        self._queue = queue

    async def import_playlist(self, user_id: UUID, access_token: str, playlist_id: str) -> ImportResult:
        """Importe la playlist ; l'import est noté dans import_job, réussi ou non."""
        jobs = ImportJobRepository(self._db)
        job_id = await jobs.start(user_id, f"{self._provider.name}_playlist")
        try:
            source = await self._provider.get_playlist(access_token, playlist_id)
            async with self._db.transaction() as tx:
                playlist_id_db, created = await self._save_playlist(
                    tx, user_id, source.external_id, source.name
                )
                track_ids, new_ids = await self._save_tracks(tx, source.tracks)
                await PlaylistRepository(tx).replace_items(playlist_id_db, track_ids)
        except Exception as e:
            await jobs.finish(job_id, "failed", {"playlist": playlist_id, "error": str(e)[:500]})
            raise

        # Après la validation (commit) : sinon le worker pourrait chercher un morceau pas encore visible.
        stats = ImportStats(
            total=len(source.tracks),
            new=len(new_ids),
            known=len(track_ids) - len(new_ids),
            skipped=len(source.tracks) - len(track_ids),
            queued=await self._enqueue(new_ids),
        )
        await jobs.finish(
            job_id,
            "done",
            {"playlist": source.external_id, "playlist_id": str(playlist_id_db), **asdict(stats)},
        )
        return ImportResult(job_id, playlist_id_db, source.name, created, stats)

    async def _save_playlist(
        self, tx: Queryable, user_id: UUID, external_id: str, name: str
    ) -> tuple[UUID, bool]:
        """Retrouve la playlist déjà importée (et la renomme) ou la crée ; indique si elle est nouvelle."""
        playlists = PlaylistRepository(tx)
        existing = await playlists.find_by_source(user_id, self._provider.name, external_id)
        if existing is not None:
            await playlists.rename(existing, name)
            return existing, False
        return await playlists.create_imported(user_id, name, self._provider.name, external_id), True

    async def _save_tracks(self, tx: Queryable, tracks: list[ProviderTrack]) -> tuple[list[UUID], list[UUID]]:
        """Enregistre les morceaux lisibles ; renvoie leurs identifiants (en ordre), puis les nouveaux."""
        repo = TrackRepository(tx)
        ordered: list[UUID] = []
        new: list[UUID] = []
        for track in tracks:
            if track.external_id is None:  # morceau local, épisode, morceau retiré
                continue
            track_id = await self._find(repo, track.isrc, track.external_id)
            if track_id is None:
                track_id = await repo.create(track.title, track.duration_ms, track.isrc)
                await repo.set_artists(track_id, track.artists)
                new.append(track_id)
            await repo.add_external_id(track_id, self._provider.name, track.external_id)
            ordered.append(track_id)
        return ordered, new

    async def _find(self, repo: TrackRepository, isrc: str | None, external_id: str) -> UUID | None:
        """Cherche le morceau en base : d'abord par ISRC, puis par identifiant chez le service."""
        if isrc:
            found = await repo.find_by_isrc(isrc)
            if found is not None:
                return found
        return await repo.find_by_external_id(self._provider.name, external_id)

    async def _enqueue(self, track_ids: list[UUID]) -> int:
        """Met les nouveaux morceaux en file d'analyse ; renvoie combien l'ont été."""
        queued = 0
        for track_id in track_ids:
            try:
                await self._queue.enqueue_analysis(str(track_id))
                queued += 1
            except Exception:
                # L'import est déjà validé : le morceau reste « pending » et pourra être relancé.
                log.exception("Mise en file impossible pour %s", track_id)
        return queued
