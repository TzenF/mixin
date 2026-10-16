"""Analyse audio avec Essentia : BPM et tonalité d'un fichier.

Essentia n'est installé que dans l'image du worker : ce module ne doit être importé que par le worker
(jamais par l'API ni par les tests, qui tournent dans l'image `api`).
"""

from __future__ import annotations

from pathlib import Path

import essentia
import essentia.standard as es

from app.domain.audio_features import AudioFeatures
from app.domain.camelot import CamelotKey

essentia.log.infoActive = False
essentia.log.warningActive = False

SAMPLE_RATE = 44100
# Profil conçu pour la musique électronique : meilleur résultat mesuré pendant les spikes.
KEY_PROFILE = "edma"


class EssentiaAnalyzer:
    """Mesure le BPM et la tonalité d'un fichier audio."""

    version = f"essentia-{essentia.__version__}/{KEY_PROFILE}"

    def analyze(self, path: Path) -> AudioFeatures:
        """Analyse le fichier (bloquant et gourmand en CPU : à appeler hors de la boucle asyncio)."""
        audio = es.MonoLoader(filename=str(path), sampleRate=SAMPLE_RATE)()
        bpm, *_ = es.RhythmExtractor2013(method="multifeature")(audio)
        key, scale, strength = es.KeyExtractor(profileType=KEY_PROFILE, sampleRate=SAMPLE_RATE)(audio)
        return AudioFeatures(
            bpm=round(float(bpm), 1),
            key=CamelotKey.parse(f"{key}{'m' if scale == 'minor' else ''}"),
            key_confidence=min(max(float(strength), 0.0), 1.0),
        )
