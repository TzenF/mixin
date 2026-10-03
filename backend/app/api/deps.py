"""Dépendances FastAPI partagées par les routes."""

from typing import Annotated

from fastapi import Depends, Request

from app.adapters.db import Database
from app.adapters.queue import TaskQueue
from app.adapters.track_repository import TrackRepository


def get_db(request: Request) -> Database:
    """Fournit la base ouverte au démarrage de l'application."""
    return request.app.state.db


def get_queue(request: Request) -> TaskQueue:
    """Fournit la file de tâches ouverte au démarrage de l'application."""
    return request.app.state.queue


def get_track_repository(db: Annotated[Database, Depends(get_db)]) -> TrackRepository:
    """Fournit le dépôt des morceaux."""
    return TrackRepository(db)
