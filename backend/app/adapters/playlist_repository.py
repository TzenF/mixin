"""Accès aux playlists de notre base (`playlist`, `playlist_item`)."""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime
from uuid import UUID

from app.adapters.db import Queryable
from app.adapters.rating_repository import RATING_JOIN_SQL, RatingRow
from app.adapters.track_repository import TRACK_COLUMNS_SQL, CatalogRow


@dataclass(frozen=True, slots=True)
class PlaylistRow:
    """Une playlist ; source_provider est None pour une playlist créée dans l'application."""

    id: UUID
    name: str
    source_provider: str | None
    track_count: int
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ExportRow:
    """Lien entre une de nos playlists et sa copie exportée chez un service musical."""

    external_playlist_id: str
    last_synced_at: datetime


@dataclass(frozen=True, slots=True)
class TransitionRow:
    """Enchaînement d'un morceau vers le suivant (voir la fonction SQL transition)."""

    key_move: str | None
    key_distance: int
    half_double: bool
    bpm_diff: float
    bpm_change: float
    tempo_ok: bool  # écart de BPM dans la tolérance (le reste vient de la tonalité)
    same_mode: bool  # même lettre Camelot (mineur/mineur ou majeur/majeur)
    compatible: bool


@dataclass(frozen=True, slots=True)
class PlaylistItemRow:
    """Un morceau de la playlist, et son enchaînement vers le suivant (None : dernier, ou non analysé)."""

    item_id: int
    position: int
    track: CatalogRow
    transition_to_next: TransitionRow | None
    my_rating: RatingRow | None = None  # ma note de ce morceau vers le suivant


_PLAYLIST_SQL = """
SELECT p.id, p.name, p.source_provider::text AS source_provider, p.updated_at,
       (SELECT count(*) FROM playlist_item pi WHERE pi.playlist_id = p.id)::integer AS track_count
FROM playlist p
WHERE p.owner_id = %(owner)s::uuid
"""

# Morceaux dans l'ordre, valeurs affichées pour l'utilisateur, et enchaînement vers le suivant (LEAD).
_ITEMS_SQL = f"""
WITH items AS (
    SELECT pi.id AS item_id, pi.position, {TRACK_COLUMNS_SQL},
           f.bpm AS raw_bpm, f.camelot_num AS raw_num, f.camelot_letter::text AS raw_letter
    FROM playlist_item pi
    JOIN track t ON t.id = pi.track_id
    LEFT JOIN effective_features(%(owner)s::uuid) f ON f.track_id = t.id
    WHERE pi.playlist_id = %(playlist_id)s::uuid
),
paired AS (
    SELECT items.*,
           LEAD(raw_bpm) OVER w AS next_bpm,
           LEAD(raw_num) OVER w AS next_num,
           LEAD(raw_letter) OVER w AS next_letter,
           LEAD(id) OVER w AS next_track_id
    FROM items
    WINDOW w AS (ORDER BY position)
)
SELECT p.*, tr.key_move, tr.key_distance, tr.half_double,
       tr.bpm_diff::float AS bpm_diff, tr.bpm_change::float AS bpm_change,
       tr.bpm_diff <= %(tolerance)s::numeric AS tempo_ok, p.raw_letter = p.next_letter AS same_mode,
       tr.compatible, my_r.rating AS my_rating, my_r.comment AS my_comment
FROM paired p
LEFT JOIN LATERAL transition(p.raw_bpm, p.raw_num, p.raw_letter,
                             p.next_bpm, p.next_num, p.next_letter, %(tolerance)s::numeric) tr ON true
{RATING_JOIN_SQL.format(from_col="p.id", to_col="p.next_track_id")}
ORDER BY p.position
"""

