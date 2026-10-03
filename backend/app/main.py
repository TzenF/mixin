"""Point d'entrée de l'API : assemble la configuration, les adaptateurs et les routes."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.adapters.db import Database
from app.adapters.oauth_state_store import OAuthStateStore
from app.adapters.queue import TaskQueue
from app.api import auth, health, spotify, tracks
from app.api.errors import register_error_handlers
from app.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Construit l'application FastAPI (une fonction pour pouvoir en créer une par test)."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Ouvre la base, la file et les clients externes au démarrage, les ferme à l'arrêt."""
        app.state.settings = settings
        app.state.db = await Database.connect(settings.database_url)
        app.state.queue = await TaskQueue.connect(settings.redis_url)
        app.state.oauth_states = OAuthStateStore.connect(settings.redis_url)
        app.state.http = httpx.AsyncClient(timeout=30)
        try:
            yield
        finally:
            await app.state.http.aclose()
            await app.state.oauth_states.close()
            await app.state.queue.close()
            await app.state.db.close()

    app = FastAPI(title="DJ Platform API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(spotify.router)
    app.include_router(tracks.router)
    return app


app = create_app()
