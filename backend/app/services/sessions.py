"""Sessions de connexion : un jeton aléatoire dans le cookie, son empreinte en base."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.adapters.db import Queryable
from app.adapters.session_repository import SessionRepository


class SessionService:
    """Ouvre, retrouve et ferme les sessions des utilisateurs."""

    def __init__(self, db: Queryable, days: int) -> None:
        self._sessions = SessionRepository(db)
        self._days = days

    async def open(self, user_id: UUID) -> str:
        """Ouvre une session et renvoie le jeton à mettre dans le cookie."""
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(days=self._days)
        await self._sessions.create(_hash(token), user_id, expires_at)
        return token

    async def user_id(self, token: str) -> UUID | None:
        """Renvoie l'utilisateur de la session, ou None si le jeton est inconnu ou expiré."""
        return await self._sessions.find_user_id(_hash(token))

    async def close(self, token: str) -> None:
        """Ferme la session (déconnexion)."""
        await self._sessions.delete(_hash(token))

    @property
    def max_age_seconds(self) -> int:
        """Durée de vie d'une session, pour l'attribut Max-Age du cookie."""
        return self._days * 24 * 3600


def _hash(token: str) -> bytes:
    """Empreinte SHA-256 du jeton : une fuite de la base ne donne pas de session utilisable."""
    return hashlib.sha256(token.encode()).digest()
