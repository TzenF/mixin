"""Accès PostgreSQL : pool de connexions asynchrone (psycopg 3)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Protocol

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

Row = dict[str, Any]


class Queryable(Protocol):
    """Ce dont un dépôt a besoin : la base elle-même, ou une transaction en cours."""

    async def fetch_all(self, query: str, params: dict[str, Any] | None = None) -> list[Row]:
        """Exécute une requête et renvoie toutes les lignes."""
        ...

    async def fetch_one(self, query: str, params: dict[str, Any] | None = None) -> Row | None:
        """Exécute une requête et renvoie la première ligne, ou None."""
        ...


class Transaction:
    """Requêtes exécutées sur une même connexion, validées ensemble ou annulées ensemble."""

    def __init__(self, conn: AsyncConnection[Row]) -> None:
        self._conn = conn

    async def fetch_all(self, query: str, params: dict[str, Any] | None = None) -> list[Row]:
        """Exécute une requête dans la transaction et renvoie toutes les lignes."""
        cur = await self._conn.execute(query, params)
        return await cur.fetchall() if cur.description else []

    async def fetch_one(self, query: str, params: dict[str, Any] | None = None) -> Row | None:
        """Exécute une requête dans la transaction et renvoie la première ligne, ou None."""
        cur = await self._conn.execute(query, params)
        return await cur.fetchone() if cur.description else None


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

    async def fetch_all(self, query: str, params: dict[str, Any] | None = None) -> list[Row]:
        """Exécute une requête et renvoie toutes les lignes (tableau vide si la requête n'en renvoie pas)."""
        async with self.transaction() as tx:
            return await tx.fetch_all(query, params)

    async def fetch_one(self, query: str, params: dict[str, Any] | None = None) -> Row | None:
        """Exécute une requête et renvoie la première ligne, ou None."""
        async with self.transaction() as tx:
            return await tx.fetch_one(query, params)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Transaction]:
        """Ouvre une transaction : validée à la sortie du bloc, annulée si une exception en sort."""
        async with self._pool.connection() as conn, conn.transaction():
            yield Transaction(conn)

    async def ping(self) -> bool:
        """Indique si la base répond."""
        try:
            row = await self.fetch_one("SELECT 1 AS ok")
            return row is not None and row["ok"] == 1
        except Exception:
            return False
