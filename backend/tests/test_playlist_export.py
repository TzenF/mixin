"""Export d'une playlist vers Spotify : faux Spotify en mémoire, vraie base."""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.adapters.db import Database
from app.adapters.spotify_auth import SpotifyAuthError
from app.api.deps import get_spotify_connection, get_spotify_provider
from app.config import get_settings
from app.domain.music_provider import ProviderPlaylist, ProviderTrack
from app.services.playlist_editor import PlaylistMissingError, PlaylistReadOnlyError
from app.services.playlist_export import PlaylistExporter
from tests.conftest import requires_services

pytestmark = requires_services


@dataclass
class FakeSpotify:
    """Faux Spotify : garde en mémoire les playlists de l'utilisateur (id -> morceaux)."""

    name: str = "spotify"
    playlists: dict[str, list[str]] = field(default_factory=dict)
    descriptions: dict[str, tuple[str, str]] = field(default_factory=dict)
    replaced: list[str] = field(default_factory=list)
    by_isrc: dict[str, str] = field(default_factory=dict)
    searched: list[str] = field(default_factory=list)

    async def find_track_by_isrc(self, access_token: str, isrc: str) -> str | None:
        """Morceau connu par ISRC (note chaque recherche)."""
        self.searched.append(isrc)
        return self.by_isrc.get(isrc)

    async def get_user_playlists(self, access_token: str) -> list[ProviderPlaylist]:
        """Playlists encore présentes chez l'utilisateur."""
        return [
            ProviderPlaylist(external_id=k, name=k, track_count=len(v)) for k, v in self.playlists.items()
        ]

    async def get_playlist(self, access_token: str, playlist_id: str) -> ProviderPlaylist:
        """Non utilisé ici."""
        raise NotImplementedError

    async def get_saved_tracks(self, access_token: str) -> list[ProviderTrack]:
        """Non utilisé ici."""
        return []

    async def create_playlist(
        self, access_token: str, name: str, description: str, track_ids: list[str]
    ) -> str:
        """Crée une playlist en mémoire."""
        playlist_id = f"sp{len(self.descriptions) + 1}"
        self.playlists[playlist_id] = list(track_ids)
        self.descriptions[playlist_id] = (name, description)
        return playlist_id

    async def replace_playlist_items(self, access_token: str, playlist_id: str, track_ids: list[str]) -> None:
        """Remplace le contenu en mémoire."""
        self.playlists[playlist_id] = list(track_ids)
        self.replaced.append(playlist_id)

    def playlist_url(self, playlist_id: str) -> str:
        """Adresse factice."""
        return f"https://open.spotify.com/playlist/{playlist_id}"


@dataclass
class FakeConnection:
    """Fausse connexion Spotify : un jeton, ou une session Spotify expirée."""

    expired: bool = False

    async def access_token(self, user_id: uuid.UUID) -> str:
        """Renvoie un jeton, ou lève l'erreur « reconnecte-toi »."""
        if self.expired:
            raise SpotifyAuthError("Session Spotify expirée : reconnecte-toi")
        return "jeton"


