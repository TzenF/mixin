"""Dépendances FastAPI partagées par les routes."""

from typing import Annotated
from uuid import UUID

import httpx
from fastapi import Cookie, Depends, HTTPException, Request, status

from app.adapters.db import Database
from app.adapters.oauth_state_store import OAuthStateStore
from app.adapters.queue import TaskQueue
from app.adapters.spotify_auth import SpotifyAuth
from app.adapters.spotify_provider import SpotifyProvider
from app.adapters.token_cipher import TokenCipher
from app.adapters.track_repository import TrackRepository
from app.config import Settings
from app.services.playlist_import import PlaylistImporter
from app.services.sessions import SessionService
from app.services.spotify_connection import SpotifyConnection

SESSION_COOKIE = "session"


def get_settings(request: Request) -> Settings:
    """Fournit la configuration avec laquelle l'application a été créée."""
    return request.app.state.settings


def get_db(request: Request) -> Database:
    """Fournit la base ouverte au démarrage de l'application."""
    return request.app.state.db


def get_queue(request: Request) -> TaskQueue:
    """Fournit la file de tâches ouverte au démarrage de l'application."""
    return request.app.state.queue


def get_http_client(request: Request) -> httpx.AsyncClient:
    """Fournit le client HTTP partagé pour les API externes."""
    return request.app.state.http


def get_track_repository(db: Annotated[Database, Depends(get_db)]) -> TrackRepository:
    """Fournit le dépôt des morceaux."""
    return TrackRepository(db)


def get_session_service(
    db: Annotated[Database, Depends(get_db)], settings: Annotated[Settings, Depends(get_settings)]
) -> SessionService:
    """Fournit le service des sessions de connexion."""
    return SessionService(db, settings.session_days)


async def get_current_user_id(
    sessions: Annotated[SessionService, Depends(get_session_service)],
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> UUID:
    """Renvoie l'utilisateur connecté ; HTTP 401 si aucune session valide."""
    user_id = await sessions.user_id(session) if session else None
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Non connecté")
    return user_id


def get_spotify_provider(client: Annotated[httpx.AsyncClient, Depends(get_http_client)]) -> SpotifyProvider:
    """Fournit l'adaptateur de la Web API Spotify."""
    return SpotifyProvider(client)


def get_spotify_connection(
    request: Request,
    db: Annotated[Database, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
    provider: Annotated[SpotifyProvider, Depends(get_spotify_provider)],
) -> SpotifyConnection:
    """Fournit le service de connexion Spotify (erreur claire si la configuration est incomplète)."""
    states: OAuthStateStore = request.app.state.oauth_states
    return SpotifyConnection(
        db,
        SpotifyAuth(client, settings.spotify_client_id, settings.spotify_redirect_uri),
        provider,
        states,
        TokenCipher(settings.token_encryption_key),
    )


def get_playlist_importer(
    db: Annotated[Database, Depends(get_db)],
    provider: Annotated[SpotifyProvider, Depends(get_spotify_provider)],
    queue: Annotated[TaskQueue, Depends(get_queue)],
) -> PlaylistImporter:
    """Fournit le service d'import de playlists Spotify."""
    return PlaylistImporter(db, provider, queue)
