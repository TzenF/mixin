"""File de tâches (Redis + arq) : l'API y dépose les analyses, le worker les exécute."""

from __future__ import annotations

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings


class TaskQueue:
    """Dépose des tâches dans Redis pour le worker arq."""

    def __init__(self, redis: ArqRedis) -> None:
        self._redis = redis

    @classmethod
    async def connect(cls, url: str) -> TaskQueue:
        """Se connecte à Redis à partir d'une URL redis://."""
        return cls(await create_pool(RedisSettings.from_dsn(url)))

    async def close(self) -> None:
        """Ferme la connexion à Redis."""
        await self._redis.aclose()

    async def enqueue_analysis(self, track_id: str) -> str | None:
        """Met l'analyse d'un morceau en file ; renvoie None si elle y est déjà."""
        # _job_id fixe : une analyse déjà en file pour ce morceau n'est pas dupliquée
        job = await self._redis.enqueue_job("analyze_track", track_id, _job_id=f"analyze:{track_id}")
        return job.job_id if job else None

    async def ping(self) -> bool:
        """Indique si Redis répond."""
        try:
            return bool(await self._redis.ping())
        except Exception:
            return False
