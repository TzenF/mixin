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


# Position au-delà de toute playlist : le morceau est placé en fin (insert_items s'arrête à la fin).
END_OF_PLAYLIST = 2_147_483_647


class PlaylistEditor:
    """Crée, renomme, remplit, duplique et supprime les playlists d'un utilisateur."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, owner_id: UUID, name: str) -> PlaylistRow:
        """Crée une playlist vide."""
        repo = PlaylistRepository(self._db)
        playlist_id = await repo.create(owner_id, name)
        return await owned_playlist(repo, owner_id, playlist_id)

    async def update(self, owner_id: UUID, playlist_id: UUID, changes: dict[str, object]) -> PlaylistRow:
        """Change le nom, le créneau ou la part jouée d'une playlist modifiable (absent = inchangé)."""
        repo = PlaylistRepository(self._db)
        await editable_playlist(repo, owner_id, playlist_id)
        await repo.update(playlist_id, changes)
        return await owned_playlist(repo, owner_id, playlist_id)

    async def delete(self, owner_id: UUID, playlist_id: UUID) -> None:
        """Supprime une de mes playlists, importée ou non (une importée pourra être réimportée)."""
        repo = PlaylistRepository(self._db)
        await owned_playlist(repo, owner_id, playlist_id)
        await repo.delete(playlist_id)

    async def add_track(
        self, owner_id: UUID, playlist_id: UUID, track_id: UUID, position: int | None = None
    ) -> tuple[int, int]:
        """Ajoute un morceau en fin, ou à `position` (les suivants descendent) ; renvoie (élément, place)."""
        at = END_OF_PLAYLIST if position is None else position
        return (await self.insert_tracks(owner_id, playlist_id, [track_id], at))[0]

    async def insert_tracks(
        self, owner_id: UUID, playlist_id: UUID, track_ids: list[UUID], position: int
    ) -> list[tuple[int, int]]:
        """Insère ces morceaux, dans l'ordre, à `position` (tout ou rien) ; renvoie (élément, place)."""
        async with self._db.transaction() as tx:
            repo = PlaylistRepository(tx)
            await editable_playlist(repo, owner_id, playlist_id)
            tracks = TrackRepository(tx)
            for track_id in dict.fromkeys(track_ids):
                if not await tracks.exists(track_id):
                    raise TrackMissingError("Morceau inconnu")
            await repo.lock(playlist_id)
            return await repo.insert_items(playlist_id, track_ids, position)

    async def reorder(self, owner_id: UUID, playlist_id: UUID, item_ids: list[int]) -> None:
        """Remplace l'ordre des morceaux ; la liste doit contenir exactement les éléments actuels."""
        async with self._db.transaction() as tx:
            repo = PlaylistRepository(tx)
            await editable_playlist(repo, owner_id, playlist_id)
            await repo.lock(playlist_id)
            current = await repo.item_ids(playlist_id)
            if len(item_ids) != len(current) or set(item_ids) != set(current):
                raise OrderMismatchError("La playlist a changé entre-temps : recharge-la")
            await repo.reorder(playlist_id, item_ids)

    async def remove_item(self, owner_id: UUID, playlist_id: UUID, item_id: int) -> None:
        """Retire un morceau de la playlist (les suivants remontent d'une place)."""
        await self.remove_items(owner_id, playlist_id, [item_id])

    async def remove_items(self, owner_id: UUID, playlist_id: UUID, item_ids: list[int]) -> None:
        """Retire ces morceaux d'un coup (tout ou rien : un seul absent, et rien n'est retiré)."""
        async with self._db.transaction() as tx:
            repo = PlaylistRepository(tx)
            await editable_playlist(repo, owner_id, playlist_id)
            await repo.lock(playlist_id)
            wanted = set(item_ids)
            if await repo.remove_items(playlist_id, list(wanted)) != len(wanted):
                raise TrackMissingError("Ce morceau n'est pas dans la playlist")

    async def copy(self, owner_id: UUID, playlist_id: UUID) -> PlaylistRow:
        """Duplique une de mes playlists (importée ou non) en une playlist modifiable, « X (copie) »."""
        async with self._db.transaction() as tx:
            repo = PlaylistRepository(tx)
            source = await owned_playlist(repo, owner_id, playlist_id)
            copy_id = await repo.create(owner_id, f"{source.name} (copie)", forked_from=playlist_id)
            await repo.copy_items(playlist_id, copy_id)
            return await owned_playlist(repo, owner_id, copy_id)


async def owned_playlist(repo: PlaylistRepository, owner_id: UUID, playlist_id: UUID) -> PlaylistRow:
    """La playlist si elle est à moi ; sinon PlaylistMissingError (sans dire si elle existe)."""
    playlist = await repo.get_for_owner(owner_id, playlist_id)
    if playlist is None:
        raise PlaylistMissingError("Playlist inconnue")
    return playlist


async def editable_playlist(repo: PlaylistRepository, owner_id: UUID, playlist_id: UUID) -> PlaylistRow:
    """La playlist si elle est à moi et créée ici ; sinon PlaylistMissingError ou PlaylistReadOnlyError."""
    playlist = await owned_playlist(repo, owner_id, playlist_id)
    if playlist.source_provider is not None:
        raise PlaylistReadOnlyError("Playlist importée : duplique-la pour la modifier")
    return playlist
