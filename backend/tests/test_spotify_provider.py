"""Adaptateur Spotify testé contre une fausse API (httpx.MockTransport) : aucun appel réseau."""

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.adapters.spotify_provider import SpotifyApiError, SpotifyProvider
from app.domain.music_provider import PlaylistNotFoundError

pytestmark = pytest.mark.anyio

ME = {"id": "katia", "display_name": "Katia"}


def _playlist(pid: str, owner: str, total: int) -> dict[str, Any]:
    """Playlist telle que la renvoie GET /me/playlists (format 2026 : `items.total`)."""
    return {"id": pid, "name": f"Playlist {pid}", "owner": {"id": owner}, "items": {"total": total}}


def _entry(item: dict[str, Any] | None) -> dict[str, Any]:
    """Entrée de playlist (format 2026 : `item` au lieu de `track`)."""
    return {"added_at": "2026-10-01T00:00:00Z", "item": item}


def _api(routes: dict[str, Callable[[httpx.Request], httpx.Response]]) -> SpotifyProvider:
    """Adaptateur branché sur une fausse API : clé = chemin (+ query éventuelle)."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Répond selon le chemin demandé."""
        key = request.url.path + (f"?{request.url.query.decode()}" if request.url.query else "")
        for route, respond in routes.items():
            if key == route or request.url.path == route:
                return respond(request)
        return httpx.Response(404, json={"error": key})

    return SpotifyProvider(httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def _json(data: dict[str, Any]) -> Callable[[httpx.Request], httpx.Response]:
    """Réponse JSON 200 fixe."""
    return lambda _req: httpx.Response(200, json=data)


async def test_lists_only_owned_playlists_across_pages() -> None:
    page2 = "https://api.spotify.com/v1/me/playlists?offset=50&limit=50"
    provider = _api(
        {
            "/v1/me": _json(ME),
            "/v1/me/playlists?limit=50": _json(
                {"items": [_playlist("a", "katia", 32), _playlist("b", "autre", 10), None], "next": page2}
            ),
            "/v1/me/playlists?offset=50&limit=50": _json(
                {"items": [_playlist("c", "katia", 5)], "next": None}
            ),
        }
    )

    playlists = await provider.get_user_playlists("jeton")

    assert [(p.external_id, p.track_count) for p in playlists] == [("a", 32), ("c", 5)]


async def test_get_playlist_maps_tracks_and_marks_unplayable_ones() -> None:
    track = {
        "type": "track",
        "id": "t1",
        "name": "TESLA",
        "artists": [{"name": "Mau P"}],
        "duration_ms": 180000,
        "external_ids": {"isrc": "nl8rl2530184"},
    }
    local = {"type": "track", "id": None, "is_local": True, "name": "Mon edit", "artists": []}
    episode = {"type": "episode", "id": "e1", "name": "Un podcast"}
    provider = _api(
        {
            "/v1/me": _json(ME),
            "/v1/me/playlists": _json({"items": [_playlist("a", "katia", 4)], "next": None}),
            "/v1/playlists/a/items": _json(
                {"items": [_entry(track), _entry(local), _entry(episode), _entry(None)], "next": None}
            ),
        }
    )

    playlist = await provider.get_playlist("jeton", "a")

    first = playlist.tracks[0]
    assert (first.external_id, first.title, first.artists, first.isrc) == (
        "t1",
        "TESLA",
        ["Mau P"],
        "NL8RL2530184",
    )
    assert [t.external_id for t in playlist.tracks[1:]] == [None, None, None]


async def test_get_playlist_refuses_a_playlist_of_someone_else() -> None:
    provider = _api(
        {
            "/v1/me": _json(ME),
            "/v1/me/playlists": _json({"items": [_playlist("b", "autre", 10)], "next": None}),
        }
    )

    with pytest.raises(PlaylistNotFoundError):
        await provider.get_playlist("jeton", "b")


async def test_retries_after_429() -> None:
    calls = {"n": 0}

    def flaky(_req: httpx.Request) -> httpx.Response:
        """Répond 429 la première fois, puis 200."""
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json=ME)

    user = await _api({"/v1/me": flaky}).get_current_user("jeton")

    assert user.id == "katia" and calls["n"] == 2


async def test_gives_up_when_retry_after_is_too_long() -> None:
    provider = _api({"/v1/me": lambda _req: httpx.Response(429, headers={"Retry-After": "3600"})})

    with pytest.raises(SpotifyApiError) as exc:
        await provider.get_current_user("jeton")
    assert exc.value.status_code == 429


async def test_display_name_falls_back_to_spotify_id() -> None:
    user = await _api({"/v1/me": _json({"id": "katia", "display_name": None})}).get_current_user("jeton")

    assert user.display_name == "katia"
