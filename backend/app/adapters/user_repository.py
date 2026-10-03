"""Accès aux utilisateurs et à leurs comptes musicaux associés (`app_user`, `music_account`)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.adapters.db import Queryable


@dataclass(frozen=True, slots=True)
class UserRow:
    """Un utilisateur de l'application."""

    id: UUID
    display_name: str
    email: str | None


@dataclass(frozen=True, slots=True)
class MusicAccountRow:
    """Le compte musical associé d'un utilisateur, jetons encore chiffrés."""

    provider_user_id: str
    access_token_enc: bytes
    refresh_token_enc: bytes | None
    expires_at: datetime | None


class UserRepository:
    """Lecture et écriture des utilisateurs et de leurs comptes musicaux."""

    def __init__(self, db: Queryable) -> None:
        self._db = db

    async def get(self, user_id: UUID) -> UserRow | None:
        """Renvoie l'utilisateur, ou None s'il n'existe pas."""
        row = await self._db.fetch_one(
            "SELECT id, display_name, email FROM app_user WHERE id = %(id)s", {"id": user_id}
        )
        return UserRow(**row) if row else None

    async def create(self, display_name: str) -> UUID:
        """Crée un utilisateur (sans email ni mot de passe) et renvoie son identifiant."""
        row = await self._db.fetch_one(
            "INSERT INTO app_user (display_name) VALUES (%(name)s) RETURNING id", {"name": display_name}
        )
        assert row is not None
        return row["id"]

    async def find_by_provider_account(self, provider: str, provider_user_id: str) -> UUID | None:
        """Renvoie l'utilisateur associé à ce compte du service musical, ou None."""
        row = await self._db.fetch_one(
            """SELECT user_id FROM music_account
               WHERE provider = %(provider)s::music_provider AND provider_user_id = %(puid)s""",
            {"provider": provider, "puid": provider_user_id},
        )
        return row["user_id"] if row else None

    async def save_music_account(
        self,
        user_id: UUID,
        provider: str,
        provider_user_id: str,
        access_token_enc: bytes,
        refresh_token_enc: bytes | None,
        scopes: list[str],
        expires_at: datetime,
    ) -> None:
        """Associe le compte musical à l'utilisateur, ou met à jour ses jetons s'il l'est déjà."""
        await self._db.fetch_one(
            """INSERT INTO music_account
                   (user_id, provider, provider_user_id, access_token_enc, refresh_token_enc,
                    scopes, expires_at)
               VALUES (%(user_id)s, %(provider)s::music_provider, %(puid)s, %(access)s, %(refresh)s,
                       %(scopes)s, %(expires_at)s)
               ON CONFLICT (user_id, provider) DO UPDATE SET
                   provider_user_id  = EXCLUDED.provider_user_id,
                   access_token_enc  = EXCLUDED.access_token_enc,
                   refresh_token_enc = COALESCE(EXCLUDED.refresh_token_enc, music_account.refresh_token_enc),
                   scopes            = EXCLUDED.scopes,
                   expires_at        = EXCLUDED.expires_at""",
            {
                "user_id": user_id,
                "provider": provider,
                "puid": provider_user_id,
                "access": access_token_enc,
                "refresh": refresh_token_enc,
                "scopes": scopes,
                "expires_at": expires_at,
            },
        )

    async def get_music_account(self, user_id: UUID, provider: str) -> MusicAccountRow | None:
        """Renvoie le compte musical associé de l'utilisateur pour ce service, ou None."""
        row = await self._db.fetch_one(
            """SELECT provider_user_id, access_token_enc, refresh_token_enc, expires_at
               FROM music_account WHERE user_id = %(user_id)s AND provider = %(provider)s::music_provider""",
            {"user_id": user_id, "provider": provider},
        )
        return MusicAccountRow(**row) if row else None

    async def update_tokens(
        self,
        user_id: UUID,
        provider: str,
        access_token_enc: bytes,
        refresh_token_enc: bytes | None,
        expires_at: datetime,
    ) -> None:
        """Enregistre des jetons rafraîchis (le refresh_token n'est remplacé que s'il en vient un nouveau)."""
        await self._db.fetch_one(
            """UPDATE music_account SET
                   access_token_enc  = %(access)s,
                   refresh_token_enc = COALESCE(%(refresh)s, refresh_token_enc),
                   expires_at        = %(expires_at)s
               WHERE user_id = %(user_id)s AND provider = %(provider)s::music_provider""",
            {
                "user_id": user_id,
                "provider": provider,
                "access": access_token_enc,
                "refresh": refresh_token_enc,
                "expires_at": expires_at,
            },
        )
