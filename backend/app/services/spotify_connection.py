"""Cas d'usage « connecter Spotify » : OAuth PKCE, création de l'utilisateur, jetons chiffrés."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from uuid import UUID

from app.adapters.db import Database
from app.adapters.oauth_state_store import OAuthStateStore
from app.adapters.spotify_auth import EXPIRY_MARGIN, SpotifyAuth, SpotifyAuthError, SpotifyTokens, pkce_pair
from app.adapters.spotify_provider import SpotifyProvider
from app.adapters.token_cipher import TokenCipher
from app.adapters.user_repository import UserRepository

PROVIDER = "spotify"


class SpotifyConnection:
    """Connecte un utilisateur via Spotify et fournit un jeton d'accès toujours valide."""

    def __init__(
        self,
        db: Database,
        auth: SpotifyAuth,
        provider: SpotifyProvider,
        states: OAuthStateStore,
        cipher: TokenCipher,
    ) -> None:
        self._db = db
        self._auth = auth
        self._provider = provider
        self._states = states
        self._cipher = cipher

    async def start_login(self) -> tuple[str, str]:
        """Prépare la connexion ; renvoie l'URL d'autorisation Spotify et le `state` à garder en cookie."""
        state = secrets.token_urlsafe(16)
        verifier, challenge = pkce_pair()
        await self._states.save(state, verifier)
        return self._auth.authorize_url(state, challenge), state

    async def complete_login(self, code: str, state: str) -> UUID:
        """Termine la connexion : échange le code, crée ou retrouve l'utilisateur, enregistre ses jetons."""
        verifier = await self._states.pop(state)
        if verifier is None:
            raise SpotifyAuthError("Connexion expirée ou déjà utilisée : recommence")
        tokens = await self._auth.exchange_code(code, verifier)
        profile = await self._provider.get_current_user(tokens.access_token)

        async with self._db.transaction() as tx:
            users = UserRepository(tx)
            user_id = await users.find_by_provider_account(PROVIDER, profile.id)
            if user_id is None:
                user_id = await users.create(profile.display_name)
            await users.save_music_account(
                user_id,
                PROVIDER,
                profile.id,
                self._cipher.encrypt(tokens.access_token),
                self._encrypt_optional(tokens.refresh_token),
                tokens.scopes,
                tokens.expires_at,
            )
        return user_id

    async def access_token(self, user_id: UUID) -> str:
        """Renvoie un jeton d'accès Spotify valide, rafraîchi d'abord s'il expire bientôt."""
        users = UserRepository(self._db)
        account = await users.get_music_account(user_id, PROVIDER)
        if account is None:
            raise SpotifyAuthError("Aucun compte Spotify associé : connecte-toi avec Spotify")
        if account.expires_at and account.expires_at - EXPIRY_MARGIN > datetime.now(UTC):
            return self._cipher.decrypt(account.access_token_enc)
        if account.refresh_token_enc is None:
            raise SpotifyAuthError("Session Spotify expirée : reconnecte-toi")

        tokens: SpotifyTokens = await self._auth.refresh(self._cipher.decrypt(account.refresh_token_enc))
        await users.update_tokens(
            user_id,
            PROVIDER,
            self._cipher.encrypt(tokens.access_token),
            self._encrypt_optional(tokens.refresh_token),
            tokens.expires_at,
        )
        return tokens.access_token

    def _encrypt_optional(self, token: str | None) -> bytes | None:
        """Chiffre le jeton s'il y en a un."""
        return self._cipher.encrypt(token) if token else None
