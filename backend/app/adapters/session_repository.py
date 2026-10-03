"""Accès aux sessions de connexion (`user_session`) : seule l'empreinte du jeton est stockée."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.adapters.db import Queryable


class SessionRepository:
    """Création, lecture et suppression des sessions."""

    def __init__(self, db: Queryable) -> None:
        self._db = db

    async def create(self, token_hash: bytes, user_id: UUID, expires_at: datetime) -> None:
        """Enregistre une session, et fait le ménage dans celles qui ont expiré."""
        await self._db.fetch_one("DELETE FROM user_session WHERE expires_at < now()")
        await self._db.fetch_one(
            """INSERT INTO user_session (token_hash, user_id, expires_at)
               VALUES (%(hash)s, %(user_id)s, %(expires_at)s)""",
            {"hash": token_hash, "user_id": user_id, "expires_at": expires_at},
        )

    async def find_user_id(self, token_hash: bytes) -> UUID | None:
        """Renvoie l'utilisateur d'une session encore valide, ou None."""
        row = await self._db.fetch_one(
            "SELECT user_id FROM user_session WHERE token_hash = %(hash)s AND expires_at > now()",
            {"hash": token_hash},
        )
        return row["user_id"] if row else None

    async def delete(self, token_hash: bytes) -> None:
        """Supprime une session (déconnexion)."""
        await self._db.fetch_one("DELETE FROM user_session WHERE token_hash = %(hash)s", {"hash": token_hash})
