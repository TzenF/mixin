"""Adaptateur Spotify testé contre une fausse API (httpx.MockTransport) : aucun appel réseau."""

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.adapters.spotify_provider import SpotifyApiError, SpotifyProvider
from app.domain.music_provider import MusicProviderError, PlaylistNotFoundError

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


async def test_does_not_send_the_token_to_a_foreign_next_link() -> None:
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Note l'hôte appelé ; la première page pointe vers un autre site."""
        hosts.append(request.url.host)
        if request.url.path == "/v1/me":
            return httpx.Response(200, json=ME)
        return httpx.Response(200, json={"items": [], "next": "https://ailleurs.example/v1/me/playlists"})

    provider = SpotifyProvider(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(MusicProviderError, match="lien de page inattendu"):
        await provider.get_user_playlists("jeton")
    assert set(hosts) == {"api.spotify.com"}


def _recording_api(created_id: str = "new") -> tuple[SpotifyProvider, list[tuple[str, str, Any]]]:
    """Fausse API qui note chaque appel (méthode, chemin, corps JSON) et accepte les écritures."""
    calls: list[tuple[str, str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Enregistre l'appel puis répond comme Spotify."""
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, body))
        if request.method == "POST" and request.url.path == "/v1/me/playlists":
            return httpx.Response(201, json={"id": created_id})
        return httpx.Response(201 if request.method == "POST" else 200, json={"snapshot_id": "s"})

    return SpotifyProvider(httpx.AsyncClient(transport=httpx.MockTransport(handler))), calls


async def test_create_playlist_is_private_and_adds_tracks_by_batches_of_100() -> None:
    provider, calls = _recording_api(created_id="pl1")
    ids = [f"t{i}" for i in range(250)]

    assert await provider.create_playlist("jeton", "Set", "Exportée", ids) == "pl1"

    assert calls[0] == (
        "POST",
        "/v1/me/playlists",
        {"name": "Set", "public": False, "description": "Exportée"},
    )
    adds = calls[1:]
    assert [(m, p) for m, p, _ in adds] == [("POST", "/v1/playlists/pl1/items")] * 3
    assert [len(b["uris"]) for _, _, b in adds] == [100, 100, 50]
    assert adds[0][2]["uris"][0] == "spotify:track:t0"
    assert adds[2][2]["uris"][-1] == "spotify:track:t249"  # l'ordre est conservé


async def test_replace_puts_the_first_100_then_appends_the_rest() -> None:
    provider, calls = _recording_api()

    await provider.replace_playlist_items("jeton", "pl1", [f"t{i}" for i in range(150)])

    assert [(m, p, len(b["uris"])) for m, p, b in calls] == [
        ("PUT", "/v1/playlists/pl1/items", 100),
        ("POST", "/v1/playlists/pl1/items", 50),
    ]


async def test_replace_with_no_track_empties_the_playlist() -> None:
    provider, calls = _recording_api()
    await provider.replace_playlist_items("jeton", "pl1", [])
    assert calls == [("PUT", "/v1/playlists/pl1/items", {"uris": []})]


async def test_write_error_is_reported() -> None:
    provider = _api({"/v1/me/playlists": lambda _req: httpx.Response(403, json={"error": "forbidden"})})
    with pytest.raises(SpotifyApiError) as exc:
        await provider.create_playlist("jeton", "Set", "", [])
    assert exc.value.status_code == 403


def test_playlist_url() -> None:
    assert SpotifyProvider(httpx.AsyncClient()).playlist_url("abc") == "https://open.spotify.com/playlist/abc"


async def test_finds_a_track_by_isrc_keeping_only_an_exact_match() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        """Répond comme GET /search : un résultat voisin, puis le bon (ISRC en minuscules)."""
        assert (request.url.params["q"], request.url.params["type"]) == ("isrc:NLCK41041964", "track")
        items = [
            {"id": "voisin", "external_ids": {"isrc": "NLCK41041965"}},
            {"id": "bon", "external_ids": {"isrc": "nlck41041964"}},
        ]
        return httpx.Response(200, json={"tracks": {"items": items}})

    assert await _api({"/v1/search": respond}).find_track_by_isrc("t", "NLCK41041964") == "bon"


async def test_isrc_unknown_to_spotify() -> None:
    other = {"tracks": {"items": [{"id": "x", "external_ids": {"isrc": "AUTRE0000001"}}]}}
    assert await _api({"/v1/search": _json(other)}).find_track_by_isrc("t", "NLCK41041964") is None
    empty = {"tracks": {"items": []}}
    assert await _api({"/v1/search": _json(empty)}).find_track_by_isrc("t", "NLCK41041964") is None