@pytest.fixture
def setlists(user_id: uuid.UUID, test_prefix: str) -> Iterator[dict[str, str]]:
    """Ma playlist « Set » (B, A sur Spotify ; C absent de Spotify), une importée et celle d'un autre."""
    p = test_prefix
    other = uuid.uuid4()
    with psycopg.connect(get_settings().database_url, autocommit=True) as conn:

        def track(title: str, spotify_id: str | None) -> uuid.UUID:
            """Crée un morceau, avec un identifiant Spotify s'il est donné."""
            tid = uuid.uuid4()
            conn.execute("INSERT INTO track (id, title) VALUES (%s, %s)", (tid, f"{p} {title}"))
            if spotify_id:
                conn.execute(
                    """INSERT INTO track_external_id (track_id, provider, external_id)
                       VALUES (%s, 'spotify', %s)""",
                    (tid, f"{p}-{spotify_id}"),
                )
            return tid

        def playlist(owner: uuid.UUID, name: str, tracks: list[uuid.UUID], imported: bool = False) -> str:
            """Crée une playlist avec ces morceaux, dans l'ordre."""
            row = conn.execute(
                """INSERT INTO playlist (owner_id, name, source_provider, source_external_id)
                   VALUES (%s, %s, %s, %s) RETURNING id""",
                (owner, f"{p} {name}", "spotify" if imported else None, f"{p}-imp" if imported else None),
            ).fetchone()
            assert row is not None
            for position, tid in enumerate(tracks):
                conn.execute(
                    "INSERT INTO playlist_item (playlist_id, track_id, position) VALUES (%s, %s, %s)",
                    (row[0], tid, position),
                )
            return str(row[0])

        a, b, c = track("A", "spA"), track("B", "spB"), track("C", None)
        conn.execute("INSERT INTO app_user (id, display_name) VALUES (%s, 'Autre')", (other,))
        yield {
            "set": playlist(user_id, "Set", [b, c, a]),
            "imported": playlist(user_id, "Importée", [a], imported=True),
            "other": playlist(other, "Pas à moi", [a]),
        }
        conn.execute("DELETE FROM app_user WHERE id = %s", (other,))


@pytest.mark.anyio
async def test_first_export_creates_a_playlist_in_order_and_skips_tracks_not_on_spotify(
    db: Database, setlists: dict[str, str], user_id: uuid.UUID, test_prefix: str
) -> None:
    spotify = FakeSpotify()

    result = await PlaylistExporter(db, spotify).export(user_id, uuid.UUID(setlists["set"]), "jeton")

    assert (result.created, result.exported, result.skipped) == (True, 2, 1)
    assert spotify.playlists[result.external_playlist_id] == [f"{test_prefix}-spB", f"{test_prefix}-spA"]
    name, description = spotify.descriptions[result.external_playlist_id]
    assert name == f"{test_prefix} Set" and description.startswith("Exportée depuis DJ Platform le ")
    assert result.url == f"https://open.spotify.com/playlist/{result.external_playlist_id}"


@pytest.mark.anyio
async def test_reexport_updates_the_same_spotify_playlist(
    db: Database, setlists: dict[str, str], user_id: uuid.UUID, test_prefix: str
) -> None:
    spotify = FakeSpotify()
    exporter = PlaylistExporter(db, spotify)
    first = await exporter.export(user_id, uuid.UUID(setlists["set"]), "jeton")

    second = await exporter.export(user_id, uuid.UUID(setlists["set"]), "jeton")

    assert (second.created, second.external_playlist_id) == (False, first.external_playlist_id)
    assert spotify.replaced == [first.external_playlist_id]
    assert len(spotify.playlists) == 1
    assert second.exported_at >= first.exported_at


@pytest.mark.anyio
async def test_reexport_creates_a_new_playlist_if_deleted_on_spotify(
    db: Database, setlists: dict[str, str], user_id: uuid.UUID
) -> None:
    spotify = FakeSpotify()
    exporter = PlaylistExporter(db, spotify)
    first = await exporter.export(user_id, uuid.UUID(setlists["set"]), "jeton")
    del spotify.playlists[first.external_playlist_id]  # supprimée (plus suivie) côté Spotify

    second = await exporter.export(user_id, uuid.UUID(setlists["set"]), "jeton")

    assert second.created and second.external_playlist_id != first.external_playlist_id
    assert spotify.replaced == []  # on ne remplit pas une playlist devenue invisible


@pytest.mark.anyio
async def test_imported_and_foreign_playlists_are_refused(
    db: Database, setlists: dict[str, str], user_id: uuid.UUID
) -> None:
    exporter = PlaylistExporter(db, FakeSpotify())
    with pytest.raises(PlaylistReadOnlyError):
        await exporter.export(user_id, uuid.UUID(setlists["imported"]), "jeton")
    with pytest.raises(PlaylistMissingError):
        await exporter.export(user_id, uuid.UUID(setlists["other"]), "jeton")


