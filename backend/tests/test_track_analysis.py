"""Service d'analyse testé avec un faux Deezer et un faux Essentia (aucun appel réseau) et la vraie base."""

import uuid
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from app.adapters.db import Database
from app.adapters.deezer_client import DeezerTrack, DeezerUnavailableError
from app.adapters.track_repository import TrackRepository
from app.domain.audio_features import AudioFeatures
from app.domain.camelot import CamelotKey
from app.services.track_analysis import TrackAnalyzer
from tests.conftest import requires_services

pytestmark = [pytest.mark.anyio, requires_services]


@dataclass
class FakeDeezer:
    """Faux Deezer : connaît quelques ISRC, ou ne répond pas du tout."""

    tracks: dict[str, DeezerTrack] = field(default_factory=dict)
    down: bool = False

    async def find_by_isrc(self, isrc: str) -> DeezerTrack | None:
        """Renvoie le morceau connu pour cet ISRC."""
        if self.down:
            raise DeezerUnavailableError("quota")
        return self.tracks.get(isrc)

    async def download(self, url: str, dest: Path) -> None:
        """Écrit un faux extrait."""
        dest.write_bytes(b"faux mp3")


@dataclass
class FakeEssentia:
    """Faux analyseur : renvoie la mesure donnée (ou plante) et note le fichier reçu."""

    result: AudioFeatures | None
    version: str = "fake-1"
    seen: list[Path] = field(default_factory=list)

    def analyze(self, path: Path) -> AudioFeatures:
        """Vérifie que l'extrait est bien là, puis renvoie la mesure."""
        assert path.read_bytes() == b"faux mp3"
        self.seen.append(path)
        if self.result is None:
            raise RuntimeError("fichier illisible")
        return self.result


FEATURES = AudioFeatures(bpm=128.4, key=CamelotKey(5, "A"), key_confidence=0.95)


async def _track(db: Database, prefix: str, isrc: bool = True) -> uuid.UUID:
    """Crée un morceau de test (titre et ISRC préfixés pour le nettoyage)."""
    return await TrackRepository(db).create(f"{prefix} titre", None, prefix if isrc else None)


async def _status(db: Database, track_id: uuid.UUID) -> str:
    """Statut d'analyse du morceau."""
    row = await db.fetch_one(
        "SELECT analysis_status::text AS s FROM track WHERE id = %(id)s", {"id": track_id}
    )
    assert row is not None
    return row["s"]


async def _essentia_rows(db: Database, track_id: uuid.UUID) -> list[dict[str, object]]:
    """Lignes Essentia du morceau."""
    return await db.fetch_all(
        """SELECT bpm::float AS bpm, camelot_num, camelot_letter, analyzer_version
           FROM track_analysis WHERE track_id = %(id)s AND source = 'essentia'""",
        {"id": track_id},
    )


async def test_analysis_saves_features_and_deletes_the_preview(db: Database, test_prefix: str) -> None:
    track_id = await _track(db, test_prefix)
    essentia = FakeEssentia(FEATURES)
    deezer = FakeDeezer({test_prefix: DeezerTrack(f"{test_prefix}-dz", "https://cdn/x.mp3")})

    assert await TrackAnalyzer(db, deezer, essentia).analyze(track_id) == "done"

    assert await _status(db, track_id) == "done"
    assert await _essentia_rows(db, track_id) == [
        {"bpm": 128.4, "camelot_num": 5, "camelot_letter": "A", "analyzer_version": "fake-1"}
    ]
    assert await TrackRepository(db).find_by_external_id("deezer", f"{test_prefix}-dz") == track_id
    assert not essentia.seen[0].exists()  # on ne garde jamais l'audio


async def test_reanalysis_replaces_the_essentia_value(db: Database, test_prefix: str) -> None:
    track_id = await _track(db, test_prefix)
    deezer = FakeDeezer({test_prefix: DeezerTrack("1", "https://cdn/x.mp3")})
    await TrackAnalyzer(db, deezer, FakeEssentia(FEATURES)).analyze(track_id)

    better = AudioFeatures(bpm=130.0, key=CamelotKey(8, "B"), key_confidence=0.9)
    await TrackAnalyzer(db, deezer, FakeEssentia(better, version="fake-2")).analyze(track_id)

    assert await _essentia_rows(db, track_id) == [
        {"bpm": 130.0, "camelot_num": 8, "camelot_letter": "B", "analyzer_version": "fake-2"}
    ]


async def test_no_isrc_or_unknown_to_deezer_means_no_preview(db: Database, test_prefix: str) -> None:
    without_isrc = await _track(db, test_prefix, isrc=False)
    unknown = await _track(db, test_prefix)
    analyzer = TrackAnalyzer(db, FakeDeezer(), FakeEssentia(FEATURES))

    assert await analyzer.analyze(without_isrc) == "no_preview"
    assert await analyzer.analyze(unknown) == "no_preview"
    assert await _status(db, unknown) == "no_preview"


async def test_track_without_preview_on_deezer(db: Database, test_prefix: str) -> None:
    track_id = await _track(db, test_prefix)
    deezer = FakeDeezer({test_prefix: DeezerTrack("1", None)})

    assert await TrackAnalyzer(db, deezer, FakeEssentia(FEATURES)).analyze(track_id) == "no_preview"


async def test_analysis_error_marks_failed_and_deletes_the_preview(db: Database, test_prefix: str) -> None:
    track_id = await _track(db, test_prefix)
    essentia = FakeEssentia(None)
    deezer = FakeDeezer({test_prefix: DeezerTrack("1", "https://cdn/x.mp3")})

    assert await TrackAnalyzer(db, deezer, essentia).analyze(track_id) == "failed"

    assert await _status(db, track_id) == "failed"
    assert await _essentia_rows(db, track_id) == []
    assert not essentia.seen[0].exists()


async def test_deezer_down_leaves_the_track_pending(db: Database, test_prefix: str) -> None:
    track_id = await _track(db, test_prefix)

    with pytest.raises(DeezerUnavailableError):
        await TrackAnalyzer(db, FakeDeezer(down=True), FakeEssentia(FEATURES)).analyze(track_id)

    assert await _status(db, track_id) == "pending"


async def test_unknown_track(db: Database) -> None:
    analyzer = TrackAnalyzer(db, FakeDeezer(), FakeEssentia(FEATURES))
    assert await analyzer.analyze(uuid.uuid4()) == "not_found"
