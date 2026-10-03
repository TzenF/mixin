"""Service d'import testé avec un faux service musical (aucun appel réseau) et la vraie base."""

import uuid
from dataclasses import dataclass, field

import psycopg
import pytest

from app.adapters.db import Database
from app.adapters.playlist_repository import PlaylistRepository
from app.config import get_settings
from app.domain.music_provider import MusicProviderError, ProviderPlaylist, ProviderTrack
from app.services.playlist_import import PlaylistImporter
from tests.conftest import requires_services

pytestmark = [pytest.mark.anyio, requires_services]


@dataclass
class FakeProvider:
    """Faux service musical : renvoie les playlists qu'on lui donne."""

    playlists: dict[str, ProviderPlaylist]
    name: str = "spotify"

    async def get_user_playlists(self, access_token: str) -> list[ProviderPlaylist]:
        """Liste les playlists connues."""
        return list(self.playlists.values())

    async def get_playlist(self, access_token: str, playlist_id: str) -> ProviderPlaylist:
        """Renvoie la playlist demandée, ou lève l'erreur du service."""
        if playlist_id not in self.playlists:
            raise MusicProviderError("introuvable")
        return self.playlists[playlist_id]

    async def get_saved_tracks(self, access_token: str) -> list[ProviderTrack]:
        """Non utilisé ici."""
        return []

    async def create_playlist(self, access_token: str, name: str, track_ids: list[str]) -> str:
        """Non utilisé ici."""
        return ""


@dataclass
class FakeQueue:
    """Fausse file : note les morceaux mis en analyse."""

    enqueued: list[str] = field(default_factory=list)

    async def enqueue_analysis(self, track_id: str) -> str | None:
        """Note le morceau."""
        self.enqueued.append(track_id)
        return f"analyze:{track_id}"


def _track(prefix: str, n: int, isrc: bool = True, artists: list[str] | None = None) -> ProviderTrack:
    """Morceau de test n°n (identifiants préfixés pour le nettoyage)."""
    return ProviderTrack(
        external_id=f"{prefix}-sp{n}",
        title=f"{prefix} titre {n}",
        artists=artists if artists is not None else [f"{prefix} artiste {n}"],
        duration_ms=200_000,
        isrc=f"{prefix}{n:04d}" if isrc else None,
    )


def _importer(db: Database, *playlists: ProviderPlaylist) -> tuple[PlaylistImporter, FakeQueue]:
    """Importeur branché sur un faux service et une fausse file."""
    queue = FakeQueue()
    provider = FakeProvider({p.external_id: p for p in playlists})
    return PlaylistImporter(db, provider, queue), queue


def _count(sql: str, params: dict[str, object]) -> int:
    """Exécute un SELECT count(*) sur la vraie base."""
    with psycopg.connect(get_settings().database_url) as conn:
        row = conn.execute(sql, params).fetchone()
        assert row is not None
        return int(row[0])


def _tracks_with_prefix(prefix: str) -> int:
    """Nombre de morceaux de test en base."""
    return _count("SELECT count(*) FROM track WHERE title LIKE %(p)s", {"p": f"{prefix}%"})


async def test_import_creates_playlist_tracks_and_queues_them(
    db: Database, user_id: uuid.UUID, test_prefix: str
) -> None:
    tracks = [_track(test_prefix, n) for n in range(3)]
    importer, queue = _importer(db, ProviderPlaylist("pl1", "vib", 3, tracks))

    result = await importer.import_playlist(user_id, "jeton", "pl1")

    assert result.created and result.name == "vib"
    assert (result.stats.total, result.stats.new, result.stats.known, result.stats.skipped) == (3, 3, 0, 0)
    assert len(queue.enqueued) == result.stats.queued == 3
    ordered = await PlaylistRepository(db).track_ids(result.playlist_id)
    assert [str(t) for t in ordered] == queue.enqueued  # ordre de la playlist d'origine conservé
    assert _count(
        "SELECT count(*) FROM import_job WHERE id = %(id)s AND status = 'done' AND (stats->>'new')::int = 3",
        {"id": result.import_job_id},
    )


