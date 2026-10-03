"""Worker d'analyse (arq) : lancé avec `arq app.worker.main.WorkerSettings`.

V1 : squelette. La tâche vérifie que le morceau existe et note son statut ;
l'analyse Essentia (code du test n°3) sera branchée ici à la prochaine étape.
"""

from __future__ import annotations

import logging
from typing import Any

from arq.connections import RedisSettings

from app.adapters.db import Database
from app.adapters.track_repository import TrackRepository
from app.config import get_settings

log = logging.getLogger("worker")
settings = get_settings()


async def startup(ctx: dict[str, Any]) -> None:
    """Ouvre la base au démarrage du worker."""
    ctx["db"] = await Database.connect(settings.database_url)


async def shutdown(ctx: dict[str, Any]) -> None:
    """Ferme la base à l'arrêt du worker."""
    await ctx["db"].close()


async def analyze_track(ctx: dict[str, Any], track_id: str) -> str:
    """Analyse un morceau (BPM, tonalité) et enregistre le résultat — squelette pour l'instant."""
    tracks = TrackRepository(ctx["db"])
    if not await tracks.exists(track_id):
        log.warning("Morceau %s introuvable", track_id)
        return "not_found"
    # Étapes à venir : extrait Deezer par ISRC -> Essentia -> INSERT INTO track_analysis
    log.info("Analyse demandée pour %s (ISRC %s)", track_id, await tracks.get_isrc(track_id))
    return "queued_stub"


class WorkerSettings:
    """Configuration lue par arq : tâches disponibles, connexion Redis, parallélisme."""

    functions = [analyze_track]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 2  # Essentia consomme du CPU : peu de tâches en parallèle
