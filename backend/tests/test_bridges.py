"""Morceau pont (fonction SQL bridge_tracks) et route GET /tracks/{a}/bridges/{b}."""

import uuid
from collections.abc import Iterator

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from tests.conftest import requires_services

pytestmark = requires_services


@pytest.fixture
def bridge_tracks(user_id: uuid.UUID, test_prefix: str) -> Iterator[dict[str, uuid.UUID]]:
    """Un enchaînement refusé A -> B, deux ponts (P1 avant P2), un morceau trop loin, un pas à moi."""
    data = {
        "A": (124, 6, "A"),
        "B": (124, 8, "B"),  # A -> B : 2 crans et mineur -> majeur : refusé
        "P1": (124.5, 7, "A"),  # A -> P1 voisine, P1 -> B diagonale : un pont
        "P2": (124, 6, "B"),  # A -> P2 relative, P2 -> B saut de 2 (0.50) : pont plus faible
        "LOIN": (140, 7, "A"),  # bonne tonalité, tempo trop loin des deux côtés
        "AUTRE": (124.5, 7, "A"),  # comme P1, mais pas à moi (ni playlist ni favori)
    }
    ids: dict[str, uuid.UUID] = {}
    with psycopg.connect(get_settings().database_url, autocommit=True) as conn:
        for name, (bpm, num, letter) in data.items():
            tid = uuid.uuid4()
            ids[name] = tid
            conn.execute("INSERT INTO track (id, title) VALUES (%s, %s)", (tid, f"{test_prefix} {name}"))
            conn.execute(
                """INSERT INTO track_analysis
                       (track_id, source, bpm, camelot_num, camelot_letter, key_confidence)
                   VALUES (%s, 'essentia', %s, %s, %s, 0.9)""",
                (tid, bpm, num, letter),
            )
            if name != "AUTRE":
                conn.execute("INSERT INTO favorite (user_id, track_id) VALUES (%s, %s)", (user_id, tid))
        yield ids


def _names(body: list[dict[str, object]], prefix: str) -> list[str]:
    """Titres des ponts du test, sans le préfixe (les autres morceaux de la base sont ignorés)."""
    return [str(b["title"]).removeprefix(f"{prefix} ") for b in body if str(b["title"]).startswith(prefix)]


def test_bridges_between_two_tracks(
    logged_in_client: TestClient, bridge_tracks: dict[str, uuid.UUID], test_prefix: str
) -> None:
    a, b = bridge_tracks["A"], bridge_tracks["B"]
    resp = logged_in_client.get(f"/tracks/{a}/bridges/{b}", params={"limit": 50})
    assert resp.status_code == 200
    body = resp.json()
    assert _names(body, test_prefix) == ["P1", "P2"]  # « mes morceaux » : AUTRE n'y est pas

    p1 = next(x for x in body if x["title"] == f"{test_prefix} P1")
    assert (p1["incoming"]["key_move"], p1["outgoing"]["key_move"]) == ("adjacent", "diagonal")
    assert p1["incoming"]["compatible"] and p1["outgoing"]["compatible"]
    assert (p1["incoming"]["same_mode"], p1["outgoing"]["same_mode"]) == (True, False)
    assert p1["score"] == min(p1["incoming_score"], p1["outgoing_score"])  # le plus faible des deux
    assert p1["mine"] is True

    everything = logged_in_client.get(f"/tracks/{a}/bridges/{b}", params={"scope": "all", "limit": 50}).json()
    assert set(_names(everything, test_prefix)) == {"P1", "P2", "AUTRE"}


def test_bridges_unknown_track(logged_in_client: TestClient, bridge_tracks: dict[str, uuid.UUID]) -> None:
    a = bridge_tracks["A"]
    assert logged_in_client.get(f"/tracks/{a}/bridges/{uuid.uuid4()}").status_code == 404
    assert logged_in_client.get(f"/tracks/{uuid.uuid4()}/bridges/{a}").status_code == 404


def test_bridges_require_a_session(client: TestClient) -> None:
    assert client.get(f"/tracks/{uuid.uuid4()}/bridges/{uuid.uuid4()}").status_code == 401
