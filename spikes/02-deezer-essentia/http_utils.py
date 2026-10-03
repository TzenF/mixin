"""Client HTTP minimal avec gestion du rate limiting (HTTP 429 + Retry-After)."""

from __future__ import annotations

import time

import httpx


def request(client: httpx.Client, method: str, url: str, retries: int = 5, **kwargs) -> httpx.Response:
    for _ in range(retries):
        resp = client.request(method, url, **kwargs)
        if resp.status_code != 429:
            return resp
        wait = int(resp.headers.get("Retry-After", "2"))
        print(f"   ... rate limit atteint, pause de {wait}s")
        time.sleep(wait + 1)
    return resp
