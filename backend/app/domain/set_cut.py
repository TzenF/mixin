"""Proposer quels morceaux retirer pour qu'un set tienne dans son créneau, en abîmant le moins le set.

L'ouverture et le dernier morceau ne sont jamais retirés : retirer un bout ne coûte qu'un enchaînement,
l'algorithme les choisirait presque toujours (vu le 18/10/2026 sur une vraie playlist), or ce sont des choix
délibérés.
On retire un morceau à la fois, tant que le set dépasse. À chaque fois, celui dont le retrait abîme le moins :
  1. d'abord celui dont le retrait répare un enchaînement refusé (moins de refus après) ;
  2. puis celui qui ne casse rien, en perdant le moins de score ;
  3. à égalité, le plus long (pour retirer le moins de morceaux possible).
Retirer T entre P et S remplace P -> T et T -> S par P -> S.
Un enchaînement avec un morceau non analysé est inconnu : jamais refusé, et il compte comme un enchaînement
moyen (moyenne des scores connus). À 0, retirer un morceau pas encore analysé ne coûterait rien : il partirait
toujours en premier.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SetQuality:
    """Bilan d'un ordre : enchaînements refusés (entre morceaux analysés) et somme des scores."""

    refused: int
    total_score: float


def set_quality(
    order: Sequence[int], analysed: set[int], scores: Mapping[tuple[int, int], float]
) -> SetQuality:
    """Bilan de cet ordre ; une paire de morceaux analysés absente de `scores` est refusée."""
    refused, total = 0, 0.0
    for a, b in zip(order, order[1:], strict=False):
        if a in analysed and b in analysed:
            if (a, b) in scores:
                total += scores[(a, b)]
            else:
                refused += 1
    return SetQuality(refused, total)


def suggest_cuts(
    durations: Sequence[int],
    analysed: set[int],
    scores: Mapping[tuple[int, int], float],
    target: int,
) -> list[int]:
    """Morceaux à retirer (indices actuels, triés) pour que la somme de `durations` tienne dans `target`.

    Ni le premier ni le dernier : s'il ne reste qu'eux et que ça dépasse encore, on s'arrête.

    `durations[i]` : durée comptée du morceau i (déjà réduite à la part jouée) ; `scores[(a, b)]` : score de
    a -> b quand l'enchaînement est compatible. Liste vide si le set tient déjà.
    """
    order = list(range(len(durations)))
    total = sum(durations)
    removed: list[int] = []
    unknown = sum(scores.values()) / len(scores) if scores else 0.5
    while total > target and len(order) > 2:
        best = min(
            range(1, len(order) - 1), key=lambda k: _damage(order, k, durations, analysed, scores, unknown)
        )
        removed.append(order.pop(best))
        total -= durations[removed[-1]]
    return sorted(removed)


def _damage(
    order: list[int],
    k: int,
    durations: Sequence[int],
    analysed: set[int],
    scores: Mapping[tuple[int, int], float],
    unknown: float,
) -> tuple[int, float, int, int]:
    """Clé de tri du retrait de order[k] : refus en plus, score perdu, le plus long d'abord, puis l'ordre."""
    track = order[k]
    before = order[k - 1] if k > 0 else None
    after = order[k + 1] if k + 1 < len(order) else None

    def edge(a: int | None, b: int | None) -> tuple[int, float]:
        """(refusé ?, score) d'un enchaînement ; (0, `unknown`) s'il est inconnu."""
        if a is None or b is None:
            return 0, 0.0
        if a not in analysed or b not in analysed:
            return 0, unknown
        return (0, scores[(a, b)]) if (a, b) in scores else (1, 0.0)

    lost = [edge(before, track), edge(track, after)]
    gained = edge(before, after)
    refused_delta = gained[0] - sum(r for r, _ in lost)
    score_lost = sum(s for _, s in lost) - gained[1]
    return refused_delta, score_lost, -durations[track], k