@pytest.mark.anyio
async def test_tracks_without_spotify_id_are_found_by_isrc_once(
    db: Database, user_id: uuid.UUID, test_prefix: str
) -> None:
    p = test_prefix
    with psycopg.connect(get_settings().database_url, autocommit=True) as conn:
        found, missing = uuid.uuid4(), uuid.uuid4()  # venus de l'Explorer : pas d'identifiant Spotify
        conn.execute(
            "INSERT INTO track (id, title, isrc) VALUES (%s, %s, %s), (%s, %s, %s)",
            (found, f"{p} trouvé", f"{p}001", missing, f"{p} introuvable", f"{p}002"),
        )
        row = conn.execute(
            "INSERT INTO playlist (owner_id, name) VALUES (%s, %s) RETURNING id", (user_id, f"{p} Explorer")
        ).fetchone()
        assert row is not None
        for position, tid in enumerate([found, missing, found]):
            conn.execute(
                "INSERT INTO playlist_item (playlist_id, track_id, position) VALUES (%s, %s, %s)",
                (row[0], tid, position),
            )
    spotify = FakeSpotify(by_isrc={f"{p}001": f"{p}-spF"})
    exporter = PlaylistExporter(db, spotify)

    first = await exporter.export(user_id, row[0], "jeton")

    assert (first.exported, first.skipped) == (2, 1)
    assert spotify.playlists[first.external_playlist_id] == [f"{p}-spF", f"{p}-spF"]
    assert spotify.searched == [f"{p}001", f"{p}002"]  # une recherche par ISRC
    with psycopg.connect(get_settings().database_url) as conn:
        saved = conn.execute(
            "SELECT track_id FROM track_external_id WHERE provider = 'spotify' AND external_id = %s",
            (f"{p}-spF",),
        ).fetchone()
    assert saved == (found,)  # gardé : plus besoin de le chercher

    await exporter.export(user_id, row[0], "jeton")
    assert spotify.searched == [f"{p}001", f"{p}002", f"{p}002"]  # seul l'introuvable est recherché


def _with_fake_spotify(client: TestClient, connection: FakeConnection | None = None) -> FakeSpotify:
    """Remplace Spotify (API et connexion) par des faux dans l'application de test."""
    spotify = FakeSpotify()
    client.app.dependency_overrides[get_spotify_provider] = lambda: spotify
    client.app.dependency_overrides[get_spotify_connection] = lambda: connection or FakeConnection()
    return spotify


def test_export_route_and_detail(logged_in_client: TestClient, setlists: dict[str, str]) -> None:
    _with_fake_spotify(logged_in_client)
    assert logged_in_client.get(f"/playlists/{setlists['set']}").json()["spotify_export"] is None

    resp = logged_in_client.post(f"/playlists/{setlists['set']}/export/spotify")
    assert resp.status_code == 200
    body = resp.json()
    assert (body["created"], body["exported"], body["skipped"]) == (True, 2, 1)

    export = logged_in_client.get(f"/playlists/{setlists['set']}").json()["spotify_export"]
    assert export["url"] == body["url"]
    assert logged_in_client.post(f"/playlists/{setlists['set']}/export/spotify").json()["created"] is False


def test_export_route_errors(logged_in_client: TestClient, setlists: dict[str, str]) -> None:
    _with_fake_spotify(logged_in_client)
    assert logged_in_client.post(f"/playlists/{setlists['imported']}/export/spotify").status_code == 409
    assert logged_in_client.post(f"/playlists/{setlists['other']}/export/spotify").status_code == 404

    _with_fake_spotify(logged_in_client, FakeConnection(expired=True))
    expired = logged_in_client.post(f"/playlists/{setlists['set']}/export/spotify")
    assert expired.status_code == 401 and "reconnecte" in expired.json()["detail"]


def test_export_requires_a_session(client: TestClient) -> None:
    assert client.post(f"/playlists/{uuid.uuid4()}/export/spotify").status_code == 401
