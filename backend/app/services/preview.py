"""Cas d'usage « écouter un extrait » : trouve l'URL de l'extrait Deezer d'un morceau, au moment de l'écoute.

Le navigateur lit l'URL directement sur le CDN de Deezer : le serveur ne télécharge, ne stocke ni ne relaie
l'audio (règle n°5). L'URL est signée et expire après environ 15 min : elle n'est jamais enregistrée (ni en
base, ni dans Redis) ni journalisée. Ce service ne fait aucune écriture.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from urllib.parse import urlsplit
from uuid import UUID

from app.adapters.deezer_client import DeezerTrack, preview_expiry
from app.adapters.track_repository import TrackRepository

PreviewMissingReason = Literal["no_isrc", "unknown_on_deezer", "no_preview"]

_MESSAGES: dict[PreviewMissingReason, str] = {
    "no_isrc": "Pas d'extrait : ce morceau n'a pas d'ISRC pour le retrouver sur Deezer",
    "unknown_on_deezer": "Pas d'extrait : Deezer ne connaît pas ce morceau",
    "no_preview": "Pas d'extrait : Deezer n'en propose pas pour ce morceau",
}


class PreviewUnavailableError(Exception):
    """Le morceau n'a pas d'extrait écoutable ; `reason` dit pourquoi."""

    def __init__(self, reason: PreviewMissingReason) -> None:
        super().__init__(_MESSAGES[reason])
        self.reason = reason


class PreviewSource(Protocol):
    """Ce dont le service a besoin de Deezer."""

    async def get_track(self, deezer_id: str) -> DeezerTrack | None:
        """Relit un morceau par son identifiant Deezer."""
        ...

    async def find_by_isrc(self, isrc: str) -> DeezerTrack | None:
        """Cherche un morceau par ISRC."""
        ...


@dataclass(frozen=True, slots=True)
class Preview:
    """URL d'extrait à lire tout de suite ; expires_at None si l'expiration est inconnue."""

    url: str
    expires_at: datetime | None


class PreviewService:
    """Fournit l'URL de l'extrait d'un morceau, redemandée à Deezer à chaque écoute."""

    def __init__(self, tracks: TrackRepository, deezer: PreviewSource) -> None:
        self._tracks = tracks
        self._deezer = deezer

    async def preview(self, track_id: UUID) -> Preview:
        """URL neuve de l'extrait, ou PreviewUnavailableError (pas d'extrait) / DeezerUnavailableError."""
        deezer_id = await self._tracks.find_external_id(track_id, "deezer")
        if deezer_id is not None:
            found = await self._deezer.get_track(deezer_id)
        else:
            # Morceau pas encore analysé : on cherche par ISRC sans rien enregistrer (le worker le fera).
            isrc = await self._tracks.get_isrc(track_id)
            if isrc is None:
                raise PreviewUnavailableError("no_isrc")
            found = await self._deezer.find_by_isrc(isrc)
        if found is None:
            raise PreviewUnavailableError("unknown_on_deezer")
        if found.preview_url is None or urlsplit(found.preview_url).scheme != "https":
            raise PreviewUnavailableError("no_preview")
        return Preview(url=found.preview_url, expires_at=preview_expiry(found.preview_url))
