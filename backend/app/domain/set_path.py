"""Chercher un chemin de A à B en plusieurs morceaux, dans le graphe des enchaînements compatibles.

Le graphe vient du SQL (`transition_edges`) : pour chaque morceau, les morceaux vers lesquels il s'enchaîne et
le score de l'enchaînement. Le meilleur chemin a le moins de morceaux possible, puis, à longueur égale, le
meilleur enchaînement le plus faible (un chemin vaut son pire passage), puis la meilleure somme des scores.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

# morceau -> [(morceau suivant possible, score de l'enchaînement)]
TransitionGraph = Mapping[UUID, Sequence[tuple[UUID, float]]]

# (enchaînement le plus faible, somme des scores, morceaux depuis A) : comparé sur les deux premiers.
_Partial = tuple[float, float, tuple[UUID, ...]]


@dataclass(frozen=True, slots=True)
class SetPath:
    """Un chemin de A à B : les morceaux dans l'ordre (A et B compris) et son enchaînement le plus faible."""

    track_ids: tuple[UUID, ...]
    score: float


def find_paths(
    graph: TransitionGraph, start: UUID, end: UUID, max_intermediates: int = 4, count: int = 3
) -> list[SetPath]:
    """Jusqu'à `count` chemins de `start` à `end`, sans intermédiaire commun, du meilleur au moins bon.

    Chaque chemin a au moins un morceau entre A et B (l'enchaînement direct n'est pas un chemin) et au plus
    `max_intermediates`. Après le meilleur, on cherche de nouveau sans ses morceaux : de vraies alternatives.
    """
    paths: list[SetPath] = []
    banned: set[UUID] = set()
    while len(paths) < count:
        path = _best_path(graph, start, end, max_intermediates, banned)
        if path is None:
            break
        paths.append(path)
        banned.update(path.track_ids[1:-1])
    return paths


def _best_path(
    graph: TransitionGraph, start: UUID, end: UUID, max_intermediates: int, banned: set[UUID]
) -> SetPath | None:
    """Le meilleur chemin le plus court qui évite `banned`, ou None.

    Recherche par couches : la couche k garde, pour chaque morceau, le meilleur chemin de k morceaux depuis A
    qui y mène (approximation : un chemin moins bon n'est pas gardé, même s'il éviterait un détour).
    """
    layer: dict[UUID, _Partial] = {start: (math.inf, 0.0, (start,))}
    for _ in range(max_intermediates):
        layer = _next_layer(graph, layer, end, banned)
        best: _Partial | None = None
        for weakest, total, path in layer.values():
            for target, score in graph.get(path[-1], ()):
                if target == end:
                    candidate = (min(weakest, score), total + score, (*path, end))
                    if best is None or candidate[:2] > best[:2]:
                        best = candidate
        if best is not None:
            return SetPath(track_ids=best[2], score=best[0])
    return None


def _next_layer(
    graph: TransitionGraph, layer: dict[UUID, _Partial], end: UUID, banned: set[UUID]
) -> dict[UUID, _Partial]:
    """Couche suivante : chaque chemin prolongé d'un morceau (ni B, ni interdit, ni déjà dans le chemin)."""
    following: dict[UUID, _Partial] = {}
    for weakest, total, path in layer.values():
        for target, score in graph.get(path[-1], ()):
            if target == end or target in banned or target in path:
                continue
            candidate = (min(weakest, score), total + score, (*path, target))
            current = following.get(target)
            if current is None or candidate[:2] > current[:2]:
                following[target] = candidate
    return following
