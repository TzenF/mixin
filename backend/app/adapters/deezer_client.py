"""Deezer, utilisé en coulisses : retrouve un morceau par ISRC et télécharge son extrait de 30 s.

API publique, sans compte utilisateur. Vérifié en octobre 2026 : `GET /track/isrc:<ISRC>` renvoie `id` et
`preview` (URL signée qui expire : on la télécharge aussitôt, on ne la stocke jamais). Les erreurs arrivent
en HTTP 200 avec un objet `error` ; le code 800 (« no data ») veut dire « ISRC inconnu ».
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx

from app.adapters.http_retry import request_with_retry

DEEZER_API = "https://api.deezer.com"
_NO_DATA = 800
# Un extrait de 30 s pèse environ 480 Ko (mesuré en octobre 2026) : au-delà de 5 Mo, ce n'en est pas un.
MAX_PREVIEW_BYTES = 5_000_000


class DeezerUnavailableError(Exception):
    """Deezer ne répond pas correctement pour l'instant (quota, panne, réseau) : réessayer plus tard."""


class InvalidPreviewError(Exception):
    """L'extrait proposé par Deezer est refusé (pas en HTTPS, ou trop gros) : inutile de réessayer."""


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
        # L'ISRC vient de Spotify : encodé pour qu'un « / » ou un « ? » ne change pas l'URL appelée.
        data = (await self._get(f"{DEEZER_API}/track/isrc:{quote(isrc, safe='')}")).json()
        if error := data.get("error"):
            if error.get("code") == _NO_DATA:
                return None
            raise DeezerUnavailableError(f"Deezer : {error.get('message', 'erreur inconnue')}")
        if not data.get("id"):
            return None
        return DeezerTrack(str(data["id"]), data.get("preview") or None)

    async def download(self, url: str, dest: Path) -> None:
        """Télécharge l'extrait dans le fichier `dest` (HTTPS uniquement, taille plafonnée)."""
        # L'URL est signée : on ne la journalise pas en entier.
        if urlsplit(url).scheme != "https":
            raise InvalidPreviewError("Extrait refusé : URL qui n'est pas en HTTPS")
        try:
            async with self._client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    raise DeezerUnavailableError(f"Extrait Deezer : HTTP {resp.status_code}")
                if resp.url.scheme != "https":  # redirection vers HTTP
                    raise InvalidPreviewError("Extrait refusé : redirigé hors HTTPS")
                size = 0
                with dest.open("wb") as file:
                    async for chunk in resp.aiter_bytes():
                        size += len(chunk)
                        if size > MAX_PREVIEW_BYTES:
                            raise InvalidPreviewError(f"Extrait refusé : plus de {MAX_PREVIEW_BYTES} octets")
                        file.write(chunk)
        except httpx.HTTPError as e:
            raise DeezerUnavailableError(f"Extrait Deezer injoignable : {e.__class__.__name__}") from e

    async def _get(self, url: str) -> httpx.Response:
        """Envoie un GET ; lève DeezerUnavailableError si Deezer ne répond pas par un 200."""
        try:
            resp = await request_with_retry(self._client, "GET", url)
        except httpx.HTTPError as e:
            raise DeezerUnavailableError(f"Deezer injoignable : {e}") from e
        if resp.status_code != 200:
            raise DeezerUnavailableError(f"Deezer a répondu HTTP {resp.status_code}")
        return resp
