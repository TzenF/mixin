"""Explorer : synchronisation des sources (faux Deezer, vraie base) et routes associées."""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Annotated

import psycopg
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.adapters.db import Database
from app.adapters.deezer_client import DeezerPlaylist, DeezerUnavailableError
from app.api.deps import get_db, get_explore_sync
from app.config import get_settings
from app.domain.music_provider import ProviderTrack
from app.services.explore import ExploreSourceMissingError, ExploreSync, InvalidSourceError
from tests.conftest import requires_services

pytestmark = requires_services


@dataclass
class FakeDeezer:
    """Faux Deezer : la playlist renvoie ce qu'on lui donne (None = inconnue), ou Deezer est en panne."""

    tracks: list[ProviderTrack] | None = None
    down: bool = False
    details: DeezerPlaylist | None = None
    short_links: dict[str, str] = field(default_factory=dict)
    asked: list[str] = field(default_factory=list)

    async def playlist(self, playlist_id: str) -> DeezerPlaylist | None:
        """Détails de la playlist (note l'identifiant demandé)."""
        self.asked.append(playlist_id)
        return self.details

    async def resolve_short_link(self, url: str) -> str | None:
        """Destination d'un lien court connu."""
        return self.short_links.get(url)

    async def playlist_tracks(self, playlist_id: str) -> list[ProviderTrack] | None:
        """Morceaux de la playlist."""
        if self.down:
            raise DeezerUnavailableError("quota")
        return self.tracks


@dataclass
class FakeQueue:
    """Fausse file : note les morceaux mis en analyse."""

    queued: list[str] = field(default_factory=list)

    async def enqueue_analysis(self, track_id: str) -> str | None:
        """Note le morceau."""
        self.queued.append(track_id)
        return track_id


def _track(prefix: str, n: int) -> ProviderTrack:
    """Morceau Deezer de test (identifiant et ISRC préfixés pour le nettoyage)."""
    return ProviderTrack(
        external_id=f"{prefix}-dz{n}",
        title=f"{prefix} titre {n}",
        artists=[f"{prefix} artiste"],
        duration_ms=180_000,
        isrc=f"{prefix}{n:03d}",
    )


@pytest.fixture
def source(test_prefix: str) -> Iterator[str]:
    """Une source de test (supprimée ensuite, avec son classement)."""
    with psycopg.connect(get_settings().database_url, autocommit=True) as conn:
        row = conn.execute(
            """INSERT INTO explore_source (provider, external_id, title, curator)
               VALUES ('deezer', %s, %s, 'Test') RETURNING id""",
            (f"{test_prefix}-src", f"{test_prefix} Top"),
        ).fetchone()
        assert row is not None
        yield str(row[0])
        conn.execute("DELETE FROM explore_source WHERE id = %s", (row[0],))


def _ranking(source_id: str) -> list[str]:
    """Titres de la source, dans l'ordre du classement."""
    with psycopg.connect(get_settings().database_url) as conn:
        rows = conn.execute(
            """SELECT t.title FROM explore_item ei JOIN track t ON t.id = ei.track_id
               WHERE ei.source_id = %s ORDER BY ei.position""",
            (source_id,),
        ).fetchall()
    return [r[0].split(" ", 1)[1] for r in rows]


@pytest.mark.anyio
async def test_sync_creates_tracks_ranks_them_and_queues_only_new_ones(
    db: Database, source: str, test_prefix: str
) -> None:
    queue = FakeQueue()
    deezer = FakeDeezer([_track(test_prefix, 1), _track(test_prefix, 2), _track(test_prefix, 3)])
    sync = ExploreSync(db, deezer, queue)

    first = await sync.sync(uuid.UUID(source))
    assert (first.total, first.new, len(queue.queued)) == (3, 3, 3)
    assert _ranking(source) == ["titre 1", "titre 2", "titre 3"]

    # Le top change : 3 monte, 1 sort, 4 entre
    deezer.tracks = [_track(test_prefix, 3), _track(test_prefix, 2), _track(test_prefix, 4)]
    second = await sync.sync(uuid.UUID(source))
    assert (second.total, second.new, len(queue.queued)) == (3, 1, 4)  # seul 4 est nouveau
    assert _ranking(source) == ["titre 3", "titre 2", "titre 4"]
    with psycopg.connect(get_settings().database_url) as conn:
        kept = conn.execute(
            "SELECT count(*) FROM track WHERE title = %s", (f"{test_prefix} titre 1",)
        ).fetchone()
    assert kept == (1,)  # sorti du top mais toujours dans le catalogue


