"""Accès aux morceaux en base : tout le SQL qui concerne `track` passe par ici."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from app.adapters.db import Queryable
from app.adapters.rating_repository import RATING_JOIN_SQL
from app.domain.camelot import CamelotKey

CatalogSort = Literal["title", "bpm", "key", "rank"]


@dataclass(frozen=True, slots=True)
class CatalogFilters:
    """Filtres du catalogue ; None = pas de filtre sur ce critère."""

    only_mine: bool = True  # False : tous les morceaux de la base
    text: str | None = None  # dans le titre ou le nom d'un artiste
    bpm_min: float | None = None
    bpm_max: float | None = None
    key: CamelotKey | None = None
    status: str | None = None
    sort: CatalogSort = "title"
    limit: int = 50
    offset: int = 0
    track_id: UUID | None = None  # un seul morceau (fiche d'un morceau)
    favorites_only: bool = False
    only_new: bool = False  # seulement ce qui n'est pas à moi (ni dans mes playlists, ni en favori)
    source_id: UUID | None = None  # seulement les morceaux de cette source de l'Explorer


@dataclass(frozen=True, slots=True)
class CatalogRow:
    """Un morceau du catalogue, avec les valeurs affichées (voir effective_features)."""

    id: UUID
    title: str
    artists: list[str]
    bpm: float | None
    camelot: str | None
    bpm_source: str | None
    key_source: str | None
    key_confidence: float | None
    analysis_status: str
    favorite: bool
    mine: bool  # dans une de mes playlists ou en favori
    rank: int | None = None  # place dans la source de l'Explorer (1 = premier), None hors source


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
class BridgeRow:
    """Un morceau qui fait le pont entre A et B : les deux enchaînements passent (voir bridge_tracks)."""

    track_id: UUID
    title: str
    artists: list[str]
    bpm: float
    camelot: str
    score: float  # le plus faible des deux enchaînements
    favorite: bool
    mine: bool
    incoming: TransitionRow  # A -> ce morceau
    incoming_score: float
    outgoing: TransitionRow  # ce morceau -> B
    outgoing_score: float


@dataclass(frozen=True, slots=True)
class ScoredTransition:
    """Un enchaînement compatible et son score (voir transition_edges en SQL)."""

    transition: TransitionRow
    score: float


@dataclass(frozen=True, slots=True)
class CatalogPage:
    """Une page du catalogue et le nombre total de morceaux qui passent les filtres."""

    total: int
    items: list[CatalogRow]


@dataclass(frozen=True, slots=True)
class SuggestionRow:
    """Une ligne renvoyée par la fonction SQL suggest_tracks."""

    track_id: UUID
    title: str
    artists: list[str]
    bpm: float
    camelot: str
    key_move: str
    half_double: bool
    bpm_diff_pct: float
    score: float
    favorite: bool
    my_rating: int | None  # ma note de l'enchaînement départ -> ce morceau
    my_comment: str | None


# Artistes du morceau `t`, dans l'ordre d'affichage.
_ARTISTS_SQL = """COALESCE((SELECT array_agg(a.name ORDER BY ta.position)
                 FROM track_artist ta JOIN artist a ON a.id = ta.artist_id
                 WHERE ta.track_id = t.id), '{}')"""

# Le morceau `t` est un favori de l'utilisateur.
_FAVORITE_SQL = (
    """EXISTS (SELECT 1 FROM favorite fav WHERE fav.track_id = t.id AND fav.user_id = %(user_id)s::uuid)"""
)

# Le morceau `t` est à moi : dans une de mes playlists, ou en favori.
_IS_MINE_SQL = f"""({_FAVORITE_SQL} OR EXISTS (
          SELECT 1 FROM playlist_item pi JOIN playlist p ON p.id = pi.playlist_id
          WHERE pi.track_id = t.id AND p.owner_id = %(user_id)s::uuid))"""

# « Mes morceaux » = ceux de mes playlists et mes favoris ; sans effet si only_mine est faux.
_MINE_SQL = f"(NOT %(only_mine)s OR {_IS_MINE_SQL})"

# Seulement mes favoris ; sans effet si favorites_only est faux.
_FAVORITES_ONLY_SQL = f"(NOT %(favorites_only)s OR {_FAVORITE_SQL})"

# suggest_tracks est appelée sans limite (NULL) : le filtre « mes morceaux » s'applique avant la limite.
_SUGGEST_SQL = f"""
SELECT s.track_id, t.title, {_ARTISTS_SQL} AS artists, s.bpm::float AS bpm, s.camelot, s.key_move,
       s.half_double, s.bpm_diff::float AS bpm_diff_pct, s.score::float AS score, {_FAVORITE_SQL} AS favorite,
       my_r.rating AS my_rating, my_r.comment AS my_comment
