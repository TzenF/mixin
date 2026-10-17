"""Accès aux sources de l'Explorer (`explore_source`, `explore_item`) : tops et playlists éditoriales."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.adapters.db import Queryable


@dataclass(frozen=True, slots=True)
class ExploreSourceRow:
    """Une source de l'Explorer et l'état de sa dernière synchronisation."""

    id: UUID
    provider: str
    external_id: str
    title: str
    curator: str | None
    added_by: UUID | None
    last_synced_at: datetime | None
    last_error: str | None
    track_count: int
    analysed_count: int  # BPM et tonalité connus
    pending_count: int  # encore en attente d'analyse (un morceau sans extrait n'y est plus)


_SOURCE_SQL = """
SELECT s.id, s.provider::text AS provider, s.external_id, s.title, s.curator, s.added_by,
       s.last_synced_at, s.last_error,
       (SELECT count(*) FROM explore_item ei WHERE ei.source_id = s.id)::integer AS track_count,
       (SELECT count(*) FROM explore_item ei JOIN track t ON t.id = ei.track_id
         WHERE ei.source_id = s.id AND t.analysis_status = 'done')::integer AS analysed_count,
       (SELECT count(*) FROM explore_item ei JOIN track t ON t.id = ei.track_id
         WHERE ei.source_id = s.id AND t.analysis_status = 'pending')::integer AS pending_count
FROM explore_source s
"""


class ExploreRepository:
    """Lecture et écriture des sources de l'Explorer et de leur classement."""

    def __init__(self, db: Queryable) -> None:
        self._db = db

    async def list(self) -> list[ExploreSourceRow]:
        """Toutes les sources : par défaut d'abord, puis par date d'ajout."""
        rows = await self._db.fetch_all(
            f"{_SOURCE_SQL} ORDER BY s.added_by IS NOT NULL, s.created_at, s.title"
        )
        return [ExploreSourceRow(**r) for r in rows]

    async def get(self, source_id: UUID) -> ExploreSourceRow | None:
        """La source, ou None si elle n'existe pas."""
        row = await self._db.fetch_one(f"{_SOURCE_SQL} WHERE s.id = %(id)s", {"id": source_id})
        return ExploreSourceRow(**row) if row else None

    async def ids(self, never_synced_only: bool = False) -> list[UUID]:
        """Identifiants des sources (seulement celles jamais synchronisées, si demandé)."""
        rows = await self._db.fetch_all(
            "SELECT id FROM explore_source WHERE NOT %(only)s OR last_synced_at IS NULL ORDER BY created_at",
            {"only": never_synced_only},
        )
        return [r["id"] for r in rows]

    async def lock_sync(self) -> None:
        """Une seule synchronisation à la fois jusqu'à la fin de la transaction.

        Deux sources partagent souvent des morceaux (Top France et Top Worldwide) : créées en parallèle, les
        mêmes lignes (morceau par ISRC, artiste par nom) provoquaient un DeadlockDetected (vu le 17/10/2026).
        """
        await self._db.fetch_one("SELECT pg_advisory_xact_lock(hashtext('explore_sync'))")

    async def replace_items(self, source_id: UUID, track_ids: list[UUID]) -> None:
        """Remplace le classement de la source (positions 0, 1, 2…), sans doublon."""
        await self._db.fetch_one("DELETE FROM explore_item WHERE source_id = %(id)s", {"id": source_id})
        await self._db.fetch_one(
            """INSERT INTO explore_item (source_id, track_id, position)
               SELECT %(id)s, t.track_id, (t.ord - 1)::integer
               FROM unnest(%(track_ids)s::uuid[]) WITH ORDINALITY AS t(track_id, ord)""",
            {"id": source_id, "track_ids": track_ids},
        )

    async def mark_synced(self, source_id: UUID) -> None:
        """Note une synchronisation réussie."""
        await self._db.fetch_one(
            "UPDATE explore_source SET last_synced_at = now(), last_error = NULL WHERE id = %(id)s",
            {"id": source_id},
        )

    async def mark_failed(self, source_id: UUID, error: str) -> None:
        """Note l'échec d'une synchronisation (le classement précédent reste en place)."""
        await self._db.fetch_one(
            "UPDATE explore_source SET last_error = %(error)s WHERE id = %(id)s",
            {"id": source_id, "error": error[:300]},
        )
