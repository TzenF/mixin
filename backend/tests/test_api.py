import uuid

from fastapi.testclient import TestClient

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
def test_suggestions(logged_in_client: TestClient, tracks: dict[str, uuid.UUID]) -> None:
    # scope=all : ces morceaux ne sont dans aucune playlist de l'utilisateur
    resp = logged_in_client.get(
        f"/tracks/{tracks['Where Have You Been']}/suggestions", params={"scope": "all"}
    )
    assert resp.status_code == 200
    # La base de dev contient d'autres morceaux analysés : on ne regarde que ceux du test.
    mine = {str(t) for t in tracks.values()}
    titles = [s["title"] for s in resp.json() if s["track_id"] in mine]
    # 130.1 en 5A passe devant 129.7 en 4A ; 141.9 BPM (+10.5 %) est hors tolérance
    assert titles[:2] == ["Don't Wake Me Up", "Von dutch"]
    assert "Dernière danse" not in titles


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
