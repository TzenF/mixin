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
    spotify_redirect_uri: str = "http://127.0.0.1:8000/auth/spotify/callback"


@lru_cache
def get_settings() -> Settings:
    """Renvoie la configuration, lue une seule fois."""
    return Settings()
