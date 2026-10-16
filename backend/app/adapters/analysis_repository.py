"""Accès aux résultats d'analyse : tout le SQL qui concerne `track_analysis` passe par ici."""

from __future__ import annotations

from uuid import UUID

from app.adapters.db import Queryable
from app.domain.audio_features import AudioFeatures

# La cible du ON CONFLICT reprend exactement l'expression de l'index track_analysis_one_per_scope.
_SAVE_ESSENTIA_SQL = """
INSERT INTO track_analysis
    (track_id, source, bpm, camelot_num, camelot_letter, key_confidence, analyzer_version)
VALUES (%(track_id)s, 'essentia', %(bpm)s, %(num)s, %(letter)s, %(confidence)s, %(version)s)
ON CONFLICT (track_id, source, COALESCE(user_id, '00000000-0000-0000-0000-000000000000'))
DO UPDATE SET bpm = EXCLUDED.bpm,
              camelot_num = EXCLUDED.camelot_num,
              camelot_letter = EXCLUDED.camelot_letter,
              key_confidence = EXCLUDED.key_confidence,
              analyzer_version = EXCLUDED.analyzer_version,
              created_at = now()
"""


class AnalysisRepository:
    """Lecture et écriture des valeurs BPM / tonalité, une ligne par source."""

    def __init__(self, db: Queryable) -> None:
        self._db = db

    async def save_essentia(self, track_id: UUID, features: AudioFeatures, analyzer_version: str) -> None:
        """Enregistre la valeur Essentia du morceau (globale), en remplaçant l'éventuelle précédente."""
        await self._db.fetch_one(
            _SAVE_ESSENTIA_SQL,
            {
                "track_id": track_id,
                "bpm": features.bpm,
                "num": features.key.number,
                "letter": features.key.letter,
                "confidence": features.key_confidence,
                "version": analyzer_version,
            },
        )
