"""Lire l'identifiant d'une playlist Deezer dans ce que colle l'utilisateur : lien du site ou de l'app, ID.

Vérifié le 18/10/2026 : le site donne `https://www.deezer.com/fr/playlist/<id>?…` ; l'app mobile partage un
lien court `https://link.deezer.com/s/<code>`, à résoudre d'abord (voir `DeezerClient.resolve_short_link`).
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

SHORT_LINK_HOST = "link.deezer.com"
_ID = re.compile(r"\d{1,20}")
# /playlist/<id>, avec ou sans langue devant (/fr/, /en/, /pt-br/…)
_PLAYLIST_PATH = re.compile(r"/(?:[a-z]{2}(?:-[a-z]{2})?/)?playlist/(\d{1,20})/?")


def playlist_id_from_link(text: str) -> str | None:
    """Identifiant de la playlist (ID seul ou lien deezer.com/…/playlist/<id>) ; None sinon."""
    text = text.strip()
    if _ID.fullmatch(text):
        return text
    parts = urlsplit(text if "://" in text else f"https://{text}")
    if parts.scheme not in ("http", "https") or parts.hostname not in ("deezer.com", "www.deezer.com"):
        return None
    match = _PLAYLIST_PATH.fullmatch(parts.path.lower())
    return match.group(1) if match else None


def is_short_link(text: str) -> bool:
    """Vrai pour un lien court partagé par l'app (`https://link.deezer.com/s/…`)."""
    parts = urlsplit(text.strip())
    return parts.scheme == "https" and parts.hostname == SHORT_LINK_HOST and parts.path.startswith("/s/")
