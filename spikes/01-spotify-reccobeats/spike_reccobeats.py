"""Test de faisabilité n°2 : couverture et précision de ReccoBeats sur TES morceaux.

Entrée  : data/tracks.json (produit par spike_spotify.py)
Option  : --rekordbox data/rekordbox.xml  (export XML de ta collection rekordbox)
Sortie  : data/reccobeats.csv + bilan dans le terminal

Mesure :
  1. couverture : combien de tes morceaux ReccoBeats connaît
  2. précision  : si un XML rekordbox est fourni, écart BPM et tonalité vs rekordbox
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import httpx

from http_utils import request
from keys import camelot_from_pitch, camelot_from_text, compare_bpm, compare_keys

API = "https://api.reccobeats.com/v1"
BATCH = 40


def lookup_ids(client: httpx.Client, spotify_ids: list[str]) -> dict[str, str]:
    """Spotify ID -> UUID ReccoBeats."""
    mapping: dict[str, str] = {}
    for i in range(0, len(spotify_ids), BATCH):
        chunk = spotify_ids[i:i + BATCH]
        resp = request(client, "GET", f"{API}/track", params={"ids": ",".join(chunk)})
        if resp.status_code != 200:
            print(f"   lot {i // BATCH + 1} : HTTP {resp.status_code}")
            continue
        for item in resp.json().get("content", []):
            spotify_id = (item.get("href") or "").rsplit("/", 1)[-1]
            if spotify_id:
                mapping[spotify_id] = item["id"]
    return mapping


def audio_features(client: httpx.Client, uuid: str) -> dict | None:
    resp = request(client, "GET", f"{API}/track/{uuid}/audio-features")
    return resp.json() if resp.status_code == 200 else None


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"\(.*?\)|\[.*?\]|feat\..*| - .*", "", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def load_rekordbox(path: Path) -> dict[str, dict]:
    """Indexe les morceaux de l'XML rekordbox par 'titre normalisé|premier artiste normalisé'."""
    index: dict[str, dict] = {}
    root = ET.parse(path).getroot()
    for t in root.iter("TRACK"):
        name, artist = t.get("Name"), t.get("Artist")
        if not name:
            continue
        first_artist = re.split(r",|&| x |feat", artist or "", flags=re.I)[0]
        key = f"{normalize(name)}|{normalize(first_artist)}"
        bpm = t.get("AverageBpm")
        index[key] = {
            "bpm": float(bpm) if bpm else None,
            "tonality": t.get("Tonality"),
            "location": t.get("Location"),
        }
    return index


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tracks", default="data/tracks.json")
    parser.add_argument("--rekordbox", help="chemin vers l'export XML rekordbox")
    parser.add_argument("--out", default="data/reccobeats.csv")
    args = parser.parse_args()

    tracks = json.loads(Path(args.tracks).read_text())
    if not tracks:
        raise SystemExit("Aucun morceau dans data/tracks.json : lance d'abord spike_spotify.py.")
    rb_index = load_rekordbox(Path(args.rekordbox)) if args.rekordbox else {}
    if args.rekordbox:
        print(f"{len(rb_index)} morceaux lus dans l'XML rekordbox.")

    client = httpx.Client(timeout=30)
    print(f"Recherche de {len(tracks)} morceaux sur ReccoBeats...")
    mapping = lookup_ids(client, [t["spotify_id"] for t in tracks])

    rows, bpm_cmp, key_cmp = [], Counter(), Counter()
    with_features = 0
    for t in tracks:
        uuid = mapping.get(t["spotify_id"])
        feats = audio_features(client, uuid) if uuid else None
        if feats:
            with_features += 1
        rc_bpm = round(feats["tempo"], 1) if feats and feats.get("tempo") else None
        rc_key = camelot_from_pitch(feats.get("key"), feats.get("mode")) if feats else None

        rb = rb_index.get(f"{normalize(t['title'])}|{normalize(t['artists'][0] if t['artists'] else '')}") if rb_index else None
        rb_bpm = rb["bpm"] if rb else None
        rb_key = camelot_from_text(rb["tonality"]) if rb else None
        b, k = compare_bpm(rc_bpm, rb_bpm), compare_keys(rc_key, rb_key)
        if rb:
            bpm_cmp[b] += 1
            key_cmp[k] += 1

        rows.append({
            "titre": t["title"],
            "artistes": ", ".join(t["artists"]),
            "spotify_id": t["spotify_id"],
            "isrc": t.get("isrc") or "",
            "reccobeats_trouve": "oui" if uuid else "non",
            "bpm_reccobeats": rc_bpm or "",
            "camelot_reccobeats": rc_key or "",
            "energie": round(feats["energy"], 2) if feats and feats.get("energy") is not None else "",
            "bpm_rekordbox": rb_bpm or "",
            "camelot_rekordbox": rb_key or "",
            "ecart_bpm": b if rb else "",
            "ecart_tonalite": k if rb else "",
            "location_rekordbox": rb["location"] if rb else "",
        })

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    n = len(tracks)
    print("\n=== Bilan ReccoBeats ===")
    print(f"Couverture       : {len(mapping)}/{n} morceaux connus ({len(mapping) / n:.0%})")
    print(f"Avec BPM/tonalité : {with_features}/{n} ({with_features / n:.0%})")
    if rb_index:
        matched = sum(bpm_cmp.values())
        print(f"Appariés avec rekordbox : {matched}/{n}")
        if matched:
            print("BPM       :", dict(bpm_cmp))
            print("Tonalité  :", dict(key_cmp))
            print("  (identique = parfait ; relative/voisine = mixable mais faux ; différente = erreur)")
    print(f"\nDétail morceau par morceau : {args.out}")


if __name__ == "__main__":
    main()
