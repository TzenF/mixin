import uuid

import psycopg
from fastapi.testclient import TestClient

from app.config import get_settings
from tests.conftest import requires_services


@requires_services
def test_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": True, "queue": True}


@requires_services
def test_tracks_routes_require_a_session(client: TestClient, tracks: dict[str, uuid.UUID]) -> None:
    track_id = tracks["Where Have You Been"]
    assert client.get(f"/tracks/{track_id}/suggestions").status_code == 401
    assert client.post(f"/tracks/{track_id}/analysis").status_code == 401
    assert client.get(f"/tracks/{track_id}").status_code == 401
    assert client.post(f"/tracks/{track_id}/key/flip-mode").status_code == 401


@requires_services
def test_suggestions(logged_in_client: TestClient, tracks: dict[str, uuid.UUID], user_id: uuid.UUID) -> None:
    # Morceaux du test mis en favoris de l'utilisateur (neuf) : avec scope=mine, seuls eux sont candidats,
    # quelle que soit la taille de la base de dev (l'Explorer y ajoute des centaines de morceaux).
    with psycopg.connect(get_settings().database_url, autocommit=True) as conn:
        for track_id in tracks.values():
            conn.execute("INSERT INTO favorite (user_id, track_id) VALUES (%s, %s)", (user_id, track_id))
    resp = logged_in_client.get(
        f"/tracks/{tracks['Where Have You Been']}/suggestions", params={"scope": "mine"}
    )
    assert resp.status_code == 200
    titles = [s["title"] for s in resp.json()]
    # 130.1 en 5A passe devant 129.7 en 4A ; 141.9 BPM (+10.5 %) est hors tolérance
    assert titles == ["Don't Wake Me Up", "Von dutch"]


@requires_services
def test_suggestions_unknown_track(logged_in_client: TestClient) -> None:
    assert logged_in_client.get(f"/tracks/{uuid.uuid4()}/suggestions").status_code == 404


@requires_services
def test_request_analysis_is_deduplicated(logged_in_client: TestClient, tracks: dict[str, uuid.UUID]) -> None:
    url = f"/tracks/{tracks['Von dutch']}/analysis"
    first, second = logged_in_client.post(url), logged_in_client.post(url)
    assert first.status_code == second.status_code == 202
    assert first.json()["job_id"] is not None
    assert second.json()["job_id"] is None  # déjà en file : pas de doublon
