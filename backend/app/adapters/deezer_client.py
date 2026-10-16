"""Deezer, utilisé en coulisses : retrouve un morceau par ISRC et télécharge son extrait de 30 s.

API publique, sans compte utilisateur. Vérifié en octobre 2026 : `GET /track/isrc:<ISRC>` renvoie `id` et
`preview` (URL signée qui expire : on la télécharge aussitôt, on ne la stocke jamais). Les erreurs arrivent
en HTTP 200 avec un objet `error` ; le code 800 (« no data ») veut dire « ISRC inconnu ».
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx

from app.adapters.http_retry import request_with_retry

DEEZER_API = "https://api.deezer.com"
_NO_DATA = 800


class DeezerUnavailableError(Exception):
    """Deezer ne répond pas correctement pour l'instant (quota, panne, réseau) : réessayer plus tard."""


@dataclass(frozen=True, slots=True)
class DeezerTrack:
    """Morceau Deezer trouvé par ISRC : son identifiant et l'URL de son extrait (None s'il n'en a pas)."""

    deezer_id: str
    preview_url: str | None


class DeezerClient:
    """Accès à l'API publique de Deezer."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def find_by_isrc(self, isrc: str) -> DeezerTrack | None:
        """Cherche le morceau par ISRC ; None si Deezer ne le connaît pas."""
        data = (await self._get(f"{DEEZER_API}/track/isrc:{isrc}")).json()
        if error := data.get("error"):
            if error.get("code") == _NO_DATA:
                return None
            raise DeezerUnavailableError(f"Deezer : {error.get('message', 'erreur inconnue')}")
        if not data.get("id"):
            return None
        return DeezerTrack(str(data["id"]), data.get("preview") or None)

    async def download(self, url: str, dest: Path) -> None:
        """Télécharge l'extrait dans le fichier `dest`."""
        dest.write_bytes((await self._get(url)).content)

    async def _get(self, url: str) -> httpx.Response:
        """Envoie un GET ; lève DeezerUnavailableError si Deezer ne répond pas par un 200."""
        try:
            resp = await request_with_retry(self._client, "GET", url)
        except httpx.HTTPError as e:
            raise DeezerUnavailableError(f"Deezer injoignable : {e}") from e
        if resp.status_code != 200:
            raise DeezerUnavailableError(f"Deezer a répondu HTTP {resp.status_code}")
        return resp
