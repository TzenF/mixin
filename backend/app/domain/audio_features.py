"""Résultat d'une analyse audio : tempo et tonalité d'un morceau."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.camelot import CamelotKey


@dataclass(frozen=True, slots=True)
class AudioFeatures:
    """BPM et tonalité mesurés sur un extrait, avec la confiance dans la tonalité (0 à 1)."""

    bpm: float
    key: CamelotKey
    key_confidence: float
