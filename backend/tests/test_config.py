"""Garde-fous de la configuration en production."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings

PROD_OK = {
    "environment": "production",
    "session_cookie_secure": True,
    "token_encryption_key": "une-cle",
    "spotify_redirect_uri": "https://mixin.example/api/auth/spotify/callback",
    "database_url": "postgresql://dj:motdepasse-fort@db:5432/dj",
}


def _settings(**overrides: object) -> Settings:
    """Réglages construits sans lire le fichier .env (les valeurs données priment sur l'environnement)."""
    return Settings(_env_file=None, **{**PROD_OK, **overrides})  # type: ignore[arg-type]


def test_production_with_proper_settings_starts() -> None:
    assert _settings().is_production


def test_production_refuses_every_dev_setting_at_once() -> None:
    with pytest.raises(ValidationError) as exc:
        _settings(
            session_cookie_secure=False,
            token_encryption_key="",
            spotify_redirect_uri="http://127.0.0.1:4200/api/auth/spotify/callback",
            database_url="postgresql://dj:dj@db:5432/dj",
        )
    message = str(exc.value)
    for name in ("SESSION_COOKIE_SECURE", "TOKEN_ENCRYPTION_KEY", "SPOTIFY_REDIRECT_URI", "DATABASE_URL"):
        assert name in message


def test_development_accepts_dev_settings() -> None:
    assert not _settings(environment="development", session_cookie_secure=False).is_production


def test_api_docs_are_hidden_in_production() -> None:
    from app.main import create_app

    # Pas de `with` : on ne démarre pas l'application (ni base ni Redis), seules les routes comptent.
    client = TestClient(create_app(_settings()))
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_errors_do_not_leak_secret_values() -> None:
    with pytest.raises(ValidationError) as exc:
        _settings(session_cookie_secure=False, database_url="postgresql://dj:dj@secret-host:5432/dj")
    assert "secret-host" not in str(exc.value)
