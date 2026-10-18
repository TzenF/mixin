"""Ordre proposé pour une playlist (domaine pur, sans base)."""

import itertools

import pytest

from app.domain.reorder import OrderQuality, best_order, order_quality


def _chain(order: list[int], score: float = 0.9) -> dict[tuple[int, int], float]:
    """Enchaînements compatibles seulement le long de cet ordre (dans ce sens)."""
    return {(a, b): score for a, b in itertools.pairwise(order)}


def test_finds_the_only_chain_including_the_opener() -> None:
    hidden = [3, 0, 4, 1, 2]  # l'ouverture n'est pas le morceau 0
    order = best_order(5, _chain(hidden))
    assert order == hidden
    assert order_quality(order, _chain(hidden)) == OrderQuality(refused=0, total_score=pytest.approx(3.6))


def test_direction_matters() -> None:
    scores = _chain([2, 1, 0])  # 0 -> 1 n'existe pas, 1 -> 0 oui
    assert best_order(3, scores) == [2, 1, 0]


def test_fewer_refusals_beat_better_scores() -> None:
    # 0 -> 1 -> 2 : un seul enchaînement à 1.0 puis un refus ; 1 -> 0 -> 2 : deux enchaînements moyens
    scores = {(0, 1): 1.0, (1, 0): 0.4, (0, 2): 0.4}
    assert order_quality(best_order(3, scores), scores).refused == 0


def test_never_worse_than_the_current_order() -> None:
    scores = {(a, b): 0.5 + 0.01 * ((a * 7 + b * 3) % 11) for a in range(12) for b in range(12) if a != b}
    order = best_order(12, scores)
    assert sorted(order) == list(range(12))
    current, proposed = order_quality(list(range(12)), scores), order_quality(order, scores)
    assert (proposed.refused, -proposed.total_score) <= (current.refused, -current.total_score)


def test_tiny_playlists() -> None:
    assert best_order(0, {}) == []
    assert best_order(1, {}) == [0]
    assert best_order(2, {(1, 0): 0.8}) == [1, 0]
