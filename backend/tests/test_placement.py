"""« Où le placer ? » : places proposées pour un morceau dans une playlist (domaine pur, sans base)."""

import uuid

from app.domain.placement import find_placements

A, B, C, X = (uuid.UUID(int=n) for n in range(1, 5))


def test_a_spot_that_repairs_a_refused_transition_comes_first() -> None:
    # A -> B passe, B -> C est refusé ; X passe des deux côtés entre A et B, et entre B et C (réparation)
    scores = {(A, B): 0.9, (A, X): 0.95, (X, B): 0.95, (B, X): 0.6, (X, C): 0.6}
    places = find_placements([A, B, C], X, scores)

    assert [(p.position, p.repairs, p.before_ok, p.after_ok) for p in places] == [
        (2, True, True, True),  # répare B -> C, même avec de moins bons scores
        (1, False, True, True),
    ]
    assert places[0].score == 0.6


def test_one_sided_spots_come_last_and_ends_count_one_side() -> None:
    scores = {(X, A): 0.8, (B, X): 0.7, (A, B): 0.9}  # X peut ouvrir, ou suivre B (mais pas précéder C)
    places = find_placements([A, B, C], X, scores)

    assert [(p.position, p.before, p.after, p.before_ok, p.after_ok) for p in places] == [
        (0, None, A, True, True),  # ouverture : seul X -> A compte
        (2, B, C, True, False),  # un seul côté passe
    ]


def test_no_spot_and_limit() -> None:
    assert find_placements([A, B], X, {(A, B): 0.9}) == []
    everywhere = {(a, X): 0.8 for a in (A, B, C)} | {(X, b): 0.8 for b in (A, B, C)}
    assert len(find_placements([A, B, C], X, everywhere, limit=2)) == 2
