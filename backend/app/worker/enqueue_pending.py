"""Met en file d'analyse tous les morceaux en attente : `make analyze-pending`.

Utile pour les morceaux importés sans que l'analyse ait pu être mise en file (Redis vidé, panne…).
Tourne dans le conteneur `api` : n'importe pas `worker.main`, qui a besoin d'Essentia.
"""

from __future__ import annotations

import asyncio

from app.adapters.db import Database
from app.adapters.queue import TaskQueue
from app.adapters.track_repository import TrackRepository
from app.config import get_settings
from app.services.track_analysis import enqueue_pending


async def main() -> None:
    """Ouvre la base et la file, met les morceaux en attente en file, puis affiche le bilan."""
    settings = get_settings()
    db = await Database.connect(settings.database_url)
    queue = await TaskQueue.connect(settings.redis_url)
    try:
        queued, already_queued = await enqueue_pending(TrackRepository(db), queue)
    finally:
        await queue.close()
        await db.close()
    print(f"{queued} morceau(x) mis en file d'analyse, {already_queued} déjà en file.")


if __name__ == "__main__":
    asyncio.run(main())
