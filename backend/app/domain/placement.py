"""Trouver où insérer un morceau dans une playlist sans casser d'enchaînement (« Où le placer ? »).

Une place, c'est un trou : avant le 1er morceau (ouverture), entre deux morceaux consécutifs, ou après le
dernier (fin). Pour un trou entre P et S, on regarde P -> morceau (avant) et morceau -> S (après).
Ordre proposé :
  1. les deux passent et P -> S était refusé (le morceau répare un ⚠) ;
  2. les deux passent ;
  3. un seul passe (l'aperçu dit lequel casse).
À catégorie égale, le meilleur enchaînement le plus faible d'abord, comme pour les ponts.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Placement:
    """Une place possible : position d'insertion (0 = en tête), voisins et état des deux enchaînements."""

    position: int
    before: UUID | None  # morceau juste avant (None : ouverture)
    after: UUID | None  # morceau juste après (None : fin)
    before_ok: bool  # before -> morceau passe (vrai en ouverture : rien à enchaîner)
    after_ok: bool  # morceau -> after passe (vrai en fin)
    repairs: bool  # before -> after était refusé et les deux nouveaux passent
    score: float  # le plus faible des scores des enchaînements qui existent


def find_placements(
    order: Sequence[UUID], track: UUID, scores: Mapping[tuple[UUID, UUID], float], limit: int = 5
) -> list[Placement]:
    """Les meilleures places pour `track` dans `order` (au moins un enchaînement qui passe), au plus `limit`.

    `scores[(a, b)]` = score de a -> b quand l'enchaînement est compatible ; absent = refusé.
    """
    places: list[Placement] = []
    for position in range(len(order) + 1):
        before = order[position - 1] if position > 0 else None
        after = order[position] if position < len(order) else None
        if before is None and after is None:
            continue
        sides = []
        if before is not None:
            sides.append(scores.get((before, track)))
        if after is not None:
            sides.append(scores.get((track, after)))
        before_ok = before is None or (before, track) in scores
        after_ok = after is None or (track, after) in scores
        if not (before_ok or after_ok) or all(s is None for s in sides):
            continue
        both = before_ok and after_ok
        repairs = both and before is not None and after is not None and (before, after) not in scores
        known = [s for s in sides if s is not None]
        places.append(Placement(position, before, after, before_ok, after_ok, repairs, min(known)))
    places.sort(key=lambda p: (not p.repairs, not (p.before_ok and p.after_ok), -p.score, p.position))
    return places[:limit]
