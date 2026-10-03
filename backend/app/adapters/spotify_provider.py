"""Adaptateur Spotify : lecture du profil et des playlists (Web API, règles de février 2026).

Endpoints et noms de champs repris du spike 01, testé contre la vraie API :
  - `GET /me/playlists`, `GET /playlists/{id}/items` (plus `/tracks`) ;
  - dans les réponses : `tracks` -> `items` (nombre de titres) et `track` -> `item` (chaque entrée).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.adapters.http_retry import request_with_retry
from app.domain.music_provider import (
    MusicProviderError,
    PlaylistNotFoundError,
    ProviderPlaylist,
    ProviderTrack,
)

API = "https://api.spotify.com/v1"
PAGE_SIZE = 50
MAX_ITEMS = 10_000  # garde-fou : une playlist Spotify en contient au plus 10 000


@dataclass(frozen=True, slots=True)
class SpotifyUser:
    """Le profil Spotify de l'utilisateur connecté (l'email n'est pas fourni)."""

    id: str
    display_name: str


class SpotifyApiError(MusicProviderError):
    """Réponse d'erreur de la Web API Spotify."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"Spotify a répondu HTTP {status_code} : {message}")
        self.status_code = status_code


class SpotifyProvider:
    """Implémente MusicProvider pour Spotify."""

    name = "spotify"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def get_current_user(self, access_token: str) -> SpotifyUser:
        """Lit le profil de l'utilisateur connecté."""
        me = await self._get(access_token, f"{API}/me")
        return SpotifyUser(id=me["id"], display_name=me.get("display_name") or me["id"])

    async def get_user_playlists(self, access_token: str) -> list[ProviderPlaylist]:
        """Liste les playlists dont l'utilisateur est propriétaire (seules à renvoyer leurs titres)."""
        me = await self.get_current_user(access_token)
        entries = await self._paginate(access_token, f"{API}/me/playlists?limit={PAGE_SIZE}")
        return [
            ProviderPlaylist(external_id=p["id"], name=p.get("name") or "", track_count=_track_count(p))
            for p in entries
            if p and (p.get("owner") or {}).get("id") == me.id
        ]

    async def get_playlist(self, access_token: str, playlist_id: str) -> ProviderPlaylist:
        """Renvoie une playlist de l'utilisateur avec ses morceaux ; erreur si elle n'est pas à lui."""
        # On passe par la liste des playlists (endpoint testé) : cela vérifie aussi le propriétaire.
        owned = {p.external_id: p for p in await self.get_user_playlists(access_token)}
        playlist = owned.get(playlist_id)
        if playlist is None:
            raise PlaylistNotFoundError(f"Playlist {playlist_id} introuvable parmi tes playlists Spotify")
        entries = await self._paginate(access_token, f"{API}/playlists/{playlist_id}/items?limit={PAGE_SIZE}")
        tracks = [_to_track(e) for e in entries]
        return ProviderPlaylist(
            external_id=playlist.external_id, name=playlist.name, track_count=len(tracks), tracks=tracks
        )

    async def get_saved_tracks(self, access_token: str) -> list[ProviderTrack]:
        """Titres likés : pas encore implémenté (hors périmètre de l'import de playlists)."""
        raise NotImplementedError("Import des titres likés : prévu à une étape ultérieure")

    async def create_playlist(self, access_token: str, name: str, track_ids: list[str]) -> str:
        """Création de playlist : pas encore implémentée (étape export)."""
        raise NotImplementedError("Export vers Spotify : prévu à l'étape export")

    async def _get(self, access_token: str, url: str) -> dict[str, Any]:
        """Appelle un endpoint GET et renvoie sa réponse JSON."""
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            resp = await request_with_retry(self._client, "GET", url, headers=headers)
        except httpx.HTTPError as e:
            raise MusicProviderError(f"Spotify injoignable : {e}") from e
        if resp.status_code != 200:
            raise SpotifyApiError(resp.status_code, resp.text[:200])
        return resp.json()

    async def _paginate(self, access_token: str, url: str | None) -> list[dict[str, Any]]:
        """Suit les liens `next` et renvoie tous les éléments de toutes les pages."""
        items: list[dict[str, Any]] = []
        while url and len(items) < MAX_ITEMS:
            page = await self._get(access_token, url)
            items.extend(page.get("items") or [])
            url = page.get("next")
        return items


def _track_count(playlist: dict[str, Any]) -> int:
    """Nombre de titres d'une playlist (`items.total` depuis 2026, `tracks.total` avant)."""
    return int((playlist.get("items") or playlist.get("tracks") or {}).get("total") or 0)


def _to_track(entry: dict[str, Any]) -> ProviderTrack:
    """Convertit une entrée de playlist ; les morceaux locaux et les épisodes n'ont pas d'external_id."""
    item = entry.get("item") or entry.get("track") or {}
    playable = item.get("type", "track") == "track" and not item.get("is_local") and bool(item.get("id"))
    return ProviderTrack(
        external_id=item["id"] if playable else None,
        title=item.get("name") or "(morceau indisponible)",
        artists=[a["name"] for a in item.get("artists") or [] if a.get("name")],
        duration_ms=item.get("duration_ms") or None,
        isrc=((item.get("external_ids") or {}).get("isrc") or "").upper() or None,
    )
