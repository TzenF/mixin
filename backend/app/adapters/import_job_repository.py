"""Accès au journal des imports (`import_job`)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from app.adapters.db import Queryable


class ImportJobRepository:
    """Ouverture et clôture des imports, avec leurs statistiques."""

    def __init__(self, db: Queryable) -> None:
        self._db = db

    async def start(self, user_id: UUID, kind: str) -> UUID:
        """Enregistre le début d'un import et renvoie son identifiant."""
        row = await self._db.fetch_one(
            "INSERT INTO import_job (user_id, kind) VALUES (%(user_id)s, %(kind)s::import_kind) RETURNING id",
            {"user_id": user_id, "kind": kind},
        )
        assert row is not None
        return row["id"]

    async def finish(self, job_id: UUID, status: str, stats: dict[str, Any]) -> None:
        """Clôt l'import avec son statut final ('done' ou 'failed') et ses statistiques."""
        await self._db.fetch_one(
            """UPDATE import_job SET status = %(status)s::job_status, stats = %(stats)s, finished_at = now()
               WHERE id = %(id)s""",
            {"id": job_id, "status": status, "stats": Jsonb(stats)},
        )
