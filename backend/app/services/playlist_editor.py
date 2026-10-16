"""Cas d'usage « modifier mes playlists » : seules mes playlists créées ici sont modifiables.

Une playlist importée d'un service musical est en lecture seule (la réimporter remplacerait les
modifications) : on la duplique pour la modifier.
"""

from __future__ import annotations

from uuid import UUID

from app.adapters.db import Database
from app.adapters.playlist_repository import PlaylistRepository, PlaylistRow
from app.adapters.track_repository import TrackRepository


class PlaylistMissingError(Exception):
    """La playlist n'existe pas, ou n'appartient pas à l'utilisateur."""


class PlaylistReadOnlyError(Exception):
    """La playlist est importée d'un service musical : il faut la dupliquer pour la modifier."""


class TrackMissingError(Exception):
    """Le morceau à ajouter n'existe pas, ou l'élément à retirer n'est pas dans la playlist."""


class OrderMismatchError(Exception):
    """Le nouvel ordre ne contient pas exactement les éléments actuels (page périmée : recharger)."""


class PlaylistEditor:
    """Crée, renomme, remplit, duplique et supprime les playlists d'un utilisateur."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, owner_id: UUID, name: str) -> PlaylistRow:
        """Crée une playlist vide."""
        repo = PlaylistRepository(self._db)
        playlist_id = await repo.create(owner_id, name)
        return await _owned(repo, owner_id, playlist_id)

    async def rename(self, owner_id: UUID, playlist_id: UUID, name: str) -> PlaylistRow:
        """Renomme une de mes playlists modifiables."""
        repo = PlaylistRepository(self._db)
        await _editable(repo, owner_id, playlist_id)
        await repo.rename(playlist_id, name)
        return await _owned(repo, owner_id, playlist_id)

    async def delete(self, owner_id: UUID, playlist_id: UUID) -> None:
        """Supprime une de mes playlists, importée ou non (une importée pourra être réimportée)."""
        repo = PlaylistRepository(self._db)
        await _owned(repo, owner_id, playlist_id)
        await repo.delete(playlist_id)

    async def add_track(self, owner_id: UUID, playlist_id: UUID, track_id: UUID) -> tuple[int, int]:
        """Ajoute un morceau en fin de playlist ; renvoie (identifiant de l'élément, position)."""
        async with self._db.transaction() as tx:
            repo = PlaylistRepository(tx)
            await _editable(repo, owner_id, playlist_id)
            if not await TrackRepository(tx).exists(track_id):
                raise TrackMissingError("Morceau inconnu")
            await repo.lock(playlist_id)
            return await repo.append_item(playlist_id, track_id)

    async def reorder(self, owner_id: UUID, playlist_id: UUID, item_ids: list[int]) -> None:
        """Remplace l'ordre des morceaux ; la liste doit contenir exactement les éléments actuels."""
        async with self._db.transaction() as tx:
            repo = PlaylistRepository(tx)
            await _editable(repo, owner_id, playlist_id)
            await repo.lock(playlist_id)
            current = await repo.item_ids(playlist_id)
            if len(item_ids) != len(current) or set(item_ids) != set(current):
                raise OrderMismatchError("La playlist a changé entre-temps : recharge-la")
            await repo.reorder(playlist_id, item_ids)

    async def remove_item(self, owner_id: UUID, playlist_id: UUID, item_id: int) -> None:
        """Retire un morceau de la playlist (les suivants remontent d'une place)."""
        async with self._db.transaction() as tx:
            repo = PlaylistRepository(tx)
            await _editable(repo, owner_id, playlist_id)
            await repo.lock(playlist_id)
            if not await repo.remove_item(playlist_id, item_id):
                raise TrackMissingError("Ce morceau n'est pas dans la playlist")

    async def copy(self, owner_id: UUID, playlist_id: UUID) -> PlaylistRow:
        """Duplique une de mes playlists (importée ou non) en une playlist modifiable, « X (copie) »."""
        async with self._db.transaction() as tx:
            repo = PlaylistRepository(tx)
            source = await _owned(repo, owner_id, playlist_id)
            copy_id = await repo.create(owner_id, f"{source.name} (copie)", forked_from=playlist_id)
            await repo.copy_items(playlist_id, copy_id)
            return await _owned(repo, owner_id, copy_id)


async def _owned(repo: PlaylistRepository, owner_id: UUID, playlist_id: UUID) -> PlaylistRow:
    """La playlist si elle est à moi ; sinon PlaylistMissingError (sans dire si elle existe)."""
    playlist = await repo.get_for_owner(owner_id, playlist_id)
    if playlist is None:
        raise PlaylistMissingError("Playlist inconnue")
    return playlist


async def _editable(repo: PlaylistRepository, owner_id: UUID, playlist_id: UUID) -> PlaylistRow:
    """La playlist si elle est à moi et créée ici ; sinon PlaylistMissingError ou PlaylistReadOnlyError."""
    playlist = await _owned(repo, owner_id, playlist_id)
    if playlist.source_provider is not None:
        raise PlaylistReadOnlyError("Playlist importée : duplique-la pour la modifier")
    return playlist