_TRACK_FIELDS = [f.name for f in fields(CatalogRow)]
_TRANSITION_FIELDS = [f.name for f in fields(TransitionRow)]


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

    async def create(self, owner_id: UUID, name: str, forked_from: UUID | None = None) -> UUID:
        """Crée une playlist vide dans l'application (forked_from : playlist dont elle est la copie)."""
        row = await self._db.fetch_one(
            """INSERT INTO playlist (owner_id, name, forked_from_id)
               VALUES (%(owner)s, %(name)s, %(forked_from)s) RETURNING id""",
            {"owner": owner_id, "name": name, "forked_from": forked_from},
        )
        assert row is not None
        return row["id"]

    async def lock(self, playlist_id: UUID) -> None:
        """Verrouille la playlist jusqu'à la fin de la transaction, pour ajouter sans conflit de position."""
        await self._db.fetch_one("SELECT 1 FROM playlist WHERE id = %(id)s FOR UPDATE", {"id": playlist_id})

    async def append_item(self, playlist_id: UUID, track_id: UUID) -> tuple[int, int]:
        """Ajoute le morceau en fin de playlist ; renvoie (identifiant de l'élément, position)."""
        row = await self._db.fetch_one(
            """INSERT INTO playlist_item (playlist_id, track_id, position)
               SELECT %(id)s, %(track_id)s,
                      COALESCE((SELECT max(position) + 1 FROM playlist_item WHERE playlist_id = %(id)s), 0)
               RETURNING id, position""",
            {"id": playlist_id, "track_id": track_id},
        )
        assert row is not None
        await self._touch(playlist_id)
        return row["id"], row["position"]

    async def item_ids(self, playlist_id: UUID) -> list[int]:
        """Identifiants des éléments de la playlist, dans l'ordre."""
        rows = await self._db.fetch_all(
            "SELECT id FROM playlist_item WHERE playlist_id = %(id)s ORDER BY position", {"id": playlist_id}
        )
        return [r["id"] for r in rows]

    async def reorder(self, playlist_id: UUID, item_ids: list[int]) -> None:
        """Place les éléments dans cet ordre (0, 1, 2…) ; unicité des positions vérifiée au commit."""
        await self._db.fetch_one(
            """UPDATE playlist_item pi SET position = (t.ord - 1)::integer
               FROM unnest(%(ids)s::bigint[]) WITH ORDINALITY AS t(id, ord)
               WHERE pi.id = t.id AND pi.playlist_id = %(playlist_id)s""",
            {"playlist_id": playlist_id, "ids": item_ids},
        )
        await self._touch(playlist_id)

    async def remove_item(self, playlist_id: UUID, item_id: int) -> bool:
        """Retire l'élément et recompacte les positions ; False s'il n'est pas dans cette playlist."""
        row = await self._db.fetch_one(
            "DELETE FROM playlist_item WHERE id = %(item)s AND playlist_id = %(id)s RETURNING id",
            {"id": playlist_id, "item": item_id},
        )
        if row is None:
            return False
        await self._db.fetch_one(
            """UPDATE playlist_item pi SET position = (r.rn - 1)::integer
               FROM (SELECT id, row_number() OVER (ORDER BY position) AS rn
                     FROM playlist_item WHERE playlist_id = %(id)s) r
               WHERE pi.id = r.id""",
            {"id": playlist_id},
        )
        await self._touch(playlist_id)
        return True

    async def copy_items(self, source_id: UUID, target_id: UUID) -> None:
        """Recopie les morceaux de `source_id` dans `target_id`, dans le même ordre."""
        await self._db.fetch_one(
            """INSERT INTO playlist_item (playlist_id, track_id, position)
               SELECT %(target)s, track_id, position FROM playlist_item WHERE playlist_id = %(source)s""",
            {"source": source_id, "target": target_id},
        )

    async def delete(self, playlist_id: UUID) -> None:
        """Supprime la playlist et ses éléments (les morceaux restent dans le catalogue)."""
        await self._db.fetch_one("DELETE FROM playlist WHERE id = %(id)s", {"id": playlist_id})

    async def _touch(self, playlist_id: UUID) -> None:
        """Note que la playlist vient d'être modifiée."""
        await self._db.fetch_one(
            "UPDATE playlist SET updated_at = now() WHERE id = %(id)s", {"id": playlist_id}
        )

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
        await self._touch(playlist_id)

    async def track_ids(self, playlist_id: UUID) -> list[UUID]:
        """Morceaux de la playlist, dans l'ordre."""
        rows = await self._db.fetch_all(
            "SELECT track_id FROM playlist_item WHERE playlist_id = %(id)s ORDER BY position",
            {"id": playlist_id},
        )
        return [r["track_id"] for r in rows]

    async def list_for_owner(self, owner_id: UUID) -> list[PlaylistRow]:
        """Playlists de l'utilisateur, les plus récemment modifiées d'abord."""
        rows = await self._db.fetch_all(
            f"{_PLAYLIST_SQL} ORDER BY p.updated_at DESC, lower(p.name)", {"owner": owner_id}
        )
        return [PlaylistRow(**r) for r in rows]

    async def get_for_owner(self, owner_id: UUID, playlist_id: UUID) -> PlaylistRow | None:
        """La playlist si elle appartient à cet utilisateur, sinon None (même si elle existe)."""
        row = await self._db.fetch_one(
            f"{_PLAYLIST_SQL} AND p.id = %(playlist_id)s::uuid",
            {"owner": owner_id, "playlist_id": playlist_id},
        )
        return PlaylistRow(**row) if row else None

    async def items_with_transitions(
        self, owner_id: UUID, playlist_id: UUID, bpm_tolerance: float
    ) -> list[PlaylistItemRow]:
        """Morceaux dans l'ordre (valeurs vues par le propriétaire) et enchaînement vers le suivant."""
        rows = await self._db.fetch_all(
            _ITEMS_SQL,
            {"owner": owner_id, "user_id": owner_id, "playlist_id": playlist_id, "tolerance": bpm_tolerance},
        )
        return [
            PlaylistItemRow(
                item_id=r["item_id"],
                position=r["position"],
                track=CatalogRow(**{k: r[k] for k in _TRACK_FIELDS}),
                transition_to_next=(
                    TransitionRow(**{k: r[k] for k in _TRANSITION_FIELDS})
                    if r["key_distance"] is not None
                    else None
                ),
                my_rating=RatingRow(r["my_rating"], r["my_comment"]) if r["my_rating"] is not None else None,
            )
            for r in rows
        ]

    async def external_track_ids(self, playlist_id: UUID, provider: str) -> list[str | None]:
        """Identifiant de chaque morceau chez ce service, dans l'ordre (None s'il n'y en a pas)."""
        rows = await self._db.fetch_all(
            """SELECT e.external_id
               FROM playlist_item pi
               LEFT JOIN track_external_id e
                      ON e.track_id = pi.track_id AND e.provider = %(provider)s::music_provider
               WHERE pi.playlist_id = %(id)s
               ORDER BY pi.position""",
            {"id": playlist_id, "provider": provider},
        )
        return [r["external_id"] for r in rows]

    async def get_export(self, playlist_id: UUID, provider: str) -> ExportRow | None:
        """Dernier export de la playlist vers ce service, ou None."""
        row = await self._db.fetch_one(
            """SELECT external_playlist_id, last_synced_at FROM playlist_export
               WHERE playlist_id = %(id)s AND provider = %(provider)s::music_provider""",
            {"id": playlist_id, "provider": provider},
        )
        return ExportRow(**row) if row else None

    async def save_export(self, playlist_id: UUID, provider: str, external_playlist_id: str) -> ExportRow:
        """Enregistre (ou met à jour) l'export de la playlist vers ce service."""
        row = await self._db.fetch_one(
            """INSERT INTO playlist_export (playlist_id, provider, external_playlist_id)
               VALUES (%(id)s, %(provider)s::music_provider, %(ext)s)
               ON CONFLICT (playlist_id, provider) DO UPDATE
                   SET external_playlist_id = EXCLUDED.external_playlist_id, last_synced_at = now()
               RETURNING external_playlist_id, last_synced_at""",
            {"id": playlist_id, "provider": provider, "ext": external_playlist_id},
        )
        assert row is not None
        return ExportRow(**row)
