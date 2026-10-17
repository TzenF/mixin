"""Traduit les erreurs des services (musique, chiffrement, playlists) en réponses HTTP lisibles."""

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.adapters.deezer_client import DeezerUnavailableError
from app.adapters.spotify_auth import SpotifyAuthError
from app.adapters.spotify_provider import SpotifyApiError
from app.adapters.token_cipher import TokenCipherError
from app.domain.music_provider import MusicProviderError, PlaylistNotFoundError
from app.services.playlist_editor import (
    OrderMismatchError,
    PlaylistMissingError,
    PlaylistReadOnlyError,
    TrackMissingError,
)
from app.services.preview import PreviewUnavailableError

log = logging.getLogger(__name__)


def _status_for(exc: MusicProviderError) -> int:
    """Code HTTP à renvoyer pour une erreur de service musical."""
    if isinstance(exc, PlaylistNotFoundError):
        return status.HTTP_404_NOT_FOUND
    if isinstance(exc, SpotifyAuthError) or (isinstance(exc, SpotifyApiError) and exc.status_code == 401):
        return status.HTTP_401_UNAUTHORIZED
    return status.HTTP_502_BAD_GATEWAY


async def _music_provider_error(request: Request, exc: Exception) -> JSONResponse:
    """Réponse pour une erreur de service musical : 404, 401 (à reconnecter) ou 502."""
    assert isinstance(exc, MusicProviderError)
    code = _status_for(exc)
    if code == status.HTTP_502_BAD_GATEWAY:
        log.warning("Erreur du service musical : %s", exc)
    return JSONResponse({"detail": str(exc)}, status_code=code)


async def _cipher_error(request: Request, exc: Exception) -> JSONResponse:
    """Réponse pour une clé de chiffrement absente ou invalide (erreur de configuration)."""
    log.error("Chiffrement des jetons : %s", exc)
    return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


async def _not_found(request: Request, exc: Exception) -> JSONResponse:
    """Réponse 404 : playlist (pas à moi ou inexistante) ou morceau inconnu."""
    return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)


async def _read_only(request: Request, exc: Exception) -> JSONResponse:
    """Réponse 409 : playlist importée, à dupliquer pour la modifier."""
    return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_409_CONFLICT)


async def _stale_order(request: Request, exc: Exception) -> JSONResponse:
    """Réponse 422 : l'ordre envoyé ne correspond plus au contenu de la playlist."""
    return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT)


async def _no_preview(request: Request, exc: Exception) -> JSONResponse:
    """Réponse 404 : pas d'extrait pour ce morceau, avec la raison (`reason`)."""
    assert isinstance(exc, PreviewUnavailableError)
    return JSONResponse({"detail": str(exc), "reason": exc.reason}, status_code=status.HTTP_404_NOT_FOUND)


async def _deezer_down(request: Request, exc: Exception) -> JSONResponse:
    """Réponse 503 : Deezer ne répond pas pour l'instant (sans détail : une URL signée pourrait fuiter)."""
    log.warning("Deezer indisponible : %s", exc.__class__.__name__)
    return JSONResponse(
        {"detail": "Deezer est indisponible pour l'instant : réessaie dans un moment"},
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def register_error_handlers(app: FastAPI) -> None:
    """Branche les gestionnaires d'erreurs sur l'application."""
    app.add_exception_handler(MusicProviderError, _music_provider_error)
    app.add_exception_handler(TokenCipherError, _cipher_error)
    app.add_exception_handler(PlaylistMissingError, _not_found)
    app.add_exception_handler(TrackMissingError, _not_found)
    app.add_exception_handler(PlaylistReadOnlyError, _read_only)
    app.add_exception_handler(OrderMismatchError, _stale_order)
    app.add_exception_handler(PreviewUnavailableError, _no_preview)
    app.add_exception_handler(DeezerUnavailableError, _deezer_down)
