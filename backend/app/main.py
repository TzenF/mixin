"""Point d'entrée de l'API : assemble la configuration, les adaptateurs et les routes."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.adapters.db import Database
from app.adapters.queue import TaskQueue
from app.api import health, tracks
from app.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Construit l'application FastAPI (une fonction pour pouvoir en créer une par test)."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Ouvre la base et la file au démarrage, les ferme à l'arrêt."""
        app.state.db = await Database.connect(settings.database_url)
        app.state.queue = await TaskQueue.connect(settings.redis_url)
        try:
            yield
        finally:
            await app.state.queue.close()
            await app.state.db.close()

    app = FastAPI(title="DJ Platform API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(tracks.router)
    return app


app = create_app()