@pytest.mark.anyio
async def test_sync_reuses_a_track_known_by_isrc_and_ignores_duplicates(
    db: Database, source: str, test_prefix: str
) -> None:
    with psycopg.connect(get_settings().database_url, autocommit=True) as conn:
        conn.execute(  # déjà là, importé de Spotify par exemple
            "INSERT INTO track (title, isrc) VALUES (%s, %s)", (f"{test_prefix} déjà là", f"{test_prefix}001")
        )
    queue = FakeQueue()
    tracks = [_track(test_prefix, 1), _track(test_prefix, 2), _track(test_prefix, 1)]

    result = await ExploreSync(db, FakeDeezer(tracks), queue).sync(uuid.UUID(source))

    assert (result.total, result.new) == (2, 1)
    assert _ranking(source) == ["déjà là", "titre 2"]


@pytest.mark.anyio
async def test_failures_are_noted_and_keep_the_previous_ranking(
    db: Database, source: str, test_prefix: str
) -> None:
    await ExploreSync(db, FakeDeezer([_track(test_prefix, 1)]), FakeQueue()).sync(uuid.UUID(source))

    with pytest.raises(DeezerUnavailableError):
        await ExploreSync(db, FakeDeezer(down=True), FakeQueue()).sync(uuid.UUID(source))
    await ExploreSync(db, FakeDeezer(None), FakeQueue()).sync(uuid.UUID(source))  # playlist disparue

    assert _ranking(source) == ["titre 1"]
    with psycopg.connect(get_settings().database_url) as conn:
        row = conn.execute("SELECT last_error FROM explore_source WHERE id = %s", (source,)).fetchone()
    assert row is not None and row[0] == "Playlist introuvable chez Deezer"


def test_sources_and_their_tracks_through_the_catalog(
    logged_in_client: TestClient, source: str, test_prefix: str, user_id: uuid.UUID
) -> None:
    with psycopg.connect(get_settings().database_url, autocommit=True) as conn:
        ids = []
        for n in (1, 2):
            row = conn.execute(
                "INSERT INTO track (title, isrc) VALUES (%s, %s) RETURNING id",
                (f"{test_prefix} titre {n}", f"{test_prefix}{n:03d}"),
            ).fetchone()
            assert row is not None
            ids.append(row[0])
        conn.execute(
            "INSERT INTO explore_item (source_id, track_id, position) VALUES (%s, %s, 0), (%s, %s, 1)",
            (source, ids[1], source, ids[0]),
        )
        conn.execute("INSERT INTO favorite (user_id, track_id) VALUES (%s, %s)", (user_id, ids[0]))

    mine = {s["id"]: s for s in logged_in_client.get("/explore/sources").json()}[source]
    assert (mine["track_count"], mine["analysed_count"], mine["pending_count"], mine["removable"]) == (
        2,
        0,
        2,
        False,
    )

    body = logged_in_client.get("/tracks", params={"source": source, "scope": "all", "sort": "rank"}).json()
    assert [(i["title"], i["rank"], i["mine"]) for i in body["items"]] == [
        (f"{test_prefix} titre 2", 1, False),
        (f"{test_prefix} titre 1", 2, True),  # en favori : à moi
    ]
    new = logged_in_client.get("/tracks", params={"source": source, "scope": "new"}).json()
    assert [i["title"] for i in new["items"]] == [f"{test_prefix} titre 2"]


def test_refresh_queues_the_sync(logged_in_client: TestClient, source: str) -> None:
    resp = logged_in_client.post(f"/explore/sources/{source}/refresh")
    assert resp.status_code == 202 and resp.json()["queued"] is True
    assert (
        logged_in_client.post(f"/explore/sources/{source}/refresh").json()["queued"] is False
    )  # déjà en file
    assert logged_in_client.post(f"/explore/sources/{uuid.uuid4()}/refresh").status_code == 404


def test_explore_requires_a_session(client: TestClient) -> None:
    assert client.get("/explore/sources").status_code == 401
    assert client.post(f"/explore/sources/{uuid.uuid4()}/refresh").status_code == 401
    assert client.post("/explore/sources", json={"link": "1109890291"}).status_code == 401
    assert client.delete(f"/explore/sources/{uuid.uuid4()}").status_code == 401


