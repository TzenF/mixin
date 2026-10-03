"""Connexion à Spotify : OAuth Authorization Code + PKCE (sans secret client).

Repris du spike 01 (spikes/01-spotify-reccobeats/spotify_auth.py), testé contre la vraie API.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.adapters.http_retry import request_with_retry
from app.domain.music_provider import MusicProviderError

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
SCOPES = [
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-private",
    "user-library-read",
]
# Marge de sécurité : un jeton qui expire dans moins d'une minute est considéré comme expiré.
EXPIRY_MARGIN = timedelta(seconds=60)


class SpotifyAuthError(MusicProviderError):
    """Spotify a refusé l'échange ou le rafraîchissement du jeton : il faut se reconnecter."""


@dataclass(frozen=True, slots=True)
class SpotifyTokens:
    """Jetons renvoyés par Spotify, avec leur date d'expiration calculée."""

    access_token: str
    refresh_token: str | None
    expires_at: datetime
    scopes: list[str]


def pkce_pair() -> tuple[str, str]:
    """Génère un code_verifier PKCE et son code_challenge (S256)."""
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


class SpotifyAuth:
    """Construit l'URL d'autorisation Spotify et échange ou rafraîchit les jetons."""

    def __init__(self, client: httpx.AsyncClient, client_id: str, redirect_uri: str) -> None:
        if not client_id:
            raise SpotifyAuthError("SPOTIFY_CLIENT_ID manquant (voir .env.example)")
        self._client = client
        self._client_id = client_id
        self._redirect_uri = redirect_uri

    def authorize_url(self, state: str, code_challenge: str) -> str:
        """URL vers laquelle rediriger le navigateur pour que l'utilisateur autorise l'application."""
        params = {
            "client_id": self._client_id,
            "response_type": "code",
            "redirect_uri": self._redirect_uri,
            "code_challenge_method": "S256",
            "code_challenge": code_challenge,
            "scope": " ".join(SCOPES),
            "state": state,
        }
        return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    async def exchange_code(self, code: str, verifier: str) -> SpotifyTokens:
        """Échange le code reçu au retour de Spotify contre des jetons."""
        data = await self._post_token(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._redirect_uri,
                "client_id": self._client_id,
                "code_verifier": verifier,
            }
        )
        return _tokens(data, previous_refresh_token=None)

    async def refresh(self, refresh_token: str) -> SpotifyTokens:
        """Obtient un nouveau jeton d'accès ; Spotify peut aussi renvoyer un nouveau refresh_token."""
        data = await self._post_token(
            {"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": self._client_id}
        )
        return _tokens(data, previous_refresh_token=refresh_token)

    async def _post_token(self, form: dict[str, str]) -> dict[str, Any]:
        """Appelle l'endpoint de jetons et renvoie sa réponse JSON."""
        try:
            resp = await request_with_retry(self._client, "POST", TOKEN_URL, data=form)
        except httpx.HTTPError as e:
            raise SpotifyAuthError(f"Spotify injoignable : {e}") from e
        if resp.status_code != 200:
            raise SpotifyAuthError(f"Spotify a refusé le jeton (HTTP {resp.status_code}) : {resp.text[:200]}")
        return resp.json()


def _tokens(data: dict[str, Any], previous_refresh_token: str | None) -> SpotifyTokens:
    """Convertit la réponse de Spotify en SpotifyTokens."""
    return SpotifyTokens(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token") or previous_refresh_token,
        expires_at=datetime.now(UTC) + timedelta(seconds=int(data.get("expires_in", 3600))),
        scopes=str(data.get("scope", "")).split(),
    )
