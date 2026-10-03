"""Mémoire courte de la connexion OAuth : garde le code_verifier PKCE entre /login et /callback (Redis)."""

from __future__ import annotations

from redis.asyncio import Redis

TTL_SECONDS = 600  # au-delà de 10 minutes, la connexion doit être recommencée


class OAuthStateStore:
    """Associe un `state` OAuth à son code_verifier PKCE, pour un usage unique."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @classmethod
    def connect(cls, url: str) -> OAuthStateStore:
        """Prépare la connexion à Redis à partir d'une URL redis:// (ouverte au premier appel)."""
        return cls(Redis.from_url(url))

    async def close(self) -> None:
        """Ferme la connexion à Redis."""
        await self._redis.aclose()

    async def save(self, state: str, verifier: str) -> None:
        """Mémorise le code_verifier associé à ce `state`."""
        await self._redis.set(_key(state), verifier, ex=TTL_SECONDS)

    async def pop(self, state: str) -> str | None:
        """Renvoie le code_verifier et l'efface (usage unique) ; None si inconnu ou expiré."""
        value = await self._redis.getdel(_key(state))
        return value.decode() if isinstance(value, bytes) else value


def _key(state: str) -> str:
    """Clé Redis d'un `state` OAuth."""
    return f"oauth:state:{state}"
