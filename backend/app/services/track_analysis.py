"""Cas d'usage « analyser un morceau » : extrait Deezer retrouvé par ISRC, puis BPM et tonalité.

L'extrait est écrit dans un dossier temporaire et supprimé dès l'analyse terminée : on ne garde que les
chiffres (jamais l'audio).
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Protocol
from uuid import UUID

from app.adapters.analysis_repository import AnalysisRepository
from app.adapters.db import Database
from app.adapters.deezer_client import DeezerTrack, DeezerUnavailableError
from app.adapters.track_repository import TrackRepository
from app.domain.audio_features import AudioFeatures

log = logging.getLogger(__name__)


class PreviewSource(Protocol):
    """Ce dont l'analyse a besoin pour obtenir un extrait audio."""

    async def find_by_isrc(self, isrc: str) -> DeezerTrack | None:
        """Cherche le morceau par ISRC."""
        ...

    async def download(self, url: str, dest: Path) -> None:
        """Télécharge l'extrait dans un fichier."""
        ...


class AudioAnalyzer(Protocol):
    """Ce dont l'analyse a besoin pour mesurer un fichier audio."""

    version: str

    def analyze(self, path: Path) -> AudioFeatures:
        """Mesure le BPM et la tonalité du fichier."""
        ...


class TrackAnalyzer:
    """Analyse un morceau et enregistre son BPM et sa tonalité."""

    def __init__(self, db: Database, previews: PreviewSource, analyzer: AudioAnalyzer) -> None:
        self._db = db
        self._previews = previews
        self._analyzer = analyzer

    async def analyze(self, track_id: UUID) -> str:
        """Analyse le morceau et renvoie son statut : done, no_preview, failed (ou not_found).

        Lève DeezerUnavailableError si Deezer ne répond pas : le morceau reste « pending » et la tâche
        peut être relancée.
        """
        tracks = TrackRepository(self._db)
        if not await tracks.exists(track_id):
            log.warning("Morceau %s introuvable", track_id)
            return "not_found"

        isrc = await tracks.get_isrc(track_id)
        found = await self._previews.find_by_isrc(isrc) if isrc else None
        if found is not None:
            await tracks.add_external_id(track_id, "deezer", found.deezer_id)
        if found is None or found.preview_url is None:
            await tracks.set_analysis_status(track_id, "no_preview")
            return "no_preview"

        try:
            features = await self._measure(found.preview_url)
            async with self._db.transaction() as tx:
                await AnalysisRepository(tx).save_essentia(track_id, features, self._analyzer.version)
                await TrackRepository(tx).set_analysis_status(track_id, "done")
        except DeezerUnavailableError:
            raise
        except Exception:
            log.exception("Analyse impossible pour %s", track_id)
            await tracks.set_analysis_status(track_id, "failed")
            return "failed"
        return "done"

    async def mark_failed(self, track_id: UUID) -> None:
        """Note l'échec définitif de l'analyse (par exemple, Deezer toujours indisponible)."""
        await TrackRepository(self._db).set_analysis_status(track_id, "failed")

    async def _measure(self, preview_url: str) -> AudioFeatures:
        """Télécharge l'extrait dans un dossier temporaire, l'analyse, puis le supprime."""
        with tempfile.TemporaryDirectory(prefix="analyse-") as tmp:
            path = Path(tmp) / "extrait.mp3"
            await self._previews.download(preview_url, path)
            # Essentia bloque le CPU plusieurs secondes : hors de la boucle, le worker reste réactif.
            return await asyncio.to_thread(self._analyzer.analyze, path)
