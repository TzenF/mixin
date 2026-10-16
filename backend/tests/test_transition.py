"""Fonction SQL transition : la règle d'enchaînement partagée par les suggestions et les playlists."""

from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row

from app.config import get_settings
from tests.conftest import requires_services

pytestmark = requires_services


@pytest.fixture(scope="module")
def conn() -> Iterator[psycopg.Connection[dict[str, Any]]]:
    """Connexion à la base, partagée par les tests du module (lecture seule)."""
    with psycopg.connect(get_settings().database_url, row_factory=dict_row) as c:
        yield c


def _transition(
    conn: psycopg.Connection[dict[str, Any]], a: tuple[Any, ...], b: tuple[Any, ...], tolerance: float = 0.06
) -> dict[str, Any] | None:
    """Enchaînement de a=(bpm, numéro, lettre) vers b ; None si la fonction ne renvoie rien."""
    return conn.execute(
        """SELECT * FROM transition(%s::numeric, %s::smallint, %s,
                                    %s::numeric, %s::smallint, %s, %s::numeric)""",
        (*a, *b, tolerance),
    ).fetchone()


def test_adjacent_key_with_signed_bpm_change(conn: psycopg.Connection[dict[str, Any]]) -> None:
    t = _transition(conn, (124, 6, "A"), (125, 7, "A"))
    assert t is not None
    assert (t["key_move"], t["key_distance"], t["half_double"], t["compatible"]) == (
        "adjacent",
        1,
        False,
        True,
    )
    assert t["bpm_change"] == Decimal("0.8")

    down = _transition(conn, (125, 7, "A"), (124, 6, "A"))
    assert down is not None and down["bpm_change"] == Decimal("-0.8")  # on ralentit


def test_relative_and_wheel_wraps_around(conn: psycopg.Connection[dict[str, Any]]) -> None:
    relative = _transition(conn, (124, 6, "A"), (124, 6, "B"))
    assert relative is not None and relative["key_move"] == "relative"

    across_12 = _transition(conn, (124, 12, "A"), (124, 1, "A"))  # 12A -> 1A : voisins sur la roue
    assert across_12 is not None and (across_12["key_move"], across_12["key_distance"]) == ("adjacent", 1)


def test_diagonal_is_accepted(conn: psycopg.Connection[dict[str, Any]]) -> None:
    # ±1 cran ET changement de mode (migration 004) : une seule note de la gamme change
    for a, b in [((6, "B"), (7, "A")), ((6, "A"), (7, "B")), ((6, "A"), (5, "B")), ((6, "B"), (5, "A"))]:
        t = _transition(conn, (124, *a), (124, *b))
        assert t is not None and (t["key_move"], t["compatible"]) == ("diagonal", True), (a, b)


def test_two_steps_and_mode_change_is_refused(conn: psycopg.Connection[dict[str, Any]]) -> None:
    t = _transition(conn, (124, 6, "B"), (124, 8, "A"))
    assert t is not None and (t["key_move"], t["key_distance"], t["compatible"]) == (None, 2, False)


def test_incompatible_key_explains_why(conn: psycopg.Connection[dict[str, Any]]) -> None:
    t = _transition(conn, (124, 6, "A"), (124, 11, "A"))
    assert t is not None
    assert (t["key_move"], t["key_distance"], t["compatible"]) == (None, 5, False)


def test_tempo_too_far_is_incompatible(conn: psycopg.Connection[dict[str, Any]]) -> None:
    t = _transition(conn, (124, 6, "A"), (135, 6, "A"))
    assert t is not None
    assert (t["key_move"], t["compatible"]) == ("same", False)
    assert t["bpm_change"] == Decimal("8.9")


def test_half_double_tempo(conn: psycopg.Connection[dict[str, Any]]) -> None:
    t = _transition(conn, (128, 8, "A"), (64, 8, "A"))
    assert t is not None
    assert (t["half_double"], t["bpm_diff"], t["compatible"]) == (True, 0, True)
    assert t["bpm_change"] == Decimal("-50.0")


def test_missing_value_gives_no_result(conn: psycopg.Connection[dict[str, Any]]) -> None:
    assert _transition(conn, (None, 6, "A"), (124, 6, "A")) is None
    assert _transition(conn, (124, 6, "A"), (124, None, None)) is None
