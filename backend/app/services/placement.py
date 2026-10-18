"""Cas d'usage « Où le placer ? » : où un morceau s'insère dans ma playlist sans casser d'enchaînement.

Les enchaînements viennent du SQL (`transition_edges`, via `TrackRepository.transitions_between`), le choix
des places du domaine (`find_placements`). L'insertion passe par `PlaylistEditor.add_track(position)`.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.adapters.db import Database
from app.adapters.playlist_repository import PlaylistItemRow, PlaylistRepository
from app.adapters.track_repository import ScoredTransition, TrackRepository
from app.domain.placement import find_placements
from app.services.playlist_editor import TrackMissingError, editable_playlist


@dataclass(frozen=True, slots=True)
class PlacementResult:
    """Une place : position d'insertion, morceaux voisins, les deux enchaînements (None = refusé)."""

    position: int
    before: PlaylistItemRow | None
    after: PlaylistItemRow | None
    incoming: ScoredTransition | None  # morceau d'avant -> ce morceau
    outgoing: ScoredTransition | None  # ce morceau -> morceau d'après
    repairs: bool
    score: float


class PlacementFinder:
    """Cherche où insérer un morceau dans une de mes playlists créées ici (une importée : lecture seule)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def placements(
        self, owner_id: UUID, playlist_id: UUID, track_id: UUID, bpm_tolerance: float
    ) -> list[PlacementResult]:
        """Les meilleures places ; 404 si playlist pas à moi ou morceau inconnu, 409 si importée."""
        repo = PlaylistRepository(self._db)
        await editable_playlist(repo, owner_id, playlist_id)
        tracks = TrackRepository(self._db)
        if not await tracks.exists(track_id):
            raise TrackMissingError("Morceau inconnu")
        items = await repo.items_with_transitions(owner_id, playlist_id, bpm_tolerance)
        order = [i.track.id for i in items]
        edges = await tracks.transitions_between(
            owner_id, list(dict.fromkeys([*order, track_id])), bpm_tolerance
        )
        found = find_placements(order, track_id, {pair: e.score for pair, e in edges.items()})
        return [
            PlacementResult(
                position=p.position,
                before=items[p.position - 1] if p.before is not None else None,
                after=items[p.position] if p.after is not None else None,
                incoming=edges.get((p.before, track_id)) if p.before is not None else None,
                outgoing=edges.get((track_id, p.after)) if p.after is not None else None,
                repairs=p.repairs,
                score=p.score,
            )
            for p in found
        ]
