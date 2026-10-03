import uuid

from fastapi.testclient import TestClient

from tests.conftest import requires_services


@requires_services
def test_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": True, "queue": True}


@requires_services
def test_suggestions(client: TestClient, tracks: dict[str, uuid.UUID]) -> None:
    resp = client.get(f"/tracks/{tracks['Where Have You Been']}/suggestions")
    assert resp.status_code == 200
    titles = [s["title"] for s in resp.json()]
    # 130.1 en 5A passe devant 129.7 en 4A ; 141.9 BPM (+10.5 %) est hors tolérance
    assert titles[:2] == ["Don't Wake Me Up", "Von dutch"]
    assert "Dernière danse" not in titles


@requires_services
def test_suggestions_unknown_track(client: TestClient) -> None:
    assert client.get(f"/tracks/{uuid.uuid4()}/suggestions").status_code == 404


@requires_services
def test_request_analysis_is_deduplicated(client: TestClient, tracks: dict[str, uuid.UUID]) -> None:
    url = f"/tracks/{tracks['Von dutch']}/analysis"
    first, second = client.post(url), client.post(url)
    assert first.status_code == second.status_code == 202
    assert first.json()["job_id"] is not None
    assert second.json()["job_id"] is None  # déjà en file : pas de doublon
