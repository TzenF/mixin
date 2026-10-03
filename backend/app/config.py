"""Configuration lue depuis les variables d'environnement (voir .env.example)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Réglages de l'application ; chaque champ peut être surchargé par une variable d'environnement."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://dj:dj@localhost:5432/dj"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: list[str] = ["http://localhost:4200"]

    spotify_client_id: str = ""
    # Passe par le proxy Angular : front et API partagent la même origine, donc le cookie de session.
    spotify_redirect_uri: str = "http://127.0.0.1:4200/api/auth/spotify/callback"

    # Clé Fernet qui chiffre les jetons des services musicaux en base (voir .env.example).
    token_encryption_key: str = ""
    session_days: int = 30
    # True dès que l'application est servie en HTTPS ; False en dev (http://127.0.0.1).
    session_cookie_secure: bool = False


@lru_cache
def get_settings() -> Settings:
    """Renvoie la configuration, lue une seule fois."""
    return Settings()
