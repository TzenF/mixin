"""Proposer l'ordre d'une playlist qui enchaîne le mieux ses morceaux (ouverture comprise).

On cherche d'abord le moins d'enchaînements refusés, puis la meilleure somme des scores. Ce n'est pas
l'optimum garanti (problème du voyageur de commerce) mais une bonne approximation rapide :
  1. départ glouton depuis quelques ouvertures possibles (toujours prendre le meilleur enchaînement suivant) ;
  2. amélioration locale : déplacer un morceau ou un bloc de 2 ou 3 morceaux (dans le même sens, car A -> B
     n'a pas le score de B -> A), tant que ça améliore l'ordre.
Les morceaux sont des indices 0..n-1 ; un morceau présent deux fois dans la playlist compte pour deux.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

# Coût d'un enchaînement refusé : plus que tout gain d'un déplacement (au plus 3 scores <= 1 changent),
# donc un déplacement n'échange jamais un enchaînement refusé contre de meilleurs scores ailleurs.
_REFUSED = 10.0
_MAX_BLOCK = 3
# Mesuré le 18/10/2026 sur une vraie playlist de 399 morceaux : 5 passes = 1,3 s, 30 = 7,2 s, même qualité.
MAX_PASSES = 5


@dataclass(frozen=True, slots=True)
class OrderQuality:
    """Bilan d'un ordre : enchaînements refusés, et somme des scores des enchaînements compatibles."""

    refused: int
    total_score: float


def order_quality(order: list[int], scores: Mapping[tuple[int, int], float]) -> OrderQuality:
    """Bilan de cet ordre ; un enchaînement absent de `scores` est refusé."""
    pairs = list(zip(order, order[1:], strict=False))
    known = [scores[p] for p in pairs if p in scores]
    return OrderQuality(refused=len(pairs) - len(known), total_score=sum(known))


def best_order(
    n: int, scores: Mapping[tuple[int, int], float], openers: int = 5, max_passes: int = MAX_PASSES
) -> list[int]:
    """Ordre proposé pour les morceaux 0..n-1 (`scores[(a, b)]` = score de a -> b compatible), jamais pire
    que l'ordre de départ 0, 1, 2…"""
    if n <= 2:
        return _best_small(n, scores)
    cost = [[_REFUSED] * n for _ in range(n)]
    for (a, b), score in scores.items():
        cost[a][b] = -score
    current = list(range(n))
    starts = [current] + [_greedy(cost, start) for start in _openers(cost, openers)]
    # Seuls les 2 meilleurs départs sont améliorés (le plus long) ; l'ordre actuel reste en lice tel quel.
    starts.sort(key=lambda order: _sort_key(order_quality(order, scores)))
    finalists = [_improve(order, cost, max_passes) for order in starts[:2]] + [current]
    return min(finalists, key=lambda order: _sort_key(order_quality(order, scores)))


def _sort_key(quality: OrderQuality) -> tuple[int, float]:
    """Clé de tri : moins de refus d'abord, puis meilleure somme."""
    return quality.refused, -quality.total_score


def _best_small(n: int, scores: Mapping[tuple[int, int], float]) -> list[int]:
    """Zéro, un ou deux morceaux : le meilleur des deux sens."""
    if n < 2:
        return list(range(n))
    return [1, 0] if scores.get((1, 0), -1.0) > scores.get((0, 1), -1.0) else [0, 1]


def _openers(cost: list[list[float]], count: int) -> list[int]:
    """Ouvertures à essayer : le morceau 0 (ouverture actuelle), puis ceux vers lesquels peu de morceaux
    s'enchaînent bien (difficiles à placer ailleurs qu'en tête)."""
    n = len(cost)
    incoming = [sum(1 for a in range(n) if a != b and cost[a][b] < 0) for b in range(n)]
    hardest = sorted(range(n), key=lambda b: (incoming[b], b))
    return list(dict.fromkeys([0, *hardest]))[:count]


def _greedy(cost: list[list[float]], start: int) -> list[int]:
    """Depuis `start`, prendre chaque fois le meilleur enchaînement vers un morceau pas encore placé."""
    n = len(cost)
    order = [start]
    left = set(range(n)) - {start}
    while left:
        row = cost[order[-1]]
        nxt = min(left, key=lambda b: (row[b], b))
        order.append(nxt)
        left.remove(nxt)
    return order


def _improve(order: list[int], cost: list[list[float]], max_passes: int) -> list[int]:
    """Déplace des blocs de 1 à 3 morceaux tant que ça baisse le coût total (au plus `max_passes` passes)."""
    order = list(order)
    n = len(order)
    for _ in range(max_passes):
        changed = False
        for size in range(1, _MAX_BLOCK + 1):
            i = 0
            while i + size <= n:
                move = _best_move(order, cost, i, size)
                if move is not None:
                    block = order[i : i + size]
                    rest = order[:i] + order[i + size :]
                    order = rest[:move] + block + rest[move:]
                    changed = True
                i += 1
        if not changed:
            break
    return order


def _best_move(order: list[int], cost: list[list[float]], i: int, size: int) -> int | None:
    """Meilleure place (dans l'ordre sans le bloc) pour le bloc order[i:i+size], si elle baisse le coût."""
    n = len(order)
    first, last = order[i], order[i + size - 1]
    before = order[i - 1] if i > 0 else None
    after = order[i + size] if i + size < n else None
    # Retirer le bloc : on perd before -> first et last -> after, on gagne before -> after.
    removal = 0.0
    if before is not None:
        removal -= cost[before][first]
    if after is not None:
        removal -= cost[last][after]
    if before is not None and after is not None:
        removal += cost[before][after]
    rest = order[:i] + order[i + size :]
    best_gain, best_at = -1e-9, None
    for j in range(len(rest) + 1):
        if j == i:
            continue  # même place
        left = rest[j - 1] if j > 0 else None
        right = rest[j] if j < len(rest) else None
        insertion = 0.0
        if left is not None:
            insertion += cost[left][first]
        if right is not None:
            insertion += cost[last][right]
        if left is not None and right is not None:
            insertion -= cost[left][right]
        gain = -(removal + insertion)
        if gain > best_gain:
            best_gain, best_at = gain, j
    return best_at
