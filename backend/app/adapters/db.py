"""Accès PostgreSQL : pool de connexions asynchrone (psycopg 3)."""

from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


class Database:
    """Point d'accès unique à PostgreSQL ; chaque ligne est renvoyée sous forme de dict."""

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, url: str) -> Database:
        """Ouvre le pool de connexions (sans attendre que la base soit joignable)."""
        pool = AsyncConnectionPool(url, min_size=1, max_size=10, open=False, kwargs={"row_factory": dict_row})
        await pool.open(wait=False)
        return cls(pool)

    async def close(self) -> None:
        """Ferme toutes les connexions du pool."""
        await self._pool.close()

    async def fetch_all(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Exécute une requête et renvoie toutes les lignes."""
        async with self._pool.connection() as conn:
            cur = await conn.execute(query, params)
            return await cur.fetchall()

    async def fetch_one(self, query: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Exécute une requête et renvoie la première ligne, ou None."""
        async with self._pool.connection() as conn:
            cur = await conn.execute(query, params)
            return await cur.fetchone()

    async def ping(self) -> bool:
        """Indique si la base répond."""
        try:
            row = await self.fetch_one("SELECT 1 AS ok")
            return row is not None and row["ok"] == 1
        except Exception:
            return False
