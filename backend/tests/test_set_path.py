"""Recherche de chemin dans le graphe des enchaînements (domaine pur, sans base)."""

import uuid

from app.domain.set_path import SetPath, find_paths

A, B, C, D, E, F, G = (uuid.UUID(int=n) for n in range(1, 8))


def test_shortest_path_wins_over_a_better_but_longer_one() -> None:
    graph = {
        A: [(C, 0.6), (D, 0.95)],
        C: [(B, 0.6)],  # A -> C -> B : 1 morceau, maillon faible 0.6
        D: [(E, 0.95)],
        E: [(B, 0.95)],  # A -> D -> E -> B : meilleur mais plus long
    }
    assert find_paths(graph, A, B, count=1) == [SetPath((A, C, B), 0.6)]


def test_same_length_keeps_the_best_weakest_link() -> None:
    graph = {
        A: [(C, 1.0), (D, 0.8)],
        C: [(E, 0.5)],  # A -> C -> E -> B : maillon faible 0.5 (somme plus grande)
        D: [(F, 0.8)],  # A -> D -> F -> B : maillon faible 0.8
        E: [(B, 1.0)],
        F: [(B, 0.8)],
    }
    assert find_paths(graph, A, B, count=1) == [SetPath((A, D, F, B), 0.8)]


def test_alternatives_share_no_track_and_the_direct_link_is_not_a_path() -> None:
    graph = {
        A: [(B, 1.0), (C, 0.9), (D, 0.7)],  # A -> B direct : ignoré
        C: [(B, 0.9), (E, 0.9)],
        D: [(B, 0.7)],
        E: [(B, 0.9)],
    }
    assert find_paths(graph, A, B) == [SetPath((A, C, B), 0.9), SetPath((A, D, B), 0.7)]


def test_never_goes_through_a_track_twice_nor_beyond_the_limit() -> None:
    # A -> C -> D -> C -> B reviendrait sur C ; A -> C -> D -> E -> F -> G -> B a 5 intermédiaires
    graph = {
        A: [(C, 1.0)],
        C: [(D, 1.0)],
        D: [(C, 1.0), (E, 1.0)],
        E: [(F, 1.0)],
        F: [(G, 1.0)],
        G: [(B, 1.0)],
    }
    assert find_paths(graph, A, B, max_intermediates=4) == []
    assert find_paths(graph, A, B, max_intermediates=5) == [SetPath((A, C, D, E, F, G, B), 1.0)]


def test_no_path() -> None:
    assert find_paths({A: [(C, 1.0)]}, A, B) == []
