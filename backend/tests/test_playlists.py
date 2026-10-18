"""Playlists contre la vraie base : lecture, enchaînements, modification, accès réservé au propriétaire."""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.adapters.db import Database
from app.config import get_settings
from app.services.playlist_editor import PlaylistEditor
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


def _detail(client: TestClient, playlist_id: str) -> dict[str, Any]:
    """Détail d'une playlist (doit exister)."""
    resp = client.get(f"/playlists/{playlist_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _track_id(prefix: str, title: str) -> str:
    """Identifiant d'un morceau de test."""
    with psycopg.connect(get_settings().database_url) as conn:
        row = conn.execute("SELECT id FROM track WHERE title = %s", (f"{prefix} {title}",)).fetchone()
    assert row is not None
    return str(row[0])


def test_create_and_rename(logged_in_client: TestClient, test_prefix: str, user_id: uuid.UUID) -> None:
    created = logged_in_client.post("/playlists", json={"name": f"  {test_prefix} Nouveau  "})
    assert created.status_code == 201
    playlist = created.json()
    assert (playlist["name"], playlist["track_count"], playlist["source_provider"]) == (
        f"{test_prefix} Nouveau",
        0,
        None,
    )

    renamed = logged_in_client.patch(f"/playlists/{playlist['id']}", json={"name": f"{test_prefix} Samedi"})
    assert renamed.status_code == 200 and renamed.json()["name"] == f"{test_prefix} Samedi"
    assert logged_in_client.post("/playlists", json={"name": "   "}).status_code == 422


def test_add_tracks_at_the_end(
    logged_in_client: TestClient, playlists: dict[str, str], test_prefix: str
) -> None:
    a = _track_id(test_prefix, "A")
    added = logged_in_client.post(f"/playlists/{playlists['mine']}/items", json={"track_id": a})

    assert added.status_code == 201 and added.json()["position"] == 5
    items = _detail(logged_in_client, playlists["mine"])["items"]
    assert [i["track"]["title"].removeprefix(f"{test_prefix} ") for i in items][
        -1
    ] == "A"  # en double : permis
    unknown = logged_in_client.post(
        f"/playlists/{playlists['mine']}/items", json={"track_id": str(uuid.uuid4())}
    )
    assert unknown.status_code == 404


def test_insert_a_track_at_a_position(
    logged_in_client: TestClient, playlists: dict[str, str], test_prefix: str
) -> None:
    url = f"/playlists/{playlists['mine']}/items"
    e = _track_id(test_prefix, "E")

    def titles() -> list[str]:
        """Titres de la playlist, dans l'ordre, sans le préfixe."""
        items = _detail(logged_in_client, playlists["mine"])["items"]
        return [i["track"]["title"].removeprefix(f"{test_prefix} ") for i in items]

    middle = logged_in_client.post(url, json={"track_id": e, "position": 2})
    assert middle.status_code == 201 and middle.json()["position"] == 2
    assert titles() == ["A", "B", "E", "C", "D", "E"]

    assert logged_in_client.post(url, json={"track_id": e, "position": 0}).json()["position"] == 0
    assert logged_in_client.post(url, json={"track_id": e, "position": 99}).json()["position"] == 7
    assert titles() == ["E", "A", "B", "E", "C", "D", "E", "E"]
    assert logged_in_client.post(url, json={"track_id": e, "position": -1}).status_code == 422
    imported = f"/playlists/{playlists['imported']}/items"
    assert logged_in_client.post(imported, json={"track_id": e, "position": 0}).status_code == 409


def test_insert_several_tracks_at_once(
    logged_in_client: TestClient, playlists: dict[str, str], test_prefix: str
) -> None:
    url = f"/playlists/{playlists['mine']}/items/batch"
    a, e = _track_id(test_prefix, "A"), _track_id(test_prefix, "E")

    resp = logged_in_client.post(url, json={"track_ids": [e, a], "position": 1})
    assert resp.status_code == 201
    assert [i["position"] for i in resp.json()] == [1, 2]
    items = _detail(logged_in_client, playlists["mine"])["items"]
    assert [i["track"]["title"].removeprefix(f"{test_prefix} ") for i in items] == [
        "A",
        "E",
        "A",
        "B",
        "C",
        "D",
        "E",
    ]

    unknown = logged_in_client.post(url, json={"track_ids": [a, str(uuid.uuid4())], "position": 0})
    assert unknown.status_code == 404
    assert len(_detail(logged_in_client, playlists["mine"])["items"]) == 7  # tout ou rien
    assert logged_in_client.post(url, json={"track_ids": [], "position": 0}).status_code == 422
    imported = f"/playlists/{playlists['imported']}/items/batch"
    assert logged_in_client.post(imported, json={"track_ids": [a], "position": 0}).status_code == 409


def test_order_proposal(logged_in_client: TestClient, playlists: dict[str, str], test_prefix: str) -> None:
    # Set = A (124, 6A), B (125, 7A), C (135, 7A), D (pas analysé), E (124, 12A)
    resp = logged_in_client.get(f"/playlists/{playlists['mine']}/order/proposal")
    assert resp.status_code == 200
    body = resp.json()
    items = {
        i["item_id"]: i["track"]["title"].removeprefix(f"{test_prefix} ")
        for i in _detail(logged_in_client, playlists["mine"])["items"]
    }
    proposed = [items[i] for i in body["item_ids"]]
    assert sorted(proposed) == ["A", "B", "C", "D", "E"] and proposed[-1] == "D"  # non analysé : en fin
    # A <-> B est le seul enchaînement compatible (dans les deux sens) : ils doivent être voisins
    assert abs(proposed.index("A") - proposed.index("B")) == 1
    assert body["unanalysed"] == 1 and len(body["steps"]) == 3
    assert body["after"]["refused"] <= body["before"]["refused"]
    assert [s["transition"] is None for s in body["steps"]].count(False) == 1  # seul A <-> B passe

    imported = logged_in_client.get(f"/playlists/{playlists['imported']}/order/proposal")
    assert imported.status_code == 409
    assert logged_in_client.get(f"/playlists/{playlists['other']}/order/proposal").status_code == 404
    assert len(_detail(logged_in_client, playlists["mine"])["items"]) == 5  # rien n'a été modifié


def test_catalog_counts_links_with_a_playlist(
    logged_in_client: TestClient, playlists: dict[str, str], test_prefix: str
) -> None:
    # Set = A (124, 6A), B (125, 7A), C (135, 7A), D (pas analysé), E (124, 12A)
    with psycopg.connect(get_settings().database_url, autocommit=True) as conn:
        for title, bpm, num, letter in [("X", 124.5, 6, "B"), ("Y", 100, 1, "A")]:
            tid = uuid.uuid4()
            conn.execute("INSERT INTO track (id, title) VALUES (%s, %s)", (tid, f"{test_prefix} {title}"))
            conn.execute(
                """INSERT INTO track_analysis
                       (track_id, source, bpm, camelot_num, camelot_letter, key_confidence)
                   VALUES (%s, 'essentia', %s, %s, %s, 0.9)""",
                (tid, bpm, num, letter),
            )

    def fits(only: bool) -> dict[str, int | None]:
        """Titres du test (sans préfixe) et leur nombre de liens avec « Set »."""
        params: dict[str, str | bool] = {
            "scope": "all",
            "q": test_prefix,
            "fits": playlists["mine"],
            "limit": 50,
        }
        if only:
            params["fits_only"] = True
        body = logged_in_client.get("/tracks", params=params).json()
        return {i["title"].removeprefix(f"{test_prefix} "): i["fit_count"] for i in body["items"]}

    # X : relative de A et diagonale de B (dans un sens ou dans l'autre) ; Y : rien ; A est déjà dans Set
    assert fits(only=True) == {"X": 2}
    assert fits(only=False)["X"] == 2
    assert fits(only=False)["Y"] is None and fits(only=False)["A"] is None

    other = logged_in_client.get("/tracks", params={"fits": playlists["other"]})
    assert other.status_code == 404
    assert logged_in_client.get("/tracks", params={"fits_only": True}).status_code == 422


def test_imported_playlists_are_read_only(
    logged_in_client: TestClient, playlists: dict[str, str], test_prefix: str
) -> None:
    imported = playlists["imported"]
    a = _track_id(test_prefix, "A")

    assert logged_in_client.post(f"/playlists/{imported}/items", json={"track_id": a}).status_code == 409
    assert logged_in_client.patch(f"/playlists/{imported}", json={"name": "x"}).status_code == 409

    copy = logged_in_client.post(f"/playlists/{imported}/copy")
    assert copy.status_code == 201
    assert (copy.json()["name"], copy.json()["source_provider"]) == (f"{test_prefix} Importée (copie)", None)
    assert len(_detail(logged_in_client, copy.json()["id"])["items"]) == 1
    assert (
        logged_in_client.post(f"/playlists/{copy.json()['id']}/items", json={"track_id": a}).status_code
        == 201
    )


def test_delete(logged_in_client: TestClient, playlists: dict[str, str]) -> None:
    for name in ("mine", "imported"):  # une importée peut être supprimée (puis réimportée)
        assert logged_in_client.delete(f"/playlists/{playlists[name]}").status_code == 204
        assert logged_in_client.get(f"/playlists/{playlists[name]}").status_code == 404


def test_cannot_touch_someone_elses_playlist(
    logged_in_client: TestClient, playlists: dict[str, str], test_prefix: str
) -> None:
    other = playlists["other"]
    a = _track_id(test_prefix, "A")
    assert logged_in_client.post(f"/playlists/{other}/items", json={"track_id": a}).status_code == 404
    assert logged_in_client.patch(f"/playlists/{other}", json={"name": "x"}).status_code == 404
    assert logged_in_client.post(f"/playlists/{other}/copy").status_code == 404
    assert logged_in_client.delete(f"/playlists/{other}").status_code == 404


def test_writes_require_a_session(client: TestClient) -> None:
    some_id = uuid.uuid4()
    assert client.post("/playlists", json={"name": "x"}).status_code == 401
    assert client.patch(f"/playlists/{some_id}", json={"name": "x"}).status_code == 401
    assert client.delete(f"/playlists/{some_id}").status_code == 401
    assert client.post(f"/playlists/{some_id}/items", json={"track_id": str(some_id)}).status_code == 401
    assert client.post(f"/playlists/{some_id}/copy").status_code == 401


@pytest.mark.anyio
async def test_simultaneous_adds_get_distinct_positions(
    db: Database, playlists: dict[str, str], test_prefix: str, user_id: uuid.UUID
) -> None:
    editor = PlaylistEditor(db)
    a = uuid.UUID(_track_id(test_prefix, "A"))
    added = await asyncio.gather(
        *(editor.add_track(user_id, uuid.UUID(playlists["mine"]), a) for _ in range(5))
    )

    assert sorted(position for _, position in added) == [5, 6, 7, 8, 9]


def _titles_and_positions(client: TestClient, playlist_id: str, prefix: str) -> list[tuple[str, int]]:
    """(titre sans préfixe, position) des morceaux de la playlist, dans l'ordre."""
    items = _detail(client, playlist_id)["items"]
    return [(i["track"]["title"].removeprefix(f"{prefix} "), i["position"]) for i in items]


def test_reorder(logged_in_client: TestClient, playlists: dict[str, str], test_prefix: str) -> None:
    mine = playlists["mine"]
    ids = [i["item_id"] for i in _detail(logged_in_client, mine)["items"]]  # A B C D E

    new_order = [ids[4], ids[0], ids[1], ids[2], ids[3]]
    assert logged_in_client.put(f"/playlists/{mine}/order", json={"item_ids": new_order}).status_code == 204
    assert _titles_and_positions(logged_in_client, mine, test_prefix) == [
        ("E", 0),
        ("A", 1),
        ("B", 2),
        ("C", 3),
        ("D", 4),
    ]
    # Les enchaînements suivent le nouvel ordre : E (12A) -> A (6A) est à 6 crans
    first = _detail(logged_in_client, mine)["items"][0]["transition_to_next"]
    assert (first["key_move"], first["key_distance"]) == (None, 6)


def test_reorder_refuses_a_stale_or_foreign_list(
    logged_in_client: TestClient, playlists: dict[str, str]
) -> None:
    mine = playlists["mine"]
    ids = [i["item_id"] for i in _detail(logged_in_client, mine)["items"]]
    other_ids = [i["item_id"] for i in _detail(logged_in_client, playlists["imported"])["items"]]

    for wrong in (ids[:-1], [*ids, ids[0]], [*ids[:-1], other_ids[0]], []):  # manque, doublon, intrus, vide
        assert logged_in_client.put(f"/playlists/{mine}/order", json={"item_ids": wrong}).status_code == 422
    assert [i["item_id"] for i in _detail(logged_in_client, mine)["items"]] == ids  # rien n'a bougé
    assert (
        logged_in_client.put(
            f"/playlists/{playlists['imported']}/order", json={"item_ids": other_ids}
        ).status_code
        == 409
    )


def test_remove_item_compacts_positions(
    logged_in_client: TestClient, playlists: dict[str, str], test_prefix: str
) -> None:
    mine = playlists["mine"]
    ids = [i["item_id"] for i in _detail(logged_in_client, mine)["items"]]

    assert logged_in_client.delete(f"/playlists/{mine}/items/{ids[1]}").status_code == 204  # retire B
    assert _titles_and_positions(logged_in_client, mine, test_prefix) == [
        ("A", 0),
        ("C", 1),
        ("D", 2),
        ("E", 3),
    ]
    assert logged_in_client.delete(f"/playlists/{mine}/items/{ids[1]}").status_code == 404  # déjà retiré
    imported_item = _detail(logged_in_client, playlists["imported"])["items"][0]["item_id"]
    assert logged_in_client.delete(f"/playlists/{mine}/items/{imported_item}").status_code == 404  # pas ici
    assert (
        logged_in_client.delete(f"/playlists/{playlists['imported']}/items/{imported_item}").status_code
        == 409
    )


def test_order_and_removal_require_a_session(client: TestClient) -> None:
    some_id = uuid.uuid4()
    assert client.put(f"/playlists/{some_id}/order", json={"item_ids": []}).status_code == 401
    assert client.delete(f"/playlists/{some_id}/items/1").status_code == 401


def test_detail_shows_favorites(
    logged_in_client: TestClient, playlists: dict[str, str], test_prefix: str
) -> None:
    b = _track_id(test_prefix, "B")
    logged_in_client.put(f"/tracks/{b}/favorite")
    items = _detail(logged_in_client, playlists["mine"])["items"]
    assert [i["track"]["favorite"] for i in items] == [False, True, False, False, False]
