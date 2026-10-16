"""Cas d'usage « corriger la tonalité » : corrections perso, qui n'écrasent jamais les autres sources."""

from __future__ import annotations

from uuid import UUID

from app.adapters.analysis_repository import AnalysisRepository
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
