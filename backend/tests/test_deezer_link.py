"""Lecture des liens de playlist Deezer collés par l'utilisateur."""

import pytest

from app.domain.deezer_link import is_short_link, playlist_id_from_link


@pytest.mark.parametrize(
    "text",
    [
        "1183071761",
        "  1183071761 ",
        "https://www.deezer.com/fr/playlist/1183071761",
        "https://www.deezer.com/playlist/1183071761/",
        "http://deezer.com/playlist/1183071761",
        "www.deezer.com/en/playlist/1183071761",
        "https://www.deezer.com/pt-br/playlist/1183071761",
        # URL finale d'un lien partagé par l'app (vérifiée le 18/10/2026)
        "https://www.deezer.com/fr/playlist/1183071761?host=1814354222&utm_campaign=clipboard-generic"
        "&utm_source=user_sharing&utm_content=playlist-1183071761&deferredFl=1&universal_link=1",
    ],
)
def test_reads_the_playlist_id(text: str) -> None:
    assert playlist_id_from_link(text) == "1183071761"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "https://www.deezer.com/fr/track/2651012",
        "https://www.deezer.com/fr/album/302127",
        "https://www.deezer.com/deezer-links-404",
        "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
        "https://deezer.com.evil.example/playlist/1183071761",
        "ftp://www.deezer.com/playlist/1183071761",
        "https://link.deezer.com/s/32Qt0aV30k82TqqNUzQcB",  # à résoudre d'abord
        "Top France",
    ],
)
def test_rejects_what_is_not_a_playlist(text: str) -> None:
    assert playlist_id_from_link(text) is None


def test_recognises_short_links_from_the_app() -> None:
    assert is_short_link("https://link.deezer.com/s/32Qt0aV30k82TqqNUzQcB")
    assert is_short_link(" https://link.deezer.com/s/32Qt0aV30k82TqqNUzQcB ")
    assert not is_short_link("http://link.deezer.com/s/32Qt0aV30k82TqqNUzQcB")
    assert not is_short_link("https://link.deezer.com/autre")
    assert not is_short_link("https://deezer.page.link/abc123")  # ancien format, mort en 2025
