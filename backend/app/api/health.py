"""Route de santé : vérifie que la base et la file de tâches répondent."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from app.adapters.db import Database
from app.adapters.queue import TaskQueue
from app.api.deps import get_db, get_queue

router = APIRouter(tags=["health"])


class Health(BaseModel):
    """État de chaque service dont dépend l'API."""

    status: str
    database: bool
    queue: bool


@router.get("/health")
async def health(
    response: Response,
    db: Annotated[Database, Depends(get_db)],
    queue: Annotated[TaskQueue, Depends(get_queue)],
) -> Health:
    """Renvoie l'état des services ; HTTP 503 si l'un d'eux est en panne."""
    db_ok, queue_ok = await db.ping(), await queue.ping()
    ok = db_ok and queue_ok
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return Health(status="ok" if ok else "degraded", database=db_ok, queue=queue_ok)
