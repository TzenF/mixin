"""Extraits : URL Deezer redemandée à chaque écoute, jamais enregistrée (faux Deezer, vraie base)."""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated

import psycopg
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.adapters.db import Database
from app.adapters.deezer_client import DeezerTrack, DeezerUnavailableError, preview_expiry
from app.adapters.track_repository import TrackRepository
from app.api.deps import get_preview_service, get_track_repository
from app.config import get_settings
from app.services.preview import PreviewService, PreviewUnavailableError
from tests.conftest import requires_services

pytestmark = requires_services

# Forme réelle d'une URL d'extrait (jeton hdnea relevé le 17/10/2026), avec une expiration fixée.
EXPIRES = 1792158000
URL = f"https://cdnt-preview.dzcdn.net/api/1/1/7/a/d/0/7ad.mp3?hdnea=exp={EXPIRES}~acl=/api/1/1/7/a/d/0/7ad.mp3*~hmac=ab"


@dataclass
class FakeDeezer:
    """Faux Deezer : morceaux connus par identifiant et par ISRC ; note les appels."""

    by_id: dict[str, DeezerTrack] = field(default_factory=dict)
    by_isrc: dict[str, DeezerTrack] = field(default_factory=dict)
    down: bool = False
    calls: list[str] = field(default_factory=list)

    async def get_track(self, deezer_id: str) -> DeezerTrack | None:
        """Relit un morceau par identifiant."""
        self.calls.append(f"id:{deezer_id}")
        if self.down:
            raise DeezerUnavailableError("quota")
        return self.by_id.get(deezer_id)

    async def find_by_isrc(self, isrc: str) -> DeezerTrack | None:
        """Cherche un morceau par ISRC."""
        self.calls.append(f"isrc:{isrc}")
        return self.by_isrc.get(isrc)


def test_preview_expiry_is_read_from_the_signed_token() -> None:
    assert preview_expiry(URL) == datetime.fromtimestamp(EXPIRES, UTC)
    assert preview_expiry("https://cdn/extrait.mp3") is None


@pytest.fixture
def tracks(test_prefix: str) -> Iterator[dict[str, uuid.UUID]]:
    """Un morceau analysé (ID Deezer en base), un pas encore analysé (ISRC seul), un sans ISRC."""
    p = test_prefix
    ids = {"analysed": uuid.uuid4(), "pending": uuid.uuid4(), "no_isrc": uuid.uuid4()}
    with psycopg.connect(get_settings().database_url, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO track (id, title, isrc) VALUES (%s, %s, %s)", (ids["analysed"], f"{p} A", f"{p}A")
        )
        conn.execute(
            "INSERT INTO track_external_id (track_id, provider, external_id) VALUES (%s, 'deezer', %s)",
            (ids["analysed"], f"{p}-dz"),
        )
        conn.execute(
            "INSERT INTO track (id, title, isrc) VALUES (%s, %s, %s)", (ids["pending"], f"{p} P", f"{p}P")
        )
        conn.execute("INSERT INTO track (id, title) VALUES (%s, %s)", (ids["no_isrc"], f"{p} N"))
    yield ids


@pytest.mark.anyio
async def test_uses_the_stored_deezer_id(
    db: Database, tracks: dict[str, uuid.UUID], test_prefix: str
) -> None:
    deezer = FakeDeezer(by_id={f"{test_prefix}-dz": DeezerTrack(f"{test_prefix}-dz", URL)})

    preview = await PreviewService(TrackRepository(db), deezer).preview(tracks["analysed"])

    assert (preview.url, preview.expires_at) == (URL, datetime.fromtimestamp(EXPIRES, UTC))
    assert deezer.calls == [f"id:{test_prefix}-dz"]  # pas de recherche par ISRC


@pytest.mark.anyio
async def test_not_yet_analysed_track_is_found_by_isrc_without_writing_anything(
    db: Database, tracks: dict[str, uuid.UUID], test_prefix: str
) -> None:
    deezer = FakeDeezer(by_isrc={f"{test_prefix}P": DeezerTrack("123", URL)})

    assert (await PreviewService(TrackRepository(db), deezer).preview(tracks["pending"])).url == URL

    assert (
        await TrackRepository(db).find_external_id(tracks["pending"], "deezer") is None
    )  # le worker le fera


@pytest.mark.anyio
async def test_reasons_when_there_is_no_preview(
    db: Database, tracks: dict[str, uuid.UUID], test_prefix: str
) -> None:
    async def reason(deezer: FakeDeezer, track: str) -> str:
        """Raison du refus pour ce morceau."""
        with pytest.raises(PreviewUnavailableError) as exc:
            await PreviewService(TrackRepository(db), deezer).preview(tracks[track])
        return exc.value.reason

    dz = f"{test_prefix}-dz"
    assert await reason(FakeDeezer(), "no_isrc") == "no_isrc"
    assert await reason(FakeDeezer(), "analysed") == "unknown_on_deezer"  # retiré du catalogue Deezer
    assert await reason(FakeDeezer(by_id={dz: DeezerTrack(dz, None)}), "analysed") == "no_preview"
    assert (
        await reason(FakeDeezer(by_id={dz: DeezerTrack(dz, "http://cdn/x.mp3")}), "analysed") == "no_preview"
    )


def _with_fake_deezer(client: TestClient, deezer: FakeDeezer) -> None:
    """Remplace Deezer par un faux dans l'application de test (le dépôt reste le vrai)."""

    def service(tracks: Annotated[TrackRepository, Depends(get_track_repository)]) -> PreviewService:
        """Service d'extrait branché sur le faux Deezer."""
        return PreviewService(tracks, deezer)

    client.app.dependency_overrides[get_preview_service] = service


def test_route_returns_a_fresh_url_never_cached(
    logged_in_client: TestClient, tracks: dict[str, uuid.UUID], test_prefix: str
) -> None:
    dz = f"{test_prefix}-dz"
    _with_fake_deezer(logged_in_client, FakeDeezer(by_id={dz: DeezerTrack(dz, URL)}))

    resp = logged_in_client.get(f"/tracks/{tracks['analysed']}/preview")

    assert resp.status_code == 200
    assert resp.json()["url"] == URL
    assert resp.json()["expires_at"].startswith("2026-")
    assert resp.headers["cache-control"] == "no-store"


def test_route_errors(logged_in_client: TestClient, tracks: dict[str, uuid.UUID]) -> None:
    _with_fake_deezer(logged_in_client, FakeDeezer())
    missing = logged_in_client.get(f"/tracks/{tracks['no_isrc']}/preview")
    assert (missing.status_code, missing.json()["reason"]) == (404, "no_isrc")
    assert logged_in_client.get(f"/tracks/{uuid.uuid4()}/preview").status_code == 404

    _with_fake_deezer(logged_in_client, FakeDeezer(down=True))
    down = logged_in_client.get(f"/tracks/{tracks['analysed']}/preview")
    assert down.status_code == 503 and "quota" not in down.text  # aucun détail de Deezer renvoyé


def test_preview_requires_a_session(client: TestClient) -> None:
    assert client.get(f"/tracks/{uuid.uuid4()}/preview").status_code == 401
