"""Cas d'usage « corriger un morceau » (BPM, tonalité) : corrections perso, sans écraser Essentia."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.adapters.analysis_repository import AnalysisRepository, PersonalCorrection
from app.adapters.db import Database
from app.domain.camelot import CamelotKey


class NoKeyToFlipError(Exception):
    """Le morceau n'a pas encore de tonalité : rien à inverser."""


async def flip_mode(db: Database, user_id: UUID, track_id: UUID) -> CamelotKey:
    """Inverse majeur/mineur de la tonalité affichée (même tonique) et l'enregistre comme correction perso.

    Erreur la plus fréquente d'Essentia : la tonique est juste, le mode est inversé. Inverser deux fois
    redonne la tonalité de départ.
    """
    async with db.transaction() as tx:
        analyses = AnalysisRepository(tx)
        current = await analyses.effective_key(track_id, user_id)
        if current is None:
            raise NoKeyToFlipError("Ce morceau n'a pas encore de tonalité")
        flipped = current.parallel()
        await analyses.save_personal_key(track_id, user_id, flipped)
    return flipped


# Bornes du BPM acceptées par la base (track_analysis.bpm CHECK).
BPM_MIN, BPM_MAX = 40.0, 250.0


@dataclass(frozen=True, slots=True)
class CorrectionChanges:
    """Champs à modifier : un champ absent de `fields` reste tel quel ; à None, sa correction est annulée."""

    fields: frozenset[str]
    bpm: float | None = None
    key: CamelotKey | None = None


async def correct(db: Database, user_id: UUID, track_id: UUID, changes: CorrectionChanges) -> None:
    """Corrige BPM et/ou tonalité pour cet utilisateur ; sans plus aucun champ corrigé, Essentia revient."""
    async with db.transaction() as tx:
        analyses = AnalysisRepository(tx)
        current = await analyses.personal_correction(track_id, user_id) or PersonalCorrection(None, None)
        corrected = PersonalCorrection(
            bpm=changes.bpm if "bpm" in changes.fields else current.bpm,
            key=changes.key if "key" in changes.fields else current.key,
        )
        if corrected.bpm is None and corrected.key is None:
            await analyses.delete_personal_correction(track_id, user_id)
        else:
            await analyses.save_personal_correction(track_id, user_id, corrected)