async def test_reimport_updates_same_playlist_without_duplicates(
    db: Database, user_id: uuid.UUID, test_prefix: str
) -> None:
    first = ProviderPlaylist("pl1", "vib", 2, [_track(test_prefix, 0), _track(test_prefix, 1)])
    importer, queue = _importer(db, first)
    before = await importer.import_playlist(user_id, "jeton", "pl1")

    # La playlist a changé chez Spotify : renommée, un titre ajouté, ordre inversé
    second = ProviderPlaylist(
        "pl1", "vib v2", 3, [_track(test_prefix, 2), _track(test_prefix, 1), _track(test_prefix, 0)]
    )
    importer, queue = _importer(db, second)
    after = await importer.import_playlist(user_id, "jeton", "pl1")

    assert after.playlist_id == before.playlist_id and not after.created
    assert (after.stats.new, after.stats.known) == (1, 2)
    assert len(queue.enqueued) == 1  # seul le nouveau morceau est mis en file
    assert _tracks_with_prefix(test_prefix) == 3
    assert _count("SELECT count(*) FROM playlist WHERE owner_id = %(u)s", {"u": user_id}) == 1
    assert len(await PlaylistRepository(db).track_ids(after.playlist_id)) == 3


async def test_same_isrc_with_another_spotify_id_is_the_same_track(
    db: Database, user_id: uuid.UUID, test_prefix: str
) -> None:
    original = _track(test_prefix, 0)
    other_release = ProviderTrack(f"{test_prefix}-autre", "Autre sortie", [], None, original.isrc)
    importer, queue = _importer(db, ProviderPlaylist("pl1", "vib", 2, [original, other_release]))

    result = await importer.import_playlist(user_id, "jeton", "pl1")

    assert (result.stats.new, result.stats.known) == (1, 1)
    assert len(queue.enqueued) == 1
    assert _tracks_with_prefix(test_prefix) == 1


async def test_track_without_isrc_is_deduplicated_by_spotify_id(
    db: Database, user_id: uuid.UUID, test_prefix: str
) -> None:
    track = _track(test_prefix, 0, isrc=False)
    importer, _ = _importer(
        db, ProviderPlaylist("pl1", "a", 1, [track]), ProviderPlaylist("pl2", "b", 1, [track])
    )

    await importer.import_playlist(user_id, "jeton", "pl1")
    second = await importer.import_playlist(user_id, "jeton", "pl2")

    assert (second.stats.new, second.stats.known) == (0, 1)
    assert _tracks_with_prefix(test_prefix) == 1


async def test_tracks_without_id_are_skipped(db: Database, user_id: uuid.UUID, test_prefix: str) -> None:
    local = ProviderTrack(None, f"{test_prefix} fichier local", ["Moi"], None, None)
    importer, queue = _importer(db, ProviderPlaylist("pl1", "vib", 2, [local, _track(test_prefix, 0)]))

    result = await importer.import_playlist(user_id, "jeton", "pl1")

    assert (result.stats.total, result.stats.new, result.stats.skipped) == (2, 1, 1)
    assert len(queue.enqueued) == 1
    assert len(await PlaylistRepository(db).track_ids(result.playlist_id)) == 1


async def test_artists_are_shared_between_tracks(db: Database, user_id: uuid.UUID, test_prefix: str) -> None:
    artist = f"{test_prefix} Mau P"
    tracks = [_track(test_prefix, 0, artists=[artist]), _track(test_prefix, 1, artists=[artist.upper()])]
    importer, _ = _importer(db, ProviderPlaylist("pl1", "vib", 2, tracks))

    await importer.import_playlist(user_id, "jeton", "pl1")

    assert _count("SELECT count(*) FROM artist WHERE lower(name) = lower(%(n)s)", {"n": artist}) == 1


async def test_failed_import_is_recorded_and_writes_nothing(
    db: Database, user_id: uuid.UUID, test_prefix: str
) -> None:
    importer, queue = _importer(db)

    with pytest.raises(MusicProviderError):
        await importer.import_playlist(user_id, "jeton", "inconnue")

    assert _count(
        "SELECT count(*) FROM import_job WHERE user_id = %(u)s AND status = 'failed'", {"u": user_id}
    )
    assert _count("SELECT count(*) FROM playlist WHERE owner_id = %(u)s", {"u": user_id}) == 0
    assert queue.enqueued == []
