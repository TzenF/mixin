"""Traduit les erreurs des services musicaux et du chiffrement en réponses HTTP lisibles."""

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.adapters.spotify_auth import SpotifyAuthError
from app.adapters.spotify_provider import SpotifyApiError
from app.adapters.token_cipher import TokenCipherError
from app.domain.music_provider import MusicProviderError, PlaylistNotFoundError

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


def register_error_handlers(app: FastAPI) -> None:
    """Branche les gestionnaires d'erreurs sur l'application."""
    app.add_exception_handler(MusicProviderError, _music_provider_error)
    app.add_exception_handler(TokenCipherError, _cipher_error)
