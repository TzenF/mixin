"""Cas d'usage « tenir le créneau » : quels morceaux retirer pour que ma playlist tienne dans son créneau.

La durée comptée d'un morceau est sa durée entière réduite à la part jouée (`played_percent` de la playlist).
Les enchaînements viennent du SQL (`transition_edges`), le choix des morceaux du domaine (`suggest_cuts`).
Appliquer la proposition passe par `PlaylistEditor.remove_items` (tout ou rien).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.adapters.db import Database
from app.adapters.playlist_repository import PlaylistRepository
from app.adapters.track_repository import TrackRepository
from app.domain.set_cut import SetQuality, set_quality, suggest_cuts
from app.services.playlist_editor import editable_playlist


@dataclass(frozen=True, slots=True)
class CutProposal:
    """Morceaux à retirer (éléments de la playlist), durées avant / après et bilan des enchaînements."""

    remove_item_ids: list[int]
    total_ms: int
    total_after_ms: int
    slot_ms: int | None  # None : pas de créneau, rien à proposer
    before: SetQuality
    after: SetQuality


class SetCutter:
    """Propose quoi retirer de mes playlists (créées ici : une importée est en lecture seule)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def propose(self, owner_id: UUID, playlist_id: UUID, bpm_tolerance: float) -> CutProposal:
        """Proposition pour tenir le créneau (rien si pas de créneau ou si ça tient) ; 404 / 409 sinon."""
        repo = PlaylistRepository(self._db)
        playlist = await editable_playlist(repo, owner_id, playlist_id)
        items = await repo.items_with_transitions(owner_id, playlist_id, bpm_tolerance)
        durations = [(i.track.duration_ms or 0) * playlist.played_percent // 100 for i in items]
        analysed = {k for k, i in enumerate(items) if i.track.bpm is not None and i.track.camelot is not None}
        ids = list(dict.fromkeys(items[k].track.id for k in analysed))
        edges = await TrackRepository(self._db).transitions_between(owner_id, ids, bpm_tolerance)
        scores = {
            (a, b): edges[(items[a].track.id, items[b].track.id)].score
            for a in analysed
            for b in analysed
            if a != b and (items[a].track.id, items[b].track.id) in edges
        }
        slot_ms = playlist.slot_minutes * 60_000 if playlist.slot_minutes is not None else None
        removed = suggest_cuts(durations, analysed, scores, slot_ms) if slot_ms is not None else []
        kept = [k for k in range(len(items)) if k not in set(removed)]
        return CutProposal(
            remove_item_ids=[items[k].item_id for k in removed],
            total_ms=sum(durations),
            total_after_ms=sum(durations[k] for k in kept),
            slot_ms=slot_ms,
            before=set_quality(list(range(len(items))), analysed, scores),
            after=set_quality(kept, analysed, scores),
        )
