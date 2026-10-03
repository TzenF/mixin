"""Accès aux morceaux en base : tout le SQL qui concerne `track` passe par ici."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.adapters.db import Database


@dataclass(frozen=True, slots=True)
class SuggestionRow:
    """Une ligne renvoyée par la fonction SQL suggest_tracks."""

    track_id: UUID
    title: str
    bpm: float
    camelot: str
    key_move: str
    half_double: bool
    bpm_diff_pct: float
    score: float


_SUGGEST_SQL = """
SELECT s.track_id, t.title, s.bpm::float AS bpm, s.camelot, s.key_move, s.half_double,
       s.bpm_diff::float AS bpm_diff_pct, s.score::float AS score
FROM suggest_tracks(%(user_id)s::uuid, %(seed)s::uuid, %(tolerance)s::numeric, %(limit)s::integer) s
JOIN track t ON t.id = s.track_id
ORDER BY s.score DESC
"""


class TrackRepository:
    """Lecture et écriture des morceaux."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def exists(self, track_id: UUID | str) -> bool:
        """Indique si le morceau existe."""
        return await self._db.fetch_one("SELECT 1 FROM track WHERE id = %(id)s", {"id": track_id}) is not None

    async def get_isrc(self, track_id: UUID | str) -> str | None:
        """Renvoie l'ISRC du morceau (None s'il n'en a pas ou si le morceau n'existe pas)."""
        row = await self._db.fetch_one("SELECT isrc FROM track WHERE id = %(id)s", {"id": track_id})
        return row["isrc"] if row else None

    async def suggestions(
        self, seed: UUID, user_id: UUID | None, bpm_tolerance: float, limit: int
    ) -> list[SuggestionRow]:
        """Morceaux compatibles avec `seed`, du meilleur score au moins bon (voir suggest_tracks en SQL)."""
        rows = await self._db.fetch_all(
            _SUGGEST_SQL, {"user_id": user_id, "seed": seed, "tolerance": bpm_tolerance, "limit": limit}
        )
        return [SuggestionRow(**r) for r in rows]
