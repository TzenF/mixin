"""Configuration lue depuis les variables d'environnement (voir .env.example)."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Mot de passe de la base de dev (docker-compose.yml) : interdit en production.
DEV_DATABASE_CREDENTIALS = "dj:dj@"


class Settings(BaseSettings):
    """Réglages de l'application ; chaque champ peut être surchargé par une variable d'environnement."""

    # hide_input_in_errors : une erreur de configuration ne recopie pas les valeurs (secrets) dans les logs.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    # « production » refuse de démarrer avec des réglages de dev (voir _check_production).
    environment: Literal["development", "production"] = "development"

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

    @property
    def is_production(self) -> bool:
        """Indique si l'application tourne en production."""
        return self.environment == "production"

    @model_validator(mode="after")
    def _check_production(self) -> Self:
        """En production, refuse de démarrer avec un réglage de dev (et liste tout ce qui manque)."""
        if not self.is_production:
            return self
        problems = []
        if not self.session_cookie_secure:
            problems.append("SESSION_COOKIE_SECURE doit valoir true (cookie envoyé en HTTPS seulement)")
        if not self.token_encryption_key:
            problems.append("TOKEN_ENCRYPTION_KEY est vide")
        if not self.spotify_redirect_uri.startswith("https://"):
            problems.append("SPOTIFY_REDIRECT_URI doit être en https://")
        if DEV_DATABASE_CREDENTIALS in self.database_url:
            problems.append("DATABASE_URL utilise le mot de passe de dev")
        if problems:
            raise ValueError("Réglages de dev en production :\n- " + "\n- ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    """Renvoie la configuration, lue une seule fois."""
    return Settings()
