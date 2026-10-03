"""Fixtures des tests d'intégration.

Ils ont besoin de PostgreSQL (schéma chargé) et de Redis : `docker compose up -d db redis`.
S'ils ne sont pas joignables, les tests d'intégration sont ignorés plutôt qu'en échec.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator

import psycopg
import pytest
import redis
from fastapi.testclient import TestClient

from app.adapters.db import Database
from app.config import get_settings


def _services_up() -> bool:
    """Indique si PostgreSQL et Redis sont joignables."""
    settings = get_settings()
    try:
        psycopg.connect(settings.database_url, connect_timeout=2).close()
        redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2).ping()
        return True
    except Exception:
        return False


requires_services = pytest.mark.skipif(not _services_up(), reason="PostgreSQL/Redis indisponibles")


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Client HTTP de test, avec l'application réellement démarrée (base + file)."""
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def tracks() -> Iterator[dict[str, uuid.UUID]]:
    """Insère quelques morceaux (valeurs Essentia réelles) puis les supprime."""
    data = [
        ("Where Have You Been", 128.4, 5, "A", 0.95),
        ("Don't Wake Me Up", 130.1, 5, "A", 0.98),
        ("Von dutch", 129.7, 4, "A", 0.97),
        ("Dernière danse", 141.9, 5, "A", 0.89),
    ]
    ids: dict[str, uuid.UUID] = {}
    with psycopg.connect(get_settings().database_url, autocommit=True) as conn:
        for title, bpm, num, letter, conf in data:
            tid = uuid.uuid4()
            ids[title] = tid
            conn.execute("INSERT INTO track (id, title) VALUES (%s, %s)", (tid, title))
            conn.execute(
                """INSERT INTO track_analysis
                       (track_id, source, bpm, camelot_num, camelot_letter, key_confidence)
                   VALUES (%s, 'essentia', %s, %s, %s, %s)""",
                (tid, bpm, num, letter, conf),
            )
        yield ids
        conn.execute("DELETE FROM track WHERE id = ANY(%s)", (list(ids.values()),))


@pytest.fixture
def anyio_backend() -> str:
    """Tests asynchrones exécutés avec asyncio (plugin pytest d'anyio, déjà installé avec FastAPI)."""
    return "asyncio"


@pytest.fixture
async def db() -> AsyncIterator[Database]:
    """Base réelle, ouverte pour un test asynchrone."""
    database = await Database.connect(get_settings().database_url)
    try:
        yield database
    finally:
        await database.close()


@pytest.fixture
def user_id(test_prefix: str) -> Iterator[uuid.UUID]:
    """Crée un utilisateur jetable ; le supprimer efface aussi ses sessions, playlists et imports."""
    # Dépend de test_prefix : l'utilisateur (et ses playlist_item) est effacé AVANT les morceaux de test.
    uid = uuid.uuid4()
    with psycopg.connect(get_settings().database_url, autocommit=True) as conn:
        conn.execute("INSERT INTO app_user (id, display_name) VALUES (%s, 'Test')", (uid,))
        yield uid
        conn.execute("DELETE FROM app_user WHERE id = %s", (uid,))


@pytest.fixture
def test_prefix() -> Iterator[str]:
    """Préfixe unique pour les ISRC, ID externes et artistes d'un test ; tout ce qui le porte est effacé."""
    prefix = f"ZZ{uuid.uuid4().hex[:8].upper()}"
    yield prefix
    with psycopg.connect(get_settings().database_url, autocommit=True) as conn:
        conn.execute(
            """DELETE FROM track WHERE isrc LIKE %(p)s OR title LIKE %(p)s
                  OR id IN (SELECT track_id FROM track_external_id WHERE external_id LIKE %(p)s)""",
            {"p": f"{prefix}%"},
        )
        conn.execute("DELETE FROM artist WHERE name LIKE %s", (f"{prefix}%",))
