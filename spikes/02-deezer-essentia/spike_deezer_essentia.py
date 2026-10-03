"""Test de faisabilité n°3 : Deezer (par ISRC) + analyse maison Essentia.

Pour chaque morceau de data/tracks.json :
  1. retrouve le morceau sur Deezer par son ISRC (correspondance exacte)
  2. télécharge l'extrait de 30 s, l'analyse avec Essentia, puis le supprime
  3. compare avec ReccoBeats (data/reccobeats.csv) et avec les références connues

Sortie : data/essentia.csv + bilan dans le terminal.
"""

from __future__ import annotations

import csv
import json
import tempfile
from collections import Counter
from pathlib import Path

import httpx

from analysis import KEY_PROFILES, analyze
from http_utils import request
from keys import compare_bpm, compare_keys

DEEZER = "https://api.deezer.com"
TRACKS = Path("data/tracks.json")
RECCOBEATS = Path("data/reccobeats.csv")
OUT = Path("data/essentia.csv")

# Valeurs de référence vérifiées à la main (spotify_id -> (bpm, camelot)).
# bpm à None quand la référence porte sur une autre version du morceau.
REFERENCES = {
    "3tyPOhuVnt5zd5kGfxbCyL": (128, "5A"),   # Where Have You Been
    "0ByMNEPAPpOR5H69DVrTNy": (None, "11A"), # Don't Stop The Music
    "3Qt9dFYxJLA4u2rlXafqrf": (None, "7A"),  # Rock That Body
    "6ho0GyrWZN3mhi9zVRW7xi": (125, "9B"),   # Losing It
    "6qJhrI2BMuA8qHcmycD3fL": (132, "7B"),   # TESLA
    "3Y1EvIgEVw51XtgNEgpz5c": (130, "7B"),   # Von dutch
}


def deezer_by_isrc(client: httpx.Client, isrc: str) -> dict | None:
    resp = request(client, "GET", f"{DEEZER}/track/isrc:{isrc}")
    data = resp.json() if resp.status_code == 200 else {}
    return None if "error" in data or not data.get("id") else data


def load_reccobeats() -> dict[str, dict]:
    if not RECCOBEATS.exists():
        return {}
    with open(RECCOBEATS, encoding="utf-8") as f:
        return {row["spotify_id"]: row for row in csv.DictReader(f)}


def main() -> None:
    tracks = json.loads(TRACKS.read_text())
    reccobeats = load_reccobeats()
    client = httpx.Client(timeout=30, follow_redirects=True)

    rows = []
    found = with_preview = 0
    key_scores = {name: Counter() for name in (*KEY_PROFILES, "reccobeats")}
    bpm_scores = {name: Counter() for name in ("essentia", "reccobeats")}

    for i, t in enumerate(tracks, 1):
        print(f"[{i:>2}/{len(tracks)}] {t['title']} — {', '.join(t['artists'])}")
        row = {"titre": t["title"], "artistes": ", ".join(t["artists"]), "isrc": t.get("isrc") or ""}

        dz = deezer_by_isrc(client, t["isrc"]) if t.get("isrc") else None
        row["deezer_trouve"] = "oui" if dz else "non"
        row["deezer_titre"] = dz.get("title", "") if dz else ""
        row["deezer_bpm"] = dz.get("bpm") or "" if dz else ""
        found += bool(dz)

        if dz and dz.get("preview"):
            with_preview += 1
            with tempfile.NamedTemporaryFile(suffix=".mp3") as tmp:
                audio = request(client, "GET", dz["preview"])
                tmp.write(audio.content)
                tmp.flush()
                try:
                    row.update(analyze(tmp.name))
                except Exception as e:  # extrait corrompu, format inattendu...
                    print(f"     analyse impossible : {e}")
            # le fichier temporaire est supprimé ici : on ne garde que les chiffres

        rc = reccobeats.get(t["spotify_id"], {})
        row["bpm_reccobeats"] = rc.get("bpm_reccobeats", "")
        row["key_reccobeats"] = rc.get("camelot_reccobeats", "")

        ref = REFERENCES.get(t["spotify_id"])
        row["bpm_reference"], row["key_reference"] = (ref if ref else ("", ""))
        if ref:
            ref_bpm, ref_key = ref
            for name in KEY_PROFILES:
                key_scores[name][compare_keys(row.get(f"key_{name}"), ref_key)] += 1
            key_scores["reccobeats"][compare_keys(row["key_reccobeats"] or None, ref_key)] += 1
            if ref_bpm:
                bpm_scores["essentia"][compare_bpm(row.get("bpm"), ref_bpm)] += 1
                rc_bpm = float(row["bpm_reccobeats"]) if row["bpm_reccobeats"] else None
                bpm_scores["reccobeats"][compare_bpm(rc_bpm, ref_bpm)] += 1

        print(f"     Deezer : {row['deezer_trouve']}  |  Essentia : {row.get('bpm', '-')} BPM, "
              f"{row.get('key_edma', '-')} (edma)  |  ReccoBeats : {row['bpm_reccobeats'] or '-'}, {row['key_reccobeats'] or '-'}")
        rows.append(row)

    columns = ["titre", "artistes", "isrc", "deezer_trouve", "deezer_titre", "deezer_bpm", "bpm", "bpm_confidence",
               *(c for p in KEY_PROFILES for c in (f"key_{p}", f"strength_{p}")),
               "bpm_reccobeats", "key_reccobeats", "bpm_reference", "key_reference"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    n = len(tracks)
    missing_rc = [r for r in rows if not r["key_reccobeats"]]
    rescued = sum(1 for r in missing_rc if r.get("key_edma"))
    print("\n=== Bilan Deezer + Essentia ===")
    print(f"Trouvés sur Deezer par ISRC : {found}/{n}")
    print(f"Avec extrait analysé        : {sum(1 for r in rows if r.get('bpm'))}/{n}")
    print(f"Morceaux inconnus de ReccoBeats récupérés par Essentia : {rescued}/{len(missing_rc)}")
    print("\nTonalité vs références (identique = juste) :")
    for name, scores in key_scores.items():
        print(f"  {name:<11}: {dict(scores)}")
    print("BPM vs références :")
    for name, scores in bpm_scores.items():
        print(f"  {name:<11}: {dict(scores)}")
    print(f"\nDétail : {OUT}")


if __name__ == "__main__":
    main()
