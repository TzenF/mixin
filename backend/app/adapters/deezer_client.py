"""Deezer, en coulisses : morceau par ISRC, extrait de 30 s, et playlists publiques (tops, éditoriales).

API publique, sans compte utilisateur. Vérifié en octobre 2026 : `GET /track/isrc:<ISRC>` renvoie `id` et
`preview` (URL signée qui expire : on la télécharge aussitôt, on ne la stocke jamais). Les erreurs arrivent
en HTTP 200 avec un objet `error` ; le code 800 (« no data ») veut dire « ISRC inconnu ».
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

import httpx

from app.adapters.http_retry import request_with_retry
from app.domain.deezer_link import SHORT_LINK_HOST, is_short_link
from app.domain.music_provider import ProviderTrack

DEEZER_API = "https://api.deezer.com"
_NO_DATA = 800
# Un extrait de 30 s pèse environ 480 Ko (mesuré en octobre 2026) : au-delà de 5 Mo, ce n'en est pas un.
MAX_PREVIEW_BYTES = 5_000_000
# Garde-fou : on ne lit pas plus de morceaux que ça dans une playlist (les tops en ont 100).
MAX_PLAYLIST_TRACKS = 2000


class DeezerUnavailableError(Exception):
    """Deezer ne répond pas correctement pour l'instant (quota, panne, réseau) : réessayer plus tard."""


class InvalidPreviewError(Exception):
    """L'extrait proposé par Deezer est refusé (pas en HTTPS, ou trop gros) : inutile de réessayer."""


@dataclass(frozen=True, slots=True)
class DeezerTrack:
    """Morceau Deezer trouvé par ISRC : son identifiant et l'URL de son extrait (None s'il n'en a pas)."""

    deezer_id: str
    preview_url: str | None


@dataclass(frozen=True, slots=True)
class DeezerPlaylist:
    """Une playlist publique de Deezer (top, playlist éditoriale…)."""

    deezer_id: str
    title: str
    curator: str | None
    track_count: int
    public: bool = True


class DeezerClient:
    """Accès à l'API publique de Deezer."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def find_by_isrc(self, isrc: str) -> DeezerTrack | None:
        """Cherche le morceau par ISRC ; None si Deezer ne le connaît pas."""
        # L'ISRC vient de Spotify : encodé pour qu'un « / » ou un « ? » ne change pas l'URL appelée.
        return await self._track(f"{DEEZER_API}/track/isrc:{quote(isrc, safe='')}")

    async def get_track(self, deezer_id: str) -> DeezerTrack | None:
        """Relit un morceau par son identifiant Deezer (URL d'extrait neuve) ; None s'il n'existe plus."""
        return await self._track(f"{DEEZER_API}/track/{quote(deezer_id, safe='')}")

    async def _track(self, url: str) -> DeezerTrack | None:
        """Appelle /track/… et lit la réponse ; None pour « no data » (code 800), sinon erreur à réessayer."""
        data = (await self._get(url)).json()
        if self._missing(data) or not data.get("id"):
            return None
        return DeezerTrack(str(data["id"]), data.get("preview") or None)

    @staticmethod
    def _missing(data: dict[str, object]) -> bool:
        """Vrai si Deezer répond « no data » (code 800) ; DeezerUnavailableError pour une autre erreur."""
        error = data.get("error")
        if not isinstance(error, dict):
            return False
        if error.get("code") == _NO_DATA:
            return True
        raise DeezerUnavailableError(f"Deezer : {error.get('message', 'erreur inconnue')}")

    async def playlist(self, playlist_id: str) -> DeezerPlaylist | None:
        """Titre, créateur et taille d'une playlist publique ; None si Deezer ne la connaît pas."""
        data = (await self._get(f"{DEEZER_API}/playlist/{quote(playlist_id, safe='')}")).json()
        if self._missing(data) or not data.get("id"):
            return None
        return DeezerPlaylist(
            deezer_id=str(data["id"]),
            title=data.get("title") or "",
            curator=(data.get("creator") or {}).get("name"),
            track_count=int(data.get("nb_tracks") or 0),
            public=data.get("public") is not False,
        )

    async def resolve_short_link(self, url: str) -> str | None:
        """URL où mène un lien court de l'app (`link.deezer.com/s/…`) ; None s'il ne mène nulle part.

        Une seule requête, sans suivre les redirections (vérifié le 18/10/2026) : la 1re réponse est un 301
        vers `link.deezer.com/?dest=<URL du site>&…` ; un lien mort ou expiré, un 302 vers `deezer-links-404`.
        """
        if not is_short_link(url):
            return None
        try:
            resp = await self._client.get(url, follow_redirects=False, timeout=10)
        except httpx.HTTPError as e:
            raise DeezerUnavailableError(f"Lien Deezer injoignable : {e.__class__.__name__}") from e
        if resp.status_code >= 500 or resp.status_code == 429:
            raise DeezerUnavailableError(f"Lien Deezer : HTTP {resp.status_code}")
        location = resp.headers.get("location") if resp.is_redirect else None
        if not location:
            return None
        parts = urlsplit(location)
        if parts.hostname == SHORT_LINK_HOST:
            return (parse_qs(parts.query).get("dest") or [None])[0]
        return location

    async def playlist_tracks(self, playlist_id: str) -> list[ProviderTrack] | None:
        """Morceaux d'une playlist publique, dans l'ordre (ISRC, artiste principal) ; None si inconnue."""
        url: str | None = f"{DEEZER_API}/playlist/{quote(playlist_id, safe='')}/tracks?limit=100"
        tracks: list[ProviderTrack] = []
        while url and len(tracks) < MAX_PLAYLIST_TRACKS:
            data = (await self._get(url)).json()
            if self._missing(data):
                return None
            tracks.extend(_provider_track(item) for item in data.get("data") or [])
            url = data.get("next")
            # On ne suit la pagination que vers l'API de Deezer.
            if url and not url.startswith(f"{DEEZER_API}/"):
                raise DeezerUnavailableError("Deezer a renvoyé un lien de page inattendu")
        return tracks

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


def preview_expiry(url: str) -> datetime | None:
    """Date d'expiration d'une URL d'extrait (jeton `hdnea=exp=…`, environ 15 min) ; None si illisible."""
    match = re.search(r"[?&]hdnea=exp=(\d+)", url)
    return datetime.fromtimestamp(int(match.group(1)), UTC) if match else None


def _provider_track(item: dict[str, Any]) -> ProviderTrack:
    """Convertit un morceau d'une playlist Deezer ; un morceau non lisible n'a pas d'external_id."""
    readable = bool(item.get("readable", True)) and bool(item.get("id"))
    artist = (item.get("artist") or {}).get("name")
    isrc = (item.get("isrc") or "").upper() or None
    return ProviderTrack(
        external_id=str(item["id"]) if readable else None,
        title=item.get("title") or "(morceau indisponible)",
        artists=[artist] if artist else [],  # Deezer ne donne ici que l'artiste principal (pas les « feat. »)
        duration_ms=int(item["duration"]) * 1000 if item.get("duration") else None,
        isrc=isrc,
    )
