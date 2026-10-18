"""« Tenir le créneau » : quels morceaux retirer (domaine pur, sans base)."""

from app.domain.set_cut import SetQuality, set_quality, suggest_cuts


def test_nothing_to_cut_when_it_fits() -> None:
    assert suggest_cuts([100, 100], {0, 1}, {(0, 1): 0.9}, target=200) == []


def test_removing_a_track_that_repairs_a_refused_transition_comes_first() -> None:
    # 0 -> 1 passe, 1 -> 2 refusé, 0 -> 2 passe, 2 -> 3 passe : retirer 1 répare, même s'il est le plus court
    scores = {(0, 1): 0.9, (0, 2): 0.8, (2, 3): 0.9}
    assert suggest_cuts([300, 100, 300, 300], {0, 1, 2, 3}, scores, target=950) == [1]


def test_the_opener_and_the_last_track_are_never_removed() -> None:
    # Retirer 2 (en fin) supprimerait le refus 1 -> 2 et rendrait plus de temps, mais c'est le dernier morceau
    scores = {(0, 1): 0.9, (0, 2): 0.8}
    assert suggest_cuts([300, 100, 300], {0, 1, 2}, scores, target=650) == [1]
    assert suggest_cuts([300, 300], {0, 1}, {(0, 1): 0.9}, target=100) == []  # que des bouts : on s'arrête


def test_then_what_breaks_nothing_and_the_longest_first() -> None:
    # Tout passe et retirer 1 ou 2 coûte pareil (0 -> 2 et 1 -> 3 valent ce qu'on perd) : le plus long part
    scores = {(0, 1): 0.9, (1, 2): 0.9, (2, 3): 0.9, (0, 2): 0.9, (1, 3): 0.9}
    assert suggest_cuts([200, 200, 300, 200], {0, 1, 2, 3}, scores, target=650) == [2]


def test_unanalysed_tracks_are_not_cut_first() -> None:
    # 2 n'est pas analysé : ses enchaînements comptent comme moyens (0,9 ici) ; retirer 1 ou 2 coûte pareil
    scores = {(0, 1): 0.9, (1, 3): 0.9, (0, 3): 0.9}
    assert suggest_cuts([200, 200, 200, 200], {0, 1, 3}, scores, target=600) == [1]


def test_quality_ignores_unknown_transitions() -> None:
    assert set_quality([0, 1, 2], {0, 2}, {}) == SetQuality(refused=0, total_score=0.0)
    assert set_quality([0, 2], {0, 2}, {}) == SetQuality(refused=1, total_score=0.0)