FROM suggest_tracks(%(user_id)s::uuid, %(seed)s::uuid, %(tolerance)s::numeric, NULL::integer) s
JOIN track t ON t.id = s.track_id
{RATING_JOIN_SQL.format(from_col="%(seed)s::uuid", to_col="s.track_id")}
WHERE {_MINE_SQL} AND {_FAVORITES_ONLY_SQL}
ORDER BY s.score DESC, lower(t.title), t.id
LIMIT %(limit)s
"""

# bridge_tracks est appelée sans limite (NULL), comme suggest_tracks : « mes morceaux » avant la limite.
_BRIDGE_SQL = f"""
SELECT b.*, t.title, {_ARTISTS_SQL} AS artists, {_FAVORITE_SQL} AS favorite, {_IS_MINE_SQL} AS mine
FROM bridge_tracks(%(user_id)s::uuid, %(from_id)s::uuid, %(to_id)s::uuid,
                   %(tolerance)s::numeric, NULL::integer) b
JOIN track t ON t.id = b.track_id
WHERE {_MINE_SQL}
ORDER BY b.score DESC, lower(t.title), t.id
LIMIT %(limit)s
"""

# Enchaînements où la lettre Camelot ne change pas (les autres passent de mineur à majeur, ou l'inverse).
_SAME_MODE_MOVES = {"same", "adjacent", "energy_shift"}

# Morceaux filtrés, avec leurs valeurs affichées.
_CATALOG_FROM = f"""
FROM track t
LEFT JOIN effective_features(%(user_id)s::uuid) f ON f.track_id = t.id
LEFT JOIN explore_item ei ON ei.track_id = t.id AND ei.source_id = %(source_id)s::uuid
WHERE {_MINE_SQL}
  AND {_FAVORITES_ONLY_SQL}
  AND (NOT %(only_new)s OR NOT {_IS_MINE_SQL})
  AND (%(source_id)s::uuid IS NULL OR ei.source_id IS NOT NULL)
  AND (%(track_id)s::uuid IS NULL OR t.id = %(track_id)s::uuid)
  AND (%(text)s::text IS NULL OR t.title ILIKE %(text)s OR EXISTS (
          SELECT 1 FROM track_artist ta JOIN artist a ON a.id = ta.artist_id
          WHERE ta.track_id = t.id AND a.name ILIKE %(text)s))
  AND (%(bpm_min)s::numeric IS NULL OR f.bpm >= %(bpm_min)s::numeric)
  AND (%(bpm_max)s::numeric IS NULL OR f.bpm <= %(bpm_max)s::numeric)
  AND (%(key_num)s::smallint IS NULL
       OR (f.camelot_num = %(key_num)s::smallint AND f.camelot_letter::text = %(key_letter)s::text))
  AND (%(status)s::analysis_status IS NULL OR t.analysis_status = %(status)s::analysis_status)
"""

# Colonnes d'un CatalogRow, pour un morceau `t` joint à effective_features `f` (catalogue, playlists).
TRACK_COLUMNS_SQL = f"""
       t.id, t.title, {_ARTISTS_SQL} AS artists,
       f.bpm::float AS bpm,
       f.camelot_num || f.camelot_letter AS camelot,
       f.bpm_source::text AS bpm_source, f.key_source::text AS key_source,
       f.key_confidence::float AS key_confidence,
       t.analysis_status::text AS analysis_status,
       {_FAVORITE_SQL} AS favorite,
       {_IS_MINE_SQL} AS mine
