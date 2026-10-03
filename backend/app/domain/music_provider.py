"""Contrat commun aux services musicaux (Spotify aujourd'hui, Deezer ou autre demain).

Le reste de l'application ne connaît que cette interface ; chaque service est un adaptateur.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ProviderTrack:
    """Un morceau tel que le décrit un service musical."""

    external_id: str
    title: str
    artists: list[str]
    duration_ms: int | None
    isrc: str | None


@dataclass(frozen=True, slots=True)
class ProviderPlaylist:
    """Une playlist telle que la décrit un service musical."""

    external_id: str
    name: str
    track_count: int
    tracks: list[ProviderTrack] = field(default_factory=list)


class MusicProvider(Protocol):
    """Ce que tout adaptateur de service musical doit savoir faire."""

    name: str

    async def get_user_playlists(self, access_token: str) -> list[ProviderPlaylist]:
        """Liste les playlists de l'utilisateur connecté."""
        ...

    async def get_playlist_tracks(self, access_token: str, playlist_id: str) -> list[ProviderTrack]:
        """Liste les morceaux d'une playlist."""
        ...

    async def get_saved_tracks(self, access_token: str) -> list[ProviderTrack]:
        """Liste les titres likés de l'utilisateur."""
        ...

    async def create_playlist(self, access_token: str, name: str, track_ids: list[str]) -> str:
        """Crée une playlist avec ces morceaux et renvoie son identifiant chez le fournisseur."""
        ...
