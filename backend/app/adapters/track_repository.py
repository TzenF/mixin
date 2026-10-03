"""Accès aux morceaux en base : tout le SQL qui concerne `track` passe par ici."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.adapters.db import Queryable


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

    def __init__(self, db: Queryable) -> None:
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

    async def find_by_isrc(self, isrc: str) -> UUID | None:
        """Renvoie le morceau qui a cet ISRC, ou None."""
        row = await self._db.fetch_one("SELECT id FROM track WHERE isrc = %(isrc)s", {"isrc": isrc})
        return row["id"] if row else None

    async def find_by_external_id(self, provider: str, external_id: str) -> UUID | None:
        """Renvoie le morceau qui a cet identifiant chez ce service musical, ou None."""
        row = await self._db.fetch_one(
            """SELECT track_id FROM track_external_id
               WHERE provider = %(provider)s::music_provider AND external_id = %(ext)s""",
            {"provider": provider, "ext": external_id},
        )
        return row["track_id"] if row else None

    async def create(self, title: str, duration_ms: int | None, isrc: str | None) -> UUID:
        """Crée un morceau (analyse en attente) et renvoie son identifiant."""
        row = await self._db.fetch_one(
            """INSERT INTO track (title, duration_ms, isrc)
               VALUES (%(title)s, %(duration)s, %(isrc)s) RETURNING id""",
            {"title": title, "duration": duration_ms, "isrc": isrc},
        )
        assert row is not None
        return row["id"]

    async def add_external_id(self, track_id: UUID, provider: str, external_id: str) -> None:
        """Associe un identifiant externe au morceau ; sans effet s'il en a déjà un pour ce service."""
        await self._db.fetch_one(
            """INSERT INTO track_external_id (track_id, provider, external_id)
               VALUES (%(track_id)s, %(provider)s::music_provider, %(ext)s)
               ON CONFLICT DO NOTHING""",
            {"track_id": track_id, "provider": provider, "ext": external_id},
        )

    async def set_artists(self, track_id: UUID, names: list[str]) -> None:
        """Associe les artistes au morceau, dans l'ordre (0 = principal), en réutilisant ceux qui existent."""
        for position, name in enumerate(names):
            await self._db.fetch_one(
                """INSERT INTO track_artist (track_id, artist_id, position)
                   VALUES (%(track_id)s, %(artist_id)s, %(position)s)
                   ON CONFLICT DO NOTHING""",
                {"track_id": track_id, "artist_id": await self._artist_id(name), "position": position},
            )

    async def _artist_id(self, name: str) -> UUID:
        """Renvoie l'artiste de ce nom (sans tenir compte de la casse), en le créant s'il n'existe pas."""
        # Limite connue : deux homonymes sont fusionnés (on ne stocke pas l'ID Spotify des artistes).
        row = await self._db.fetch_one(
            "SELECT id FROM artist WHERE lower(name) = lower(%(name)s) ORDER BY id LIMIT 1", {"name": name}
        )
        if row is None:
            row = await self._db.fetch_one(
                "INSERT INTO artist (name) VALUES (%(name)s) RETURNING id", {"name": name}
            )
        assert row is not None
        return row["id"]
