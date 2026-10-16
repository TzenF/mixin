"""Playlists (lecture) contre la vraie base : liste, détail, enchaînements, accès réservé au propriétaire."""

import uuid
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from tests.conftest import requires_services

pytestmark = requires_services


@pytest.fixture
def playlists(user_id: uuid.UUID, test_prefix: str) -> Iterator[dict[str, str]]:
    """Une playlist à moi (5 morceaux), une importée, et une playlist d'un autre utilisateur."""
    p = test_prefix
    other_user = uuid.uuid4()
    with psycopg.connect(get_settings().database_url, autocommit=True) as conn:

        def track(title: str, bpm: float | None = None, key: tuple[int, str] | None = None) -> uuid.UUID:
            """Crée un morceau, analysé par Essentia si bpm et key sont donnés."""
            tid = uuid.uuid4()
            conn.execute("INSERT INTO track (id, title) VALUES (%s, %s)", (tid, f"{p} {title}"))
            if bpm is not None and key is not None:
                conn.execute(
                    """INSERT INTO track_analysis
                           (track_id, source, bpm, camelot_num, camelot_letter, key_confidence)
                       VALUES (%s, 'essentia', %s, %s, %s, 0.9)""",
                    (tid, bpm, *key),
                )
            return tid

        def playlist(
            owner: uuid.UUID, name: str, tracks: list[uuid.UUID], provider: str | None = None
        ) -> str:
            """Crée une playlist avec ces morceaux, dans l'ordre."""
            row = conn.execute(
                """INSERT INTO playlist (owner_id, name, source_provider, source_external_id)
                   VALUES (%s, %s, %s::music_provider, %s) RETURNING id""",
                (owner, f"{p} {name}", provider, f"{p}-ext" if provider else None),
            ).fetchone()
            assert row is not None
            for position, tid in enumerate(tracks):
                conn.execute(
                    "INSERT INTO playlist_item (playlist_id, track_id, position) VALUES (%s, %s, %s)",
                    (row[0], tid, position),
                )
            return str(row[0])

        a = track("A", 124, (6, "A"))
        b = track("B", 125, (7, "A"))  # A -> B : tonalité voisine, +0,8 %
        c = track("C", 135, (7, "A"))  # B -> C : même tonalité mais +8 % : trop loin
        d = track("D")  # pas analysé
        e = track("E", 124, (12, "A"))
        conn.execute("INSERT INTO app_user (id, display_name) VALUES (%s, 'Autre')", (other_user,))
        ids = {
            "mine": playlist(user_id, "Set", [a, b, c, d, e]),
            "imported": playlist(user_id, "Importée", [a], provider="spotify"),
            "other": playlist(other_user, "Pas à moi", [a]),
        }
        yield ids
        conn.execute("DELETE FROM app_user WHERE id = %s", (other_user,))


def _mine(body: list[dict[str, Any]], prefix: str) -> dict[str, dict[str, Any]]:
    """Playlists du test, par nom sans préfixe."""
    return {p["name"].removeprefix(f"{prefix} "): p for p in body if p["name"].startswith(prefix)}


def test_lists_my_playlists_only(
    logged_in_client: TestClient, playlists: dict[str, str], test_prefix: str
) -> None:
    resp = logged_in_client.get("/playlists")
    assert resp.status_code == 200
    mine = _mine(resp.json(), test_prefix)

    assert set(mine) == {"Set", "Importée"}  # pas celle de l'autre utilisateur
    assert (mine["Set"]["track_count"], mine["Set"]["source_provider"]) == (5, None)
    assert mine["Importée"]["source_provider"] == "spotify"


def test_detail_lists_tracks_in_order_with_transitions(
    logged_in_client: TestClient, playlists: dict[str, str], test_prefix: str
) -> None:
    resp = logged_in_client.get(f"/playlists/{playlists['mine']}")
    assert resp.status_code == 200
    items = resp.json()["items"]

    assert [i["track"]["title"].removeprefix(f"{test_prefix} ") for i in items] == ["A", "B", "C", "D", "E"]
    assert [i["position"] for i in items] == [0, 1, 2, 3, 4]
    a_to_b, b_to_c, c_to_d, d_to_e, last = (i["transition_to_next"] for i in items)

    assert a_to_b is not None
    assert (a_to_b["key_move"], a_to_b["compatible"], a_to_b["bpm_change"]) == ("adjacent", True, 0.8)
    assert a_to_b["same_mode"] is True
    assert b_to_c is not None
    assert (b_to_c["key_move"], b_to_c["tempo_ok"], b_to_c["compatible"], b_to_c["bpm_change"]) == (
        "same",
        False,
        False,
        8.0,
    )
    # D n'est pas analysé : enchaînements inconnus de part et d'autre ; E est le dernier
    assert (c_to_d, d_to_e, last) == (None, None, None)


def test_incompatible_key_explains_the_distance(
    logged_in_client: TestClient, playlists: dict[str, str], test_prefix: str, user_id: uuid.UUID
) -> None:
    with psycopg.connect(get_settings().database_url, autocommit=True) as conn:
        # On retire D : C (7A) est alors suivi de E (12A), à 5 crans sur la roue
        conn.execute(
            """DELETE FROM playlist_item WHERE playlist_id = %s
               AND track_id = (SELECT id FROM track WHERE title = %s)""",
            (playlists["mine"], f"{test_prefix} D"),
        )
    items = logged_in_client.get(f"/playlists/{playlists['mine']}").json()["items"]
    c_to_e = items[2]["transition_to_next"]

    # Même BPM (135 -> 124 : -8,1 %, trop loin aussi) : les deux raisons sont données
    assert (c_to_e["key_move"], c_to_e["key_distance"], c_to_e["tempo_ok"], c_to_e["compatible"]) == (
        None,
        5,
        False,
        False,
    )


def test_someone_elses_playlist_is_not_found(logged_in_client: TestClient, playlists: dict[str, str]) -> None:
    assert logged_in_client.get(f"/playlists/{playlists['other']}").status_code == 404
    assert logged_in_client.get(f"/playlists/{uuid.uuid4()}").status_code == 404


def test_playlists_require_a_session(client: TestClient) -> None:
    assert client.get("/playlists").status_code == 401
    assert client.get(f"/playlists/{uuid.uuid4()}").status_code == 401
