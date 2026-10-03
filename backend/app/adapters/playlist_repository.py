"""Accès aux playlists de notre base (`playlist`, `playlist_item`)."""

from __future__ import annotations

from uuid import UUID

from app.adapters.db import Queryable


class PlaylistRepository:
    """Lecture et écriture des playlists et de leurs morceaux."""

    def __init__(self, db: Queryable) -> None:
        self._db = db

    async def find_by_source(self, owner_id: UUID, provider: str, external_id: str) -> UUID | None:
        """Renvoie la playlist déjà importée depuis cette playlist d'origine, ou None."""
        row = await self._db.fetch_one(
            """SELECT id FROM playlist
               WHERE owner_id = %(owner)s AND source_provider = %(provider)s::music_provider
                 AND source_external_id = %(ext)s""",
            {"owner": owner_id, "provider": provider, "ext": external_id},
        )
        return row["id"] if row else None

    async def imported_sources(self, owner_id: UUID, provider: str) -> set[str]:
        """Identifiants des playlists d'origine que l'utilisateur a déjà importées depuis ce service."""
        rows = await self._db.fetch_all(
            """SELECT source_external_id FROM playlist
               WHERE owner_id = %(owner)s AND source_provider = %(provider)s::music_provider""",
            {"owner": owner_id, "provider": provider},
        )
        return {r["source_external_id"] for r in rows}

    async def create_imported(self, owner_id: UUID, name: str, provider: str, external_id: str) -> UUID:
        """Crée une playlist importée d'un service musical et renvoie son identifiant."""
        row = await self._db.fetch_one(
            """INSERT INTO playlist (owner_id, name, source_provider, source_external_id)
               VALUES (%(owner)s, %(name)s, %(provider)s::music_provider, %(ext)s) RETURNING id""",
            {"owner": owner_id, "name": name, "provider": provider, "ext": external_id},
        )
        assert row is not None
        return row["id"]

    async def rename(self, playlist_id: UUID, name: str) -> None:
        """Change le nom de la playlist."""
        await self._db.fetch_one(
            "UPDATE playlist SET name = %(name)s, updated_at = now() WHERE id = %(id)s",
            {"id": playlist_id, "name": name},
        )

    async def replace_items(self, playlist_id: UUID, track_ids: list[UUID]) -> None:
        """Remplace tous les morceaux de la playlist, dans l'ordre donné (positions 0, 1, 2…)."""
        await self._db.fetch_one("DELETE FROM playlist_item WHERE playlist_id = %(id)s", {"id": playlist_id})
        await self._db.fetch_one(
            """INSERT INTO playlist_item (playlist_id, track_id, position)
               SELECT %(id)s, t.track_id, (t.ord - 1)::integer
               FROM unnest(%(track_ids)s::uuid[]) WITH ORDINALITY AS t(track_id, ord)""",
            {"id": playlist_id, "track_ids": track_ids},
        )
        await self._db.fetch_one(
            "UPDATE playlist SET updated_at = now() WHERE id = %(id)s", {"id": playlist_id}
        )

    async def track_ids(self, playlist_id: UUID) -> list[UUID]:
        """Morceaux de la playlist, dans l'ordre."""
        rows = await self._db.fetch_all(
            "SELECT track_id FROM playlist_item WHERE playlist_id = %(id)s ORDER BY position",
            {"id": playlist_id},
        )
        return [r["track_id"] for r in rows]
