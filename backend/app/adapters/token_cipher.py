"""Chiffrement des jetons des services musicaux avant leur stockage en base (Fernet)."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class TokenCipherError(Exception):
    """La clé de chiffrement manque, est invalide, ou ne correspond pas au jeton stocké."""


class TokenCipher:
    """Chiffre et déchiffre des jetons avec la clé TOKEN_ENCRYPTION_KEY."""

    def __init__(self, key: str) -> None:
        if not key:
            raise TokenCipherError("TOKEN_ENCRYPTION_KEY manquante (voir .env.example)")
        try:
            self._fernet = Fernet(key)
        except ValueError as e:
            raise TokenCipherError("TOKEN_ENCRYPTION_KEY invalide : ce doit être une clé Fernet") from e

    def encrypt(self, token: str) -> bytes:
        """Chiffre un jeton ; le résultat va dans une colonne bytea."""
        return self._fernet.encrypt(token.encode())

    def decrypt(self, data: bytes) -> str:
        """Déchiffre un jeton lu en base."""
        try:
            return self._fernet.decrypt(bytes(data)).decode()
        except InvalidToken as e:
            raise TokenCipherError("Jeton illisible : la clé de chiffrement a-t-elle changé ?") from e
