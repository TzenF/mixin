"""Test de faisabilité n°1 : que permet encore l'API Spotify en mode développement ?

Vérifie, sur TON compte :
  A. lecture du profil
  B. liste de tes playlists
  C. lecture des morceaux d'une de tes playlists (+ présence de l'ISRC)
  D. lecture de tes titres likés
  E. création d'une playlist privée + ajout de morceaux  <- le point critique

Écrit les morceaux lus dans data/tracks.json pour le test ReccoBeats.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import httpx

from http_utils import request
from spotify_auth import get_access_token

API = "https://api.spotify.com/v1"
OUT = Path("data/tracks.json")

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
    print(f"[{'OK ' if ok else 'KO '}] {name}{' — ' + detail if detail else ''}")
    return ok


def paginate(client: httpx.Client, url: str, max_items: int = 500) -> list[dict]:
    items: list[dict] = []
    while url and len(items) < max_items:
        resp = request(client, "GET", url)
        if resp.status_code != 200:
            raise httpx.HTTPStatusError(f"{resp.status_code} {resp.text[:200]}", request=resp.request, response=resp)
        page = resp.json()
        items.extend(page.get("items", []))
        url = page.get("next")
    return items


def track_of(entry: dict) -> dict | None:
    # Février 2026 : 'track' renommé en 'item' dans les réponses de playlist.
    track = entry.get("item") or entry.get("track")
    if not track or track.get("type", "track") != "track" or not track.get("id"):
        return None
    return track


def simplify(track: dict) -> dict:
    return {
        "spotify_id": track["id"],
        "uri": track.get("uri", f"spotify:track:{track['id']}"),
        "title": track.get("name"),
        "artists": [a.get("name") for a in track.get("artists", [])],
        "duration_ms": track.get("duration_ms"),
        "isrc": (track.get("external_ids") or {}).get("isrc"),
    }


def main() -> None:
    client = httpx.Client(headers={"Authorization": f"Bearer {get_access_token()}"}, timeout=30)

    # A. Profil
    resp = request(client, "GET", f"{API}/me")
    if not check("A. Profil (/me)", resp.status_code == 200, f"HTTP {resp.status_code}"):
        print(resp.text[:500])
        return
    me = resp.json()
    print(f"   Connectée en tant que : {me.get('display_name')} ({me.get('id')})")

    # B. Playlists
    try:
        playlists = paginate(client, f"{API}/me/playlists?limit=50")
        owned = [p for p in playlists if p and (p.get("owner") or {}).get("id") == me["id"]]
        check("B. Liste des playlists", True, f"{len(playlists)} au total, dont {len(owned)} à toi")
    except httpx.HTTPStatusError as e:
        check("B. Liste des playlists", False, str(e))
        return

    # C. Morceaux d'une playlist
    tracks: list[dict] = []
    if owned:
        print("\nTes playlists :")
        for i, p in enumerate(owned):
            total = (p.get("items") or p.get("tracks") or {}).get("total", "?")
            print(f"  {i:>2}. {p['name']} ({total} titres)")
        choice = input("\nNuméro de la playlist à tester (une playlist DJ de préférence) : ").strip()
        playlist = owned[int(choice)] if choice.isdigit() and int(choice) < len(owned) else owned[0]
        try:
            entries = paginate(client, f"{API}/playlists/{playlist['id']}/items?limit=50")
            tracks = [simplify(t) for t in map(track_of, entries) if t]
            with_isrc = sum(1 for t in tracks if t["isrc"])
            check("C. Morceaux d'une playlist", len(tracks) > 0, f"{len(tracks)} morceaux dans « {playlist['name']} »")
            check("C'. ISRC présent", with_isrc > 0, f"{with_isrc}/{len(tracks)} morceaux avec ISRC")
        except httpx.HTTPStatusError as e:
            check("C. Morceaux d'une playlist", False, str(e))
    else:
        check("C. Morceaux d'une playlist", False, "aucune playlist dont tu es propriétaire")

    # D. Titres likés
    try:
        liked = paginate(client, f"{API}/me/tracks?limit=50", max_items=50)
        check("D. Titres likés (/me/tracks)", True, f"{len(liked)} lus (échantillon)")
    except httpx.HTTPStatusError as e:
        check("D. Titres likés (/me/tracks)", False, str(e))

    # E. Création de playlist + ajout de morceaux
    sample = tracks[:3]
    name = f"[TEST plateforme DJ] {datetime.now():%Y-%m-%d %H:%M}"
    resp = request(
        client, "POST", f"{API}/me/playlists",
        json={"name": name, "public": False, "description": "Playlist de test, à supprimer."},
    )
    if check("E. Création de playlist (POST /me/playlists)", resp.status_code in (200, 201), f"HTTP {resp.status_code}"):
        new_id = resp.json()["id"]
        if sample:
            resp = request(client, "POST", f"{API}/playlists/{new_id}/items", json={"uris": [t["uri"] for t in sample]})
            check("E'. Ajout de morceaux (POST /playlists/{id}/items)", resp.status_code in (200, 201), f"HTTP {resp.status_code}")
        print(f"   -> Vérifie qu'elle apparaît dans rekordbox : « {name} »")
    else:
        print(resp.text[:500])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(tracks, indent=2, ensure_ascii=False))
    print(f"\n{len(tracks)} morceaux enregistrés dans {OUT} pour le test ReccoBeats.")

    failed = [r for r in results if not r[1]]
    print("\n=== Bilan :", "tout est OK" if not failed else f"{len(failed)} point(s) KO", "===")


if __name__ == "__main__":
    main()
