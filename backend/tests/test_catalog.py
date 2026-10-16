"""Catalogue (GET /tracks) contre la vraie base.

La base de dev contient de vrais morceaux : chaque requête filtre sur le préfixe du test (`q`).
"""

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
def catalog(user_id: uuid.UUID, test_prefix: str) -> Iterator[str]:
    """Quatre morceaux : trois dans une playlist de l'utilisateur, un en dehors (Gamma)."""
    p = test_prefix
    with psycopg.connect(get_settings().database_url, autocommit=True) as conn:

        def track(title: str, status: str = "done") -> uuid.UUID:
            """Crée un morceau et renvoie son identifiant."""
            tid = uuid.uuid4()
            conn.execute(
                "INSERT INTO track (id, title, analysis_status) VALUES (%s, %s, %s::analysis_status)",
                (tid, f"{p} {title}", status),
            )
            return tid

        def essentia(tid: uuid.UUID, bpm: float, num: int, letter: str) -> None:
            """Ajoute la valeur Essentia du morceau."""
            conn.execute(
                """INSERT INTO track_analysis
                       (track_id, source, bpm, camelot_num, camelot_letter, key_confidence)
                   VALUES (%s, 'essentia', %s, %s, %s, 0.9)""",
                (tid, bpm, num, letter),
            )

        alpha, beta, gamma, delta = track("Alpha"), track("Beta"), track("Gamma"), track("Delta_x", "pending")
        essentia(alpha, 124.0, 6, "A")
        essentia(beta, 128.0, 8, "A")
        essentia(gamma, 126.0, 6, "A")
        # Correction perso : Beta passe de 8A à 8B pour cet utilisateur
        conn.execute(
            """INSERT INTO track_analysis (track_id, source, user_id, created_by, camelot_num, camelot_letter)
               VALUES (%s, 'manual', %s, %s, 8, 'B')""",
            (beta, user_id, user_id),
        )
        artist = conn.execute(
            "INSERT INTO artist (name) VALUES (%s) RETURNING id", (f"{p} Artiste",)
        ).fetchone()
        assert artist is not None
        conn.execute(
            "INSERT INTO track_artist (track_id, artist_id, position) VALUES (%s, %s, 0)", (alpha, artist[0])
        )

        playlist = conn.execute(
            "INSERT INTO playlist (owner_id, name) VALUES (%s, 'test') RETURNING id", (user_id,)
        ).fetchone()
        assert playlist is not None
        for position, tid in enumerate((alpha, beta, delta)):
            conn.execute(
                "INSERT INTO playlist_item (playlist_id, track_id, position) VALUES (%s, %s, %s)",
                (playlist[0], tid, position),
            )
    yield p


def _get(client: TestClient, prefix: str, **params: Any) -> dict[str, Any]:
    """Appelle le catalogue limité aux morceaux du test et renvoie le JSON."""
    resp = client.get("/tracks", params={"q": prefix, **params})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _titles(body: dict[str, Any], prefix: str) -> list[str]:
    """Titres de la page, sans le préfixe du test."""
    return [item["title"].removeprefix(f"{prefix} ") for item in body["items"]]


def test_mine_by_default_and_all_on_demand(logged_in_client: TestClient, catalog: str) -> None:
    mine = _get(logged_in_client, catalog)
    assert _titles(mine, catalog) == ["Alpha", "Beta", "Delta_x"]
    assert mine["total"] == 3

    everything = _get(logged_in_client, catalog, scope="all")
    assert _titles(everything, catalog) == ["Alpha", "Beta", "Delta_x", "Gamma"]


def test_items_show_effective_values(logged_in_client: TestClient, catalog: str) -> None:
    items = {i["title"].removeprefix(f"{catalog} "): i for i in _get(logged_in_client, catalog)["items"]}

    assert items["Alpha"]["artists"] == [f"{catalog} Artiste"]
    assert (items["Alpha"]["bpm"], items["Alpha"]["camelot"]) == (124.0, "6A")
    # La correction perso passe devant Essentia pour la tonalité ; le BPM reste celui d'Essentia
    assert (items["Beta"]["camelot"], items["Beta"]["key_source"]) == ("8B", "manual")
    assert (items["Beta"]["bpm"], items["Beta"]["bpm_source"]) == (128.0, "essentia")
    assert (items["Delta_x"]["bpm"], items["Delta_x"]["camelot"]) == (None, None)
    assert items["Delta_x"]["analysis_status"] == "pending"


