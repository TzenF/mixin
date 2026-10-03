"""Connexion : sessions, chiffrement des jetons, routes /auth (sans appeler Spotify)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.adapters.db import Database
from app.adapters.token_cipher import TokenCipher, TokenCipherError
from app.adapters.user_repository import UserRepository
from app.config import Settings, get_settings
from app.services.sessions import SessionService
from tests.conftest import requires_services


def test_token_cipher_roundtrip() -> None:
    cipher = TokenCipher(Fernet.generate_key().decode())
    encrypted = cipher.encrypt("jeton-secret")
    assert b"jeton-secret" not in encrypted
    assert cipher.decrypt(encrypted) == "jeton-secret"


def test_token_cipher_rejects_missing_or_foreign_key() -> None:
    with pytest.raises(TokenCipherError):
        TokenCipher("")
    encrypted = TokenCipher(Fernet.generate_key().decode()).encrypt("x")
    with pytest.raises(TokenCipherError):
        TokenCipher(Fernet.generate_key().decode()).decrypt(encrypted)


@requires_services
@pytest.mark.anyio
async def test_session_lifecycle(db: Database, user_id: uuid.UUID) -> None:
    sessions = SessionService(db, days=1)
    token = await sessions.open(user_id)

    assert await sessions.user_id(token) == user_id
    assert await sessions.user_id("jeton-inconnu") is None
    await sessions.close(token)
    assert await sessions.user_id(token) is None


@requires_services
@pytest.mark.anyio
async def test_expired_session_is_rejected(db: Database, user_id: uuid.UUID) -> None:
    token = await SessionService(db, days=-1).open(user_id)

    assert await SessionService(db, days=1).user_id(token) is None


@requires_services
@pytest.mark.anyio
async def test_music_account_upsert_keeps_refresh_token(db: Database, user_id: uuid.UUID) -> None:
    users = UserRepository(db)
    expires = datetime.now(UTC) + timedelta(hours=1)
    puid = f"test-{uuid.uuid4()}"
    await users.save_music_account(user_id, "spotify", puid, b"a1", b"r1", ["s"], expires)
    # Spotify ne renvoie pas toujours de refresh_token : l'ancien doit être conservé
    await users.save_music_account(user_id, "spotify", puid, b"a2", None, ["s"], expires)

    account = await users.get_music_account(user_id, "spotify")
    assert account is not None
    assert (bytes(account.access_token_enc), bytes(account.refresh_token_enc or b"")) == (b"a2", b"r1")
    assert await users.find_by_provider_account("spotify", puid) == user_id


@pytest.fixture
def spotify_client() -> Iterator[TestClient]:
    """Client HTTP de test avec une configuration Spotify factice (aucun appel réel à Spotify)."""
    from app.main import create_app

    settings = Settings(
        **{
            **get_settings().model_dump(),
            "spotify_client_id": "client-de-test",
            "token_encryption_key": Fernet.generate_key().decode(),
        }
    )
    with TestClient(create_app(settings)) as c:
        yield c


@requires_services
def test_me_requires_a_session(spotify_client: TestClient) -> None:
    assert spotify_client.get("/auth/me").status_code == 401
    assert spotify_client.get("/spotify/playlists").status_code == 401


@requires_services
@pytest.mark.anyio
async def test_me_with_a_session(spotify_client: TestClient, db: Database, user_id: uuid.UUID) -> None:
    token = await SessionService(db, days=1).open(user_id)
    spotify_client.cookies.set("session", token)

    resp = spotify_client.get("/auth/me")

    assert resp.status_code == 200
    assert resp.json() == {"id": str(user_id), "display_name": "Test", "spotify_connected": False}


@requires_services
def test_login_redirects_to_spotify_with_pkce(spotify_client: TestClient) -> None:
    resp = spotify_client.get("/auth/spotify/login", follow_redirects=False)

    assert resp.status_code == 302
    url = urlparse(resp.headers["location"])
    query = parse_qs(url.query)
    assert url.netloc == "accounts.spotify.com"
    assert query["code_challenge_method"] == ["S256"]
    assert query["state"] == [resp.cookies["oauth_state"]]


@requires_services
def test_callback_rejects_a_state_from_another_browser(spotify_client: TestClient) -> None:
    spotify_client.get("/auth/spotify/login", follow_redirects=False)

    resp = spotify_client.get("/auth/spotify/callback?code=x&state=pas-le-bon", follow_redirects=False)

    assert resp.status_code == 302
    assert resp.headers["location"] == "/spotify?spotify_error=invalid_state"


@requires_services
def test_callback_when_user_refuses(spotify_client: TestClient) -> None:
    resp = spotify_client.get("/auth/spotify/callback?error=access_denied&state=s", follow_redirects=False)

    assert resp.headers["location"] == "/spotify?spotify_error=access_denied"
