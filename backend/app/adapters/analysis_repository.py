"""Accès aux résultats d'analyse : tout le SQL qui concerne `track_analysis` passe par ici."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.adapters.db import Queryable
from app.domain.audio_features import AudioFeatures
from app.domain.camelot import CamelotKey

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

# Correction perso de la tonalité : seules ses colonnes de tonalité changent (un BPM corrigé est gardé).
_SAVE_PERSONAL_KEY_SQL = """
INSERT INTO track_analysis (track_id, source, user_id, created_by, camelot_num, camelot_letter)
VALUES (%(track_id)s, 'manual', %(user_id)s, %(user_id)s, %(num)s, %(letter)s)
ON CONFLICT (track_id, source, COALESCE(user_id, '00000000-0000-0000-0000-000000000000'))
DO UPDATE SET camelot_num = EXCLUDED.camelot_num,
              camelot_letter = EXCLUDED.camelot_letter,
              created_at = now()
"""

# Correction perso complète (BPM et tonalité), qui remplace la précédente.
_SAVE_PERSONAL_CORRECTION_SQL = """
INSERT INTO track_analysis (track_id, source, user_id, created_by, bpm, camelot_num, camelot_letter)
VALUES (%(track_id)s, 'manual', %(user_id)s, %(user_id)s, %(bpm)s, %(num)s, %(letter)s)
ON CONFLICT (track_id, source, COALESCE(user_id, '00000000-0000-0000-0000-000000000000'))
DO UPDATE SET bpm = EXCLUDED.bpm,
              camelot_num = EXCLUDED.camelot_num,
              camelot_letter = EXCLUDED.camelot_letter,
              created_at = now()
"""


@dataclass(frozen=True, slots=True)
class PersonalCorrection:
    """Correction perso d'un morceau : None = ce champ n'est pas corrigé (la valeur d'Essentia s'applique)."""

    bpm: float | None
    key: CamelotKey | None


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

    async def effective_key(self, track_id: UUID, user_id: UUID) -> CamelotKey | None:
        """Tonalité affichée à cet utilisateur (voir effective_features), ou None s'il n'y en a pas."""
        row = await self._db.fetch_one(
            """SELECT camelot_num, camelot_letter FROM effective_features(%(user_id)s::uuid)
               WHERE track_id = %(track_id)s AND camelot_num IS NOT NULL""",
            {"user_id": user_id, "track_id": track_id},
        )
        return CamelotKey(row["camelot_num"], row["camelot_letter"]) if row else None

    async def save_personal_key(self, track_id: UUID, user_id: UUID, key: CamelotKey) -> None:
        """Enregistre la tonalité corrigée par cet utilisateur (prioritaire pour lui)."""
        await self._db.fetch_one(
            _SAVE_PERSONAL_KEY_SQL,
            {"track_id": track_id, "user_id": user_id, "num": key.number, "letter": key.letter},
        )

    async def personal_correction(self, track_id: UUID, user_id: UUID) -> PersonalCorrection | None:
        """Correction perso de l'utilisateur pour ce morceau, ou None s'il n'en a pas."""
        row = await self._db.fetch_one(
            """SELECT bpm::float AS bpm, camelot_num, camelot_letter FROM track_analysis
               WHERE track_id = %(track_id)s AND source = 'manual' AND user_id = %(user_id)s""",
            {"track_id": track_id, "user_id": user_id},
        )
        if row is None:
            return None
        key = (
            CamelotKey(row["camelot_num"], row["camelot_letter"]) if row["camelot_num"] is not None else None
        )
        return PersonalCorrection(bpm=row["bpm"], key=key)

    async def save_personal_correction(
        self, track_id: UUID, user_id: UUID, correction: PersonalCorrection
    ) -> None:
        """Enregistre la correction perso (au moins un des deux champs) en remplaçant la précédente."""
        await self._db.fetch_one(
            _SAVE_PERSONAL_CORRECTION_SQL,
            {
                "track_id": track_id,
                "user_id": user_id,
                "bpm": correction.bpm,
                "num": correction.key.number if correction.key else None,
                "letter": correction.key.letter if correction.key else None,
            },
        )

    async def delete_personal_correction(self, track_id: UUID, user_id: UUID) -> None:
        """Supprime la correction perso : les autres sources (Essentia…) s'appliquent de nouveau."""
        await self._db.fetch_one(
            """DELETE FROM track_analysis
               WHERE track_id = %(track_id)s AND source = 'manual' AND user_id = %(user_id)s""",
            {"track_id": track_id, "user_id": user_id},
        )
