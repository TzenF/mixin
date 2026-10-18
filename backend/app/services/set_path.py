"""Cas d'usage « chemin entre deux morceaux » : de A à B en plusieurs morceaux qui s'enchaînent tous.

Le graphe vient du SQL (`transition_edges`), la recherche du domaine (`find_paths`). Coût mesuré le
18/10/2026 : environ 1,4 s sur tout le catalogue (906 morceaux analysés) ; il grandit avec le carré du nombre
de morceaux.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.adapters.track_repository import CatalogRow, ScoredTransition, TrackRepository
from app.domain.set_path import find_paths

MAX_INTERMEDIATES = 4
MAX_PATHS = 3


@dataclass(frozen=True, slots=True)
class PathResult:
    """Un chemin : les morceaux entre A et B, chaque enchaînement (de A jusqu'à B) et le plus faible."""

    tracks: list[CatalogRow]
    transitions: list[ScoredTransition]
    score: float


class PathFinder:
    """Cherche des chemins entre deux morceaux, avec les valeurs vues par l'utilisateur."""

    def __init__(self, tracks: TrackRepository) -> None:
        self._tracks = tracks

    async def paths(
        self, user_id: UUID, from_id: UUID, to_id: UUID, bpm_tolerance: float, only_mine: bool = True
    ) -> list[PathResult]:
        """Jusqu'à 3 chemins de 1 à 4 morceaux, sans intermédiaire commun, du meilleur au moins bon."""
        graph = await self._tracks.transition_graph(user_id, [from_id, to_id], bpm_tolerance, only_mine)
        found = find_paths(graph, from_id, to_id, MAX_INTERMEDIATES, MAX_PATHS)
        if not found:
            return []
        ids = list(dict.fromkeys(t for p in found for t in p.track_ids))
        rows = await self._tracks.by_ids(user_id, ids)
        transitions = await self._tracks.transitions_between(user_id, ids, bpm_tolerance)
        return [
            PathResult(
                tracks=[rows[t] for t in p.track_ids[1:-1]],
                transitions=[transitions[pair] for pair in zip(p.track_ids, p.track_ids[1:], strict=False)],
                score=p.score,
            )
            for p in found
        ]
