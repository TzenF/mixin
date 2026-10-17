"""Enregistrement des morceaux venus d'un service musical : partagé par l'import de playlists et l'Explorer.

Un morceau est retrouvé par ISRC (clé de correspondance entre plateformes), sinon par son identifiant chez le
service ; sinon il est créé (analyse en attente) avec ses artistes. L'identifiant chez le service est ajouté.
"""

from __future__ import annotations

from uuid import UUID

from app.adapters.track_repository import TrackRepository
from app.domain.music_provider import ProviderTrack


async def save_provider_tracks(
    repo: TrackRepository, provider: str, tracks: list[ProviderTrack]
) -> tuple[list[UUID], list[UUID]]:
    """Enregistre les morceaux lisibles ; renvoie leurs identifiants (dans l'ordre), puis les nouveaux."""
    ordered: list[UUID] = []
    new: list[UUID] = []
    for track in tracks:
        if track.external_id is None:  # morceau local, épisode, morceau retiré
            continue
        track_id = await _find(repo, provider, track.isrc, track.external_id)
        if track_id is None:
            track_id = await repo.create(track.title, track.duration_ms, track.isrc)
            await repo.set_artists(track_id, track.artists)
            new.append(track_id)
        await repo.add_external_id(track_id, provider, track.external_id)
        ordered.append(track_id)
    return ordered, new


async def _find(repo: TrackRepository, provider: str, isrc: str | None, external_id: str) -> UUID | None:
    """Cherche le morceau en base : d'abord par ISRC, puis par identifiant chez le service."""
    if isrc:
        found = await repo.find_by_isrc(isrc)
        if found is not None:
            return found
    return await repo.find_by_external_id(provider, external_id)