@pytest.fixture
def cleanup_sources(test_prefix: str) -> Iterator[None]:
    """Efface les sources ajoutées par le test (identifiant Deezer préfixé)."""
    yield
    with psycopg.connect(get_settings().database_url, autocommit=True) as conn:
        conn.execute("DELETE FROM explore_source WHERE external_id LIKE %s", (f"{test_prefix}%",))


def _details(prefix: str, *, public: bool = True, size: int = 50) -> DeezerPlaylist:
    """Playlist Deezer de test."""
    return DeezerPlaylist(f"{prefix}-pl", f"{prefix} Ma playlist", "Quelqu'un", size, public)


@pytest.mark.anyio
@pytest.mark.usefixtures("cleanup_sources")
async def test_add_source_from_a_link_or_a_short_link_without_duplicates(
    db: Database, user_id: uuid.UUID, test_prefix: str
) -> None:
    short = "https://link.deezer.com/s/abc"
    deezer = FakeDeezer(
        details=_details(test_prefix),
        short_links={short: "https://www.deezer.com/playlist/1183071761?host=1&utm_source=user_sharing"},
    )
    explore = ExploreSync(db, deezer, FakeQueue())

    first = await explore.add_source(user_id, "https://www.deezer.com/fr/playlist/1183071761")
    again = await explore.add_source(user_id, short)

    assert first == again
    assert deezer.asked == ["1183071761", "1183071761"]
    with psycopg.connect(get_settings().database_url) as conn:
        row = conn.execute(
            "SELECT title, curator, added_by, last_synced_at FROM explore_source WHERE id = %s", (first,)
        ).fetchone()
    assert row == (f"{test_prefix} Ma playlist", "Quelqu'un", user_id, None)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("link", "details", "error"),
    [
        ("https://www.deezer.com/fr/track/2651012", "ok", InvalidSourceError),
        ("https://link.deezer.com/s/expire", "ok", InvalidSourceError),  # mène à deezer-links-404
        ("1183071761", "private", InvalidSourceError),
        ("1183071761", "huge", InvalidSourceError),
        ("1183071761", None, ExploreSourceMissingError),
    ],
)
async def test_add_source_refusals(
    db: Database, user_id: uuid.UUID, test_prefix: str, link: str, details: str | None, error: type[Exception]
) -> None:
    playlist = {
        "ok": _details(test_prefix),
        "private": _details(test_prefix, public=False),
        "huge": _details(test_prefix, size=2001),
        None: None,
    }[details]
    deezer = FakeDeezer(
        details=playlist,
        short_links={"https://link.deezer.com/s/expire": "https://www.deezer.com/deezer-links-404"},
    )
    with pytest.raises(error):
        await ExploreSync(db, deezer, FakeQueue()).add_source(user_id, link)


@pytest.mark.usefixtures("cleanup_sources")
def test_add_and_remove_a_source_through_the_api(
    logged_in_client: TestClient, user_id: uuid.UUID, test_prefix: str, source: str
) -> None:
    deezer = FakeDeezer(details=_details(test_prefix))

    def explore(db: Annotated[Database, Depends(get_db)]) -> ExploreSync:
        """Service de l'Explorer branché sur le faux Deezer (la base reste la vraie)."""
        return ExploreSync(db, deezer, FakeQueue())

    logged_in_client.app.dependency_overrides[get_explore_sync] = explore

    resp = logged_in_client.post("/explore/sources", json={"link": "https://www.deezer.com/playlist/42"})
    assert resp.status_code == 200
    added = resp.json()
    assert (added["title"], added["removable"], added["last_synced_at"]) == (
        f"{test_prefix} Ma playlist",
        True,
        None,
    )
    assert logged_in_client.post("/explore/sources", json={"link": "42"}).json()["id"] == added["id"]

    refused = logged_in_client.post("/explore/sources", json={"link": "https://open.spotify.com/playlist/1"})
    assert refused.status_code == 422 and "playlist Deezer" in refused.json()["detail"]
    assert logged_in_client.post("/explore/sources", json={"link": ""}).status_code == 422
    deezer.details = None
    assert logged_in_client.post("/explore/sources", json={"link": "43"}).status_code == 404

    assert logged_in_client.delete(f"/explore/sources/{source}").status_code == 404  # source par défaut
    assert logged_in_client.delete(f"/explore/sources/{added['id']}").status_code == 204
    assert logged_in_client.delete(f"/explore/sources/{added['id']}").status_code == 404
    ids = {s["id"] for s in logged_in_client.get("/explore/sources").json()}
    assert added["id"] not in ids and source in ids
