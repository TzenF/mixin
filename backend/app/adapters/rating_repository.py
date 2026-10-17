"""Accès aux notes des transitions (`transition_rating`) : une note par utilisateur et par paire A → B."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.adapters.db import Queryable


@dataclass(frozen=True, slots=True)
class RatingRow:
    """Ma note d'un enchaînement (1 à 5) et mon commentaire éventuel."""

    rating: int
    comment: str | None


# Jointure réutilisée par les playlists et les suggestions : ma note de `{from_col}` vers `{to_col}`.
RATING_JOIN_SQL = """LEFT JOIN transition_rating my_r
       ON my_r.user_id = %(user_id)s::uuid
      AND my_r.from_track_id = {from_col} AND my_r.to_track_id = {to_col}"""


class RatingRepository:
    """Lecture et écriture de mes notes de transitions."""

    def __init__(self, db: Queryable) -> None:
        self._db = db

    async def save(self, user_id: UUID, from_id: UUID, to_id: UUID, rating: RatingRow) -> None:
        """Enregistre ma note de A vers B en remplaçant la précédente (created_at : dernière note)."""
        await self._db.fetch_one(
            """INSERT INTO transition_rating (user_id, from_track_id, to_track_id, rating, comment)
               VALUES (%(user)s, %(a)s, %(b)s, %(rating)s, %(comment)s)
               ON CONFLICT (user_id, from_track_id, to_track_id) DO UPDATE
                   SET rating = EXCLUDED.rating, comment = EXCLUDED.comment, created_at = now()""",
            {"user": user_id, "a": from_id, "b": to_id, "rating": rating.rating, "comment": rating.comment},
        )

    async def delete(self, user_id: UUID, from_id: UUID, to_id: UUID) -> None:
        """Efface ma note de A vers B (sans effet s'il n'y en a pas)."""
        await self._db.fetch_one(
            """DELETE FROM transition_rating
               WHERE user_id = %(user)s AND from_track_id = %(a)s AND to_track_id = %(b)s""",
            {"user": user_id, "a": from_id, "b": to_id},
        )

    async def count(self, user_id: UUID) -> int:
        """Nombre d'enchaînements que j'ai notés."""
        row = await self._db.fetch_one(
            "SELECT count(*) AS n FROM transition_rating WHERE user_id = %(user)s", {"user": user_id}
        )
        assert row is not None
        return row["n"]
