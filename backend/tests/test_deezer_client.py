"""Adaptateur Deezer testé contre une fausse API (httpx.MockTransport) : aucun appel réseau."""

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from app.adapters.deezer_client import (
    MAX_PREVIEW_BYTES,
    DeezerClient,
    DeezerTrack,
    DeezerUnavailableError,
    InvalidPreviewError,
)

pytestmark = pytest.mark.anyio


def _deezer(respond: Callable[[httpx.Request], httpx.Response]) -> DeezerClient:
    """Adaptateur branché sur une fausse API."""
    return DeezerClient(httpx.AsyncClient(transport=httpx.MockTransport(respond)))


async def test_finds_track_and_preview_by_isrc() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        """Répond comme Deezer pour un ISRC connu."""
        assert request.url.path == "/track/isrc:USUM71118074"
        return httpx.Response(200, json={"id": 14519025, "preview": "https://cdn/extrait.mp3"})

    assert await _deezer(respond).find_by_isrc("USUM71118074") == DeezerTrack(
        "14519025", "https://cdn/extrait.mp3"
    )


async def test_track_without_preview() -> None:
    deezer = _deezer(lambda _req: httpx.Response(200, json={"id": 1, "preview": ""}))
    assert await deezer.find_by_isrc("X") == DeezerTrack("1", None)


async def test_unknown_isrc_returns_none() -> None:
    # Deezer répond HTTP 200 avec une erreur « no data » (code 800)
    body = {"error": {"type": "DataException", "message": "no data", "code": 800}}
    assert await _deezer(lambda _req: httpx.Response(200, json=body)).find_by_isrc("X") is None


async def test_other_errors_mean_retry_later() -> None:
    quota = {"error": {"type": "Exception", "message": "Quota limit exceeded", "code": 4}}
    with pytest.raises(DeezerUnavailableError, match="Quota"):
        await _deezer(lambda _req: httpx.Response(200, json=quota)).find_by_isrc("X")
    with pytest.raises(DeezerUnavailableError, match="503"):
        await _deezer(lambda _req: httpx.Response(503)).find_by_isrc("X")


async def test_network_error_means_retry_later() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        """Simule une coupure réseau."""
        raise httpx.ConnectError("coupé", request=request)

    with pytest.raises(DeezerUnavailableError):
        await _deezer(respond).find_by_isrc("X")


async def test_isrc_is_encoded_in_the_url() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        """Vérifie que l'ISRC reste un seul segment de chemin, sans query."""
        assert request.url.raw_path == b"/track/isrc:AB%2F..%3Fx%3D1"
        return httpx.Response(200, json={"id": 1, "preview": ""})

    await _deezer(respond).find_by_isrc("AB/..?x=1")


async def test_download_writes_the_file(tmp_path: Path) -> None:
    dest = tmp_path / "extrait.mp3"
    await _deezer(lambda _req: httpx.Response(200, content=b"ID3...")).download("https://cdn/x.mp3", dest)
    assert dest.read_bytes() == b"ID3..."


async def test_download_refuses_plain_http(tmp_path: Path) -> None:
    deezer = _deezer(lambda _req: httpx.Response(200, content=b"ID3"))
    with pytest.raises(InvalidPreviewError):
        await deezer.download("http://cdn/x.mp3", tmp_path / "extrait.mp3")


async def test_download_refuses_a_file_too_big(tmp_path: Path) -> None:
    deezer = _deezer(lambda _req: httpx.Response(200, content=b"x" * (MAX_PREVIEW_BYTES + 1)))
    with pytest.raises(InvalidPreviewError):
        await deezer.download("https://cdn/x.mp3", tmp_path / "extrait.mp3")


async def test_download_error_means_retry_later(tmp_path: Path) -> None:
    deezer = _deezer(lambda _req: httpx.Response(503))
    with pytest.raises(DeezerUnavailableError, match="503"):
        await deezer.download("https://cdn/x.mp3", tmp_path / "extrait.mp3")


async def test_get_track_by_deezer_id() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        """Répond comme Deezer pour un identifiant connu."""
        assert request.url.path == "/track/525334532"
        return httpx.Response(200, json={"id": 525334532, "preview": "https://cdn/extrait.mp3"})

    assert await _deezer(respond).get_track("525334532") == DeezerTrack(
        "525334532", "https://cdn/extrait.mp3"
    )


async def test_get_track_gone_from_deezer() -> None:
    body = {"error": {"type": "DataException", "message": "no data", "code": 800}}
    assert await _deezer(lambda _req: httpx.Response(200, json=body)).get_track("1") is None
