"""Authentification Spotify (Authorization Code + PKCE), sans serveur de callback.

On ouvre l'URL d'autorisation dans le navigateur, Spotify redirige vers
http://127.0.0.1:8888/callback (la page ne charge pas, c'est normal),
et on colle l'URL complète de la barre d'adresse dans le terminal.
Le jeton est mis en cache dans data/spotify_token.json et rafraîchi automatiquement.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.parse
from pathlib import Path

import httpx

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
REDIRECT_URI = os.environ.get("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
SCOPES = [
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-private",
    "user-library-read",
]
TOKEN_CACHE = Path("data/spotify_token.json")


def _client_id() -> str:
    client_id = os.environ.get("SPOTIFY_CLIENT_ID")
    if not client_id:
        raise SystemExit("Variable SPOTIFY_CLIENT_ID manquante (voir README).")
    return client_id


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _save(token: dict) -> dict:
    token["expires_at"] = time.time() + token.get("expires_in", 3600) - 60
    TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE.write_text(json.dumps(token, indent=2))
    return token


def _interactive_login() -> dict:
    client_id = _client_id()
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
        "scope": " ".join(SCOPES),
        "state": state,
    }
    print("\n1) Ouvre cette URL dans ton navigateur et accepte :\n")
    print(f"{AUTH_URL}?{urllib.parse.urlencode(params)}\n")
    print("2) Le navigateur arrive sur une page qui ne charge pas (127.0.0.1:8888) : c'est normal.")
    redirected = input("3) Colle ici l'URL complète de la barre d'adresse : ").strip()

    query = urllib.parse.parse_qs(urllib.parse.urlparse(redirected).query)
    if "error" in query:
        raise SystemExit(f"Autorisation refusée : {query['error'][0]}")
    if query.get("state", [None])[0] != state:
        raise SystemExit("Paramètre 'state' invalide : recommence la connexion.")
    code = query["code"][0]

    resp = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": client_id,
            "code_verifier": verifier,
        },
    )
    resp.raise_for_status()
    return _save(resp.json())


def _refresh(token: dict) -> dict:
    resp = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": token["refresh_token"],
            "client_id": _client_id(),
        },
    )
    if resp.status_code != 200:
        return _interactive_login()
    new = resp.json()
    new.setdefault("refresh_token", token["refresh_token"])
    return _save(new)


def get_access_token() -> str:
    if TOKEN_CACHE.exists():
        token = json.loads(TOKEN_CACHE.read_text())
        if time.time() < token.get("expires_at", 0):
            return token["access_token"]
        if "refresh_token" in token:
            return _refresh(token)["access_token"]
    return _interactive_login()["access_token"]
