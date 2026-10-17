"""Worker d'analyse (arq) : lancé avec `arq app.worker.main.WorkerSettings`.

Pour chaque morceau : extrait Deezer retrouvé par ISRC -> Essentia -> ligne `essentia` dans track_analysis.
Explorer : chaque jour (et à la demande), les sources Deezer sont recopiées dans le catalogue.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import httpx
from arq import Retry, cron
from arq.connections import RedisSettings

from app.adapters.db import Database
from app.adapters.deezer_client import DeezerClient, DeezerUnavailableError
from app.adapters.essentia_analyzer import EssentiaAnalyzer
from app.adapters.explore_repository import ExploreRepository
from app.adapters.queue import TaskQueue
from app.config import get_settings
from app.services.explore import ExploreSourceMissingError, ExploreSync
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
    ctx["queue"] = TaskQueue(ctx["redis"])
    ctx["explore"] = ExploreSync(ctx["db"], DeezerClient(ctx["http"]), ctx["queue"])
    # Sources ajoutées (migration ou utilisateur) mais jamais recopiées : on s'en occupe tout de suite.
    for source_id in await ExploreRepository(ctx["db"]).ids(never_synced_only=True):
        await ctx["queue"].enqueue_explore_sync(str(source_id))


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


async def sync_explore_source(ctx: dict[str, Any], source_id: str) -> str:
    """Recopie une source de l'Explorer depuis Deezer ; un échec est noté sur la source (réessai demain)."""
    explore: ExploreSync = ctx["explore"]
    try:
        result = await explore.sync(UUID(source_id))
    except ExploreSourceMissingError:
        return "not_found"
    except DeezerUnavailableError as e:
        log.warning("Synchronisation de la source %s impossible : %s", source_id, e)
        return "failed"
    log.info("Source %s : %s morceaux, %s nouveaux", source_id, result.total, result.new)
    return "done"


async def sync_all_explore_sources(ctx: dict[str, Any]) -> int:
    """Tâche quotidienne : met en file la synchronisation de toutes les sources ; renvoie leur nombre."""
    ids = await ExploreRepository(ctx["db"]).ids()
    for source_id in ids:
        await ctx["queue"].enqueue_explore_sync(str(source_id))
    return len(ids)


class WorkerSettings:
    """Configuration lue par arq : tâches disponibles, connexion Redis, parallélisme."""

    functions = [analyze_track, sync_explore_source]
    # Les tops changent chaque semaine : une mise à jour par jour suffit (une requête Deezer par source).
    cron_jobs = [cron(sync_all_explore_sources, hour={5}, minute={0})]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 2  # Essentia consomme du CPU : peu de tâches en parallèle
    max_tries = MAX_TRIES
    # Pas de résultat gardé dans Redis (le statut est dans track.analysis_status) : sinon arq refuse de
    # remettre en file le même _job_id pendant 1 h après la fin de l'analyse.
    keep_result = 0