def test_filters(logged_in_client: TestClient, catalog: str) -> None:
    def titles(**params: Any) -> list[str]:
        """Titres renvoyés pour ces filtres, sur tous les morceaux du test."""
        return _titles(_get(logged_in_client, catalog, scope="all", **params), catalog)

    assert titles(bpm_min=125) == ["Beta", "Gamma"]
    assert titles(bpm_max=125) == ["Alpha"]
    assert titles(key="6A") == ["Alpha", "Gamma"]
    assert titles(key="Am") == []  # Am = 8A : Beta est 8B une fois corrigé
    assert titles(key="8b") == ["Beta"]
    assert titles(status="pending") == ["Delta_x"]


def test_text_search_matches_artists_and_takes_wildcards_literally(
    logged_in_client: TestClient, catalog: str
) -> None:
    by_artist = logged_in_client.get("/tracks", params={"q": f"{catalog} Artiste"}).json()
    assert _titles(by_artist, catalog) == ["Alpha"]

    assert _get(logged_in_client, f"{catalog} Delta_x")["total"] == 1
    assert _get(logged_in_client, f"{catalog} Delta%")["total"] == 0  # % n'est pas un joker
    assert _get(logged_in_client, f"{catalog} Delt_")["total"] == 0  # _ non plus


def test_sort_and_pagination(logged_in_client: TestClient, catalog: str) -> None:
    by_bpm = _get(logged_in_client, catalog, scope="all", sort="bpm")
    assert _titles(by_bpm, catalog) == ["Alpha", "Gamma", "Beta", "Delta_x"]  # sans BPM : en dernier

    by_key = _get(logged_in_client, catalog, scope="all", sort="key")
    assert _titles(by_key, catalog) == ["Alpha", "Gamma", "Beta", "Delta_x"]  # 6A, 6A, 8B, aucune

    page = _get(logged_in_client, catalog, limit=2, offset=2)
    assert (_titles(page, catalog), page["total"]) == (["Delta_x"], 3)
    past_the_end = _get(logged_in_client, catalog, offset=10)
    assert (past_the_end["items"], past_the_end["total"]) == ([], 3)


def test_invalid_parameters(logged_in_client: TestClient) -> None:
    assert logged_in_client.get("/tracks", params={"key": "13Z"}).status_code == 422
    assert logged_in_client.get("/tracks", params={"sort": "id; DROP TABLE track"}).status_code == 422
    assert logged_in_client.get("/tracks", params={"limit": 1000}).status_code == 422


def test_catalog_requires_a_session(client: TestClient) -> None:
    assert client.get("/tracks").status_code == 401


def _row(client: TestClient, prefix: str, title: str) -> dict[str, Any]:
    """Ligne du catalogue pour ce morceau de test."""
    items = _get(client, f"{prefix} {title}", scope="all")["items"]
    assert len(items) == 1
    return items[0]


def test_flip_mode_keeps_the_tonic_and_is_reversible(logged_in_client: TestClient, catalog: str) -> None:
    alpha = _row(logged_in_client, catalog, "Alpha")
    url = f"/tracks/{alpha['id']}/key/flip-mode"

    flipped = logged_in_client.post(url)
    assert flipped.status_code == 200
    assert flipped.json() == {"camelot": "9B", "key_source": "manual"}  # 6A (sol mineur) -> 9B (sol majeur)
    row = _row(logged_in_client, catalog, "Alpha")
    assert (row["camelot"], row["key_source"], row["bpm"]) == ("9B", "manual", 124.0)  # BPM inchangé

    assert logged_in_client.post(url).json()["camelot"] == "6A"


def test_flip_mode_never_touches_essentia_or_other_users(
    logged_in_client: TestClient, catalog: str, user_id: uuid.UUID
) -> None:
    beta = _row(logged_in_client, catalog, "Beta")  # 8B : déjà corrigé une fois par l'utilisateur
    assert logged_in_client.post(f"/tracks/{beta['id']}/key/flip-mode").json()["camelot"] == "5A"

    with psycopg.connect(get_settings().database_url) as conn:
        rows = conn.execute(
            """SELECT source::text, user_id, camelot_num || camelot_letter
               FROM track_analysis WHERE track_id = %s ORDER BY 1""",
            (beta["id"],),
        ).fetchall()
    # Une seule correction (mise à jour, pas ajoutée), personnelle ; la valeur Essentia reste 8A
    assert rows == [("essentia", None, "8A"), ("manual", user_id, "5A")]


def test_flip_mode_errors(logged_in_client: TestClient, client: TestClient, catalog: str) -> None:
    delta = _row(logged_in_client, catalog, "Delta_x")
    assert logged_in_client.post(f"/tracks/{delta['id']}/key/flip-mode").status_code == 409
    assert logged_in_client.post(f"/tracks/{uuid.uuid4()}/key/flip-mode").status_code == 404
