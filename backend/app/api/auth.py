"""Connexion : OAuth Spotify, déconnexion, utilisateur courant.

Le navigateur passe par le proxy Angular (/api/auth/...) : front et API partagent la même origine,
donc la redirection relative vers « /spotify » ramène sur le front.
"""

import logging
import urllib.parse
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.adapters.db import Database
from app.adapters.oauth_state_store import TTL_SECONDS
from app.adapters.user_repository import UserRepository
from app.api.deps import (
    SESSION_COOKIE,
    get_current_user_id,
    get_db,
    get_session_service,
    get_settings,
    get_spotify_connection,
)
from app.config import Settings
from app.domain.music_provider import MusicProviderError
from app.services.sessions import SessionService
from app.services.spotify_connection import SpotifyConnection

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

STATE_COOKIE = "oauth_state"
AFTER_LOGIN = "/spotify"


@router.get("/spotify/login")
async def spotify_login(
    connection: Annotated[SpotifyConnection, Depends(get_spotify_connection)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedirectResponse:
    """Redirige vers la page d'autorisation de Spotify."""
    url, state = await connection.start_login()
    resp = RedirectResponse(url, status_code=status.HTTP_302_FOUND)
    # SameSite=Lax (pas Strict) : le cookie doit revenir avec la redirection depuis accounts.spotify.com
    resp.set_cookie(
        STATE_COOKIE,
        state,
        max_age=TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
    )
    return resp


@router.get("/spotify/callback")
async def spotify_callback(
    connection: Annotated[SpotifyConnection, Depends(get_spotify_connection)],
    sessions: Annotated[SessionService, Depends(get_session_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    oauth_state: Annotated[str | None, Cookie(alias=STATE_COOKIE)] = None,
) -> RedirectResponse:
    """Retour de Spotify : ouvre une session puis renvoie vers /spotify (avec ?spotify_error=… si échec)."""
    if error or not code or not state:
        return _login_failed(error or "missing_code")
    if state != oauth_state:
        return _login_failed("invalid_state")
    try:
        user_id = await connection.complete_login(code, state)
    except MusicProviderError as e:
        log.warning("Connexion Spotify échouée : %s", e)
        return _login_failed("spotify")

    resp = RedirectResponse(AFTER_LOGIN, status_code=status.HTTP_302_FOUND)
    resp.delete_cookie(STATE_COOKIE)
    resp.set_cookie(
        SESSION_COOKIE,
        await sessions.open(user_id),
        max_age=sessions.max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
    )
    return resp


def _login_failed(reason: str) -> RedirectResponse:
    """Redirige vers la page Spotify du front avec la raison de l'échec."""
    query = urllib.parse.urlencode({"spotify_error": reason})
    resp = RedirectResponse(f"{AFTER_LOGIN}?{query}", status.HTTP_302_FOUND)
    resp.delete_cookie(STATE_COOKIE)
    return resp


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    sessions: Annotated[SessionService, Depends(get_session_service)],
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> Response:
    """Ferme la session courante et efface le cookie."""
    if session:
        await sessions.close(session)
    resp = Response(status_code=status.HTTP_204_NO_CONTENT)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


class Me(BaseModel):
    """L'utilisateur connecté."""

    id: UUID
    display_name: str
    spotify_connected: bool


@router.get("/me")
async def me(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    db: Annotated[Database, Depends(get_db)],
) -> Me:
    """Renvoie l'utilisateur connecté ; HTTP 401 si personne ne l'est."""
    users = UserRepository(db)
    user = await users.get(user_id)
    assert user is not None  # la session est supprimée en cascade avec l'utilisateur
    return Me(
        id=user.id,
        display_name=user.display_name,
        spotify_connected=await users.get_music_account(user_id, "spotify") is not None,
    )
