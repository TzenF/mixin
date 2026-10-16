"""Worker d'analyse (arq) : lancé avec `arq app.worker.main.WorkerSettings`.

Pour chaque morceau : extrait Deezer retrouvé par ISRC -> Essentia -> ligne `essentia` dans track_analysis.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import httpx
from arq import Retry
from arq.connections import RedisSettings

from app.adapters.db import Database
from app.adapters.deezer_client import DeezerClient, DeezerUnavailableError
from app.adapters.essentia_analyzer import EssentiaAnalyzer
from app.config import get_settings
from app.services.track_analysis import TrackAnalyzer

log = logging.getLogger("worker")
settings = get_settings()

MAX_TRIES = 5
RETRY_DELAY_SECONDS = 30


async def startup(ctx: dict[str, Any]) -> None:
    """Ouvre la base et le client HTTP au démarrage du worker."""
    ctx["db"] = await Database.connect(settings.database_url)
    ctx["http"] = httpx.AsyncClient(timeout=30, follow_redirects=True)
    ctx["analyzer"] = TrackAnalyzer(ctx["db"], DeezerClient(ctx["http"]), EssentiaAnalyzer())


async def shutdown(ctx: dict[str, Any]) -> None:
    """Ferme le client HTTP et la base à l'arrêt du worker."""
    await ctx["http"].aclose()
    await ctx["db"].close()


async def analyze_track(ctx: dict[str, Any], track_id: str) -> str:
    """Analyse un morceau ; si Deezer est indisponible, réessaie plus tard, puis abandonne (failed)."""
    analyzer: TrackAnalyzer = ctx["analyzer"]
    try:
        return await analyzer.analyze(UUID(track_id))
    except DeezerUnavailableError as e:
        if ctx["job_try"] >= MAX_TRIES:
            log.warning("Abandon de l'analyse de %s après %s essais : %s", track_id, MAX_TRIES, e)
            await analyzer.mark_failed(UUID(track_id))
            return "failed"
        log.info("Deezer indisponible pour %s (%s), nouvel essai plus tard", track_id, e)
        raise Retry(defer=RETRY_DELAY_SECONDS * ctx["job_try"]) from e


class WorkerSettings:
    """Configuration lue par arq : tâches disponibles, connexion Redis, parallélisme."""

    functions = [analyze_track]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 2  # Essentia consomme du CPU : peu de tâches en parallèle
    max_tries = MAX_TRIES
