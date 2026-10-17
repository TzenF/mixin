"""Notes des transitions : noter, remplacer, effacer ; ma note dans les playlists et les suggestions."""

import uuid
from collections.abc import Iterator

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from tests.conftest import requires_services

pytestmark = requires_services


@pytest.fixture
def setlist(user_id: uuid.UUID, test_prefix: str) -> Iterator[dict[str, str]]:
    """A (124 BPM, 6A) puis B (125 BPM, 7A, compatible) puis C, dans une playlist à moi."""
    ids = {name: uuid.uuid4() for name in ("a", "b", "c")}
    with psycopg.connect(get_settings().database_url, autocommit=True) as conn:
        for name, bpm, num in (("a", 124, 6), ("b", 125, 7), ("c", 126, 7)):
            conn.execute(
                "INSERT INTO track (id, title) VALUES (%s, %s)", (ids[name], f"{test_prefix} {name}")
            )
            conn.execute(
                """INSERT INTO track_analysis
                       (track_id, source, bpm, camelot_num, camelot_letter, key_confidence)
                   VALUES (%s, 'essentia', %s, %s, 'A', 0.9)""",
                (ids[name], bpm, num),
            )
        row = conn.execute(
            "INSERT INTO playlist (owner_id, name) VALUES (%s, %s) RETURNING id",
            (user_id, f"{test_prefix} Set"),
        ).fetchone()
        assert row is not None
        for position, name in enumerate(("a", "b", "c")):
            conn.execute(
                "INSERT INTO playlist_item (playlist_id, track_id, position) VALUES (%s, %s, %s)",
                (row[0], ids[name], position),
            )
        yield {**{k: str(v) for k, v in ids.items()}, "playlist": str(row[0])}


def _rate(client: TestClient, a: str, b: str, **body: object) -> int:
    """Envoie une note et renvoie le code HTTP."""
    return client.put(f"/transitions/{a}/{b}/rating", json=body).status_code


def _my_ratings(client: TestClient, playlist_id: str) -> list[dict[str, object] | None]:
    """Ma note de chaque enchaînement de la playlist, dans l'ordre."""
    return [i["my_rating"] for i in client.get(f"/playlists/{playlist_id}").json()["items"]]


def test_rate_replace_and_delete(logged_in_client: TestClient, setlist: dict[str, str]) -> None:
    a, b = setlist["a"], setlist["b"]
    resp = logged_in_client.put(f"/transitions/{a}/{b}/rating", json={"rating": 4, "comment": "  tuerie  "})
    assert resp.status_code == 200 and resp.json() == {"rating": 4, "comment": "tuerie"}
    assert _my_ratings(logged_in_client, setlist["playlist"]) == [
        {"rating": 4, "comment": "tuerie"},
        None,
        None,
    ]

    assert _rate(logged_in_client, a, b, rating=2, comment="") == 200  # remplace ; vide = pas de commentaire
    assert _my_ratings(logged_in_client, setlist["playlist"])[0] == {"rating": 2, "comment": None}
    assert logged_in_client.get("/transitions/ratings/count").json()["count"] >= 1

    for _ in range(2):  # deux fois : sans effet la seconde
        assert logged_in_client.delete(f"/transitions/{a}/{b}/rating").status_code == 204
    assert _my_ratings(logged_in_client, setlist["playlist"]) == [None, None, None]


def test_rating_is_directional(logged_in_client: TestClient, setlist: dict[str, str]) -> None:
    a, b = setlist["a"], setlist["b"]
    _rate(logged_in_client, b, a, rating=1)  # B -> A n'est pas A -> B
    assert _my_ratings(logged_in_client, setlist["playlist"])[0] is None


def test_my_rating_in_suggestions(logged_in_client: TestClient, setlist: dict[str, str]) -> None:
    a, b = setlist["a"], setlist["b"]
    _rate(logged_in_client, a, b, rating=5, comment="parfait")
    suggestions = logged_in_client.get(f"/tracks/{a}/suggestions", params={"limit": 100}).json()
    mine = {s["track_id"]: s["my_rating"] for s in suggestions if s["track_id"] in (b, setlist["c"])}

    assert mine == {b: {"rating": 5, "comment": "parfait"}, setlist["c"]: None}


def test_ratings_are_private(logged_in_client: TestClient, setlist: dict[str, str]) -> None:
    other = uuid.uuid4()
    with psycopg.connect(get_settings().database_url, autocommit=True) as conn:
        conn.execute("INSERT INTO app_user (id, display_name) VALUES (%s, 'Autre')", (other,))
        try:
            conn.execute(
                """INSERT INTO transition_rating (user_id, from_track_id, to_track_id, rating)
                   VALUES (%s, %s, %s, 1)""",
                (other, setlist["a"], setlist["b"]),
            )
            assert _my_ratings(logged_in_client, setlist["playlist"])[0] is None  # pas sa note à lui
        finally:
            conn.execute("DELETE FROM app_user WHERE id = %s", (other,))


def test_validation(logged_in_client: TestClient, setlist: dict[str, str]) -> None:
    a, b = setlist["a"], setlist["b"]
    for body in ({"rating": 0}, {"rating": 6}, {"rating": 3, "comment": "x" * 501}, {}):
        assert _rate(logged_in_client, a, b, **body) == 422, body
    assert _rate(logged_in_client, a, a, rating=3) == 422  # un morceau avec lui-même
    assert _rate(logged_in_client, a, str(uuid.uuid4()), rating=3) == 404


def test_ratings_require_a_session(client: TestClient) -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    assert client.put(f"/transitions/{a}/{b}/rating", json={"rating": 3}).status_code == 401
    assert client.delete(f"/transitions/{a}/{b}/rating").status_code == 401
    assert client.get("/transitions/ratings/count").status_code == 401
