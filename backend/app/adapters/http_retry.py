"""Requêtes HTTP vers les API externes, avec gestion du rate limiting (HTTP 429 + Retry-After)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

MAX_RETRIES = 5
# Au-delà, on abandonne plutôt que de bloquer la requête HTTP de l'utilisateur pendant des minutes.
MAX_WAIT_SECONDS = 30


async def request_with_retry(
    client: httpx.AsyncClient, method: str, url: str, **kwargs: Any
) -> httpx.Response:
    """Envoie la requête ; en cas de 429, attend le délai demandé puis réessaie (5 fois au plus)."""
    resp = await client.request(method, url, **kwargs)
    for _ in range(MAX_RETRIES):
        if resp.status_code != 429:
            return resp
        wait = _retry_after(resp)
        if wait > MAX_WAIT_SECONDS:
            log.warning("Rate limit : %s demande %s s d'attente, abandon", url, wait)
            return resp
        log.info("Rate limit : pause de %s s avant de réessayer %s", wait, url)
        await asyncio.sleep(wait)
        resp = await client.request(method, url, **kwargs)
    return resp


def _retry_after(resp: httpx.Response) -> int:
    """Lit l'en-tête Retry-After (en secondes) ; 1 s s'il est absent ou illisible."""
    try:
        return max(int(resp.headers.get("Retry-After", "1")), 0)
    except ValueError:
        return 1