"""

_CATALOG_SELECT = f"SELECT {TRACK_COLUMNS_SQL}, ei.position + 1 AS rank"

# Liste fermée : le tri est inséré tel quel dans le SQL, jamais une valeur venue de la requête HTTP.
_CATALOG_ORDER: dict[CatalogSort, str] = {
    "title": "lower(t.title), t.id",
    "bpm": "f.bpm NULLS LAST, lower(t.title), t.id",
    "key": "f.camelot_num NULLS LAST, f.camelot_letter, f.bpm, lower(t.title), t.id",
    "rank": "ei.position NULLS LAST, lower(t.title), t.id",
}


def _like_pattern(text: str) -> str:
    """Motif ILIKE « contient ce texte » : les % et _ tapés par l'utilisateur sont pris littéralement."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


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

    async def set_analysis_status(self, track_id: UUID, status: str) -> None:
        """Note où en est l'analyse du morceau : pending, done, no_preview ou failed."""
        await self._db.fetch_one(
            "UPDATE track SET analysis_status = %(status)s::analysis_status WHERE id = %(id)s",
            {"id": track_id, "status": status},
        )

    async def pending_ids(self) -> list[UUID]:
        """Morceaux dont l'analyse n'a pas encore abouti (statut pending), du plus ancien au plus récent."""
        rows = await self._db.fetch_all(
            "SELECT id FROM track WHERE analysis_status = 'pending' ORDER BY created_at, id"
        )
        return [r["id"] for r in rows]

    async def catalog(self, user_id: UUID, filters: CatalogFilters) -> CatalogPage:
        """Page du catalogue vue par cet utilisateur (ses corrections passent avant Essentia)."""
        params = {
            "user_id": user_id,
            "only_mine": filters.only_mine,
            "text": _like_pattern(filters.text) if filters.text else None,
            "bpm_min": filters.bpm_min,
            "bpm_max": filters.bpm_max,
            "key_num": filters.key.number if filters.key else None,
            "key_letter": filters.key.letter if filters.key else None,
            "status": filters.status,
            "limit": filters.limit,
            "offset": filters.offset,
            "track_id": filters.track_id,
            "favorites_only": filters.favorites_only,
            "only_new": filters.only_new,
            "source_id": filters.source_id,
        }
        # Deux requêtes : le total reste juste même quand la page demandée est vide.
        total = await self._db.fetch_one(f"SELECT count(*) AS n {_CATALOG_FROM}", params)
        rows = await self._db.fetch_all(
            f"{_CATALOG_SELECT} {_CATALOG_FROM} ORDER BY {_CATALOG_ORDER[filters.sort]}"
            " LIMIT %(limit)s OFFSET %(offset)s",
            params,
        )
        assert total is not None
        return CatalogPage(total=total["n"], items=[CatalogRow(**r) for r in rows])

    async def suggestions(
        self,
        seed: UUID,
        user_id: UUID,
        bpm_tolerance: float,
        limit: int,
        only_mine: bool = True,
        favorites_only: bool = False,
    ) -> list[SuggestionRow]:
        """Morceaux compatibles avec `seed`, du meilleur score au moins bon (voir suggest_tracks en SQL)."""
        rows = await self._db.fetch_all(
            _SUGGEST_SQL,
            {
                "user_id": user_id,
                "seed": seed,
                "tolerance": bpm_tolerance,
                "limit": limit,
                "only_mine": only_mine,
                "favorites_only": favorites_only,
            },
        )
        return [SuggestionRow(**r) for r in rows]

    async def bridges(
        self,
        from_id: UUID,
        to_id: UUID,
        user_id: UUID,
        bpm_tolerance: float,
        limit: int,
        only_mine: bool = True,
    ) -> list[BridgeRow]:
        """Morceaux qui font le pont entre `from_id` et `to_id`, du meilleur au moins bon."""
        rows = await self._db.fetch_all(
            _BRIDGE_SQL,
            {
                "user_id": user_id,
                "from_id": from_id,
                "to_id": to_id,
                "tolerance": bpm_tolerance,
                "limit": limit,
                "only_mine": only_mine,
            },
        )
        return [
            BridgeRow(
                track_id=r["track_id"],
                title=r["title"],
                artists=r["artists"],
                bpm=float(r["bpm"]),
                camelot=r["camelot"],
                score=float(r["score"]),
                favorite=r["favorite"],
                mine=r["mine"],
                incoming=_compatible_transition(r, "in_"),
                incoming_score=float(r["in_score"]),
                outgoing=_compatible_transition(r, "out_"),
                outgoing_score=float(r["out_score"]),
            )
            for r in rows
        ]

    async def transition_graph(
        self, user_id: UUID, include: list[UUID], bpm_tolerance: float, only_mine: bool = True
    ) -> dict[UUID, list[tuple[UUID, float]]]:
        """Graphe des enchaînements compatibles entre mes morceaux (ou tous), `include` toujours compris.

        Pour chaque morceau : les morceaux vers lesquels il s'enchaîne, du meilleur score au moins bon.
        """
        rows = await self._db.fetch_all(
            f"""SELECT e.from_id, e.to_id, e.score::float AS score
                FROM transition_edges(
                    %(user_id)s::uuid,
                    ARRAY(SELECT t.id FROM track t WHERE {_MINE_SQL} OR t.id = ANY(%(include)s::uuid[])),
                    %(tolerance)s::numeric) e
                ORDER BY e.from_id, e.score DESC, e.to_id""",
            {"user_id": user_id, "include": include, "tolerance": bpm_tolerance, "only_mine": only_mine},
        )
        graph: dict[UUID, list[tuple[UUID, float]]] = {}
        for r in rows:
            graph.setdefault(r["from_id"], []).append((r["to_id"], r["score"]))
        return graph

    async def transitions_between(
        self, user_id: UUID, track_ids: list[UUID], bpm_tolerance: float
    ) -> dict[tuple[UUID, UUID], ScoredTransition]:
        """Enchaînements compatibles entre ces morceaux (dans les deux sens), par paire (de, vers)."""
        rows = await self._db.fetch_all(
            """SELECT * FROM transition_edges(%(user_id)s::uuid, %(ids)s::uuid[], %(tolerance)s::numeric)""",
            {"user_id": user_id, "ids": track_ids, "tolerance": bpm_tolerance},
        )
        return {
            (r["from_id"], r["to_id"]): ScoredTransition(_compatible_transition(r), float(r["score"]))
            for r in rows
        }

    async def by_ids(self, user_id: UUID, track_ids: list[UUID]) -> dict[UUID, CatalogRow]:
        """Ces morceaux, avec les valeurs vues par l'utilisateur, par identifiant (les inconnus manquent)."""
        rows = await self._db.fetch_all(
            f"""SELECT {TRACK_COLUMNS_SQL}
                FROM track t
                LEFT JOIN effective_features(%(user_id)s::uuid) f ON f.track_id = t.id
                WHERE t.id = ANY(%(ids)s::uuid[])""",
            {"user_id": user_id, "ids": track_ids},
        )
        return {r["id"]: CatalogRow(**r) for r in rows}

    async def set_favorite(self, user_id: UUID, track_id: UUID, favorite: bool) -> None:
        """Marque ou démarque le morceau comme favori de l'utilisateur (sans effet s'il l'est déjà)."""
        if favorite:
            sql = """INSERT INTO favorite (user_id, track_id) VALUES (%(user_id)s, %(track_id)s)
                     ON CONFLICT DO NOTHING"""
        else:
            sql = "DELETE FROM favorite WHERE user_id = %(user_id)s AND track_id = %(track_id)s"
        await self._db.fetch_one(sql, {"user_id": user_id, "track_id": track_id})

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

    async def find_external_id(self, track_id: UUID, provider: str) -> str | None:
        """Identifiant du morceau chez ce service musical, ou None."""
        row = await self._db.fetch_one(
            """SELECT external_id FROM track_external_id
               WHERE track_id = %(track_id)s AND provider = %(provider)s::music_provider""",
            {"track_id": track_id, "provider": provider},
        )
        return row["external_id"] if row else None

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


def _compatible_transition(row: dict[str, Any], prefix: str = "") -> TransitionRow:
    """Enchaînement compatible lu dans les colonnes d'une ligne (`in_…` / `out_…` pour un pont)."""
    return TransitionRow(
        key_move=row[f"{prefix}key_move"],
        key_distance=row[f"{prefix}key_distance"],
        half_double=row[f"{prefix}half_double"],
        bpm_diff=float(row[f"{prefix}bpm_diff"]),
        bpm_change=float(row[f"{prefix}bpm_change"]),
        tempo_ok=True,
        same_mode=row[f"{prefix}key_move"] in _SAME_MODE_MOVES,
        compatible=True,
    )
