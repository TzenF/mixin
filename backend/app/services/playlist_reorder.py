"""Cas d'usage « proposer un ordre » : l'ordre de ma playlist qui enchaîne le mieux, sans l'appliquer.

Le graphe vient du SQL (`transition_edges`), l'ordre du domaine (`best_order`). Appliquer la proposition passe
par le réordonnancement habituel (`PlaylistEditor.reorder`), qui refuse un ordre périmé. Les morceaux non
analysés n'ont aucun enchaînement connu : ils vont en fin, dans leur ordre actuel, et ne comptent pas dans le
bilan.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.adapters.db import Database
from app.adapters.playlist_repository import PlaylistRepository
from app.adapters.track_repository import ScoredTransition, TrackRepository
from app.domain.reorder import OrderQuality, best_order, order_quality
from app.services.playlist_editor import editable_playlist


@dataclass(frozen=True, slots=True)
class ProposedOrder:
    """L'ordre proposé (éléments de la playlist), le bilan avant / après et chaque enchaînement."""

    item_ids: list[int]
    before: OrderQuality
    after: OrderQuality
    unanalysed: int  # morceaux non analysés, placés en fin
    steps: list[ScoredTransition | None]  # entre morceaux analysés consécutifs ; None = refusé


class PlaylistReorderer:
    """Propose un meilleur ordre pour mes playlists (créées ici : une importée est en lecture seule)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def propose(self, owner_id: UUID, playlist_id: UUID, bpm_tolerance: float) -> ProposedOrder:
        """Ordre proposé et bilan ; 404 si la playlist n'est pas à moi, 409 si elle est importée."""
        repo = PlaylistRepository(self._db)
        await editable_playlist(repo, owner_id, playlist_id)
        items = await repo.items_with_transitions(owner_id, playlist_id, bpm_tolerance)
        analysed, others = [], []
        for item in items:
            (analysed if item.track.bpm is not None and item.track.camelot is not None else others).append(
                item
            )
        edges = await TrackRepository(self._db).transitions_between(
            owner_id, list(dict.fromkeys(i.track.id for i in analysed)), bpm_tolerance
        )
        scores = {
            (a, b): edges[(x.track.id, y.track.id)].score
            for a, x in enumerate(analysed)
            for b, y in enumerate(analysed)
            if a != b and (x.track.id, y.track.id) in edges
        }
        order = best_order(len(analysed), scores)
        proposed = [analysed[k] for k in order]
        return ProposedOrder(
            item_ids=[i.item_id for i in proposed + others],
            before=order_quality(list(range(len(analysed))), scores),
            after=order_quality(order, scores),
            unanalysed=len(others),
            steps=[edges.get((x.track.id, y.track.id)) for x, y in zip(proposed, proposed[1:], strict=False)],
        )
