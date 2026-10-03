"""Conversions de tonalité vers la notation Camelot et comparaisons."""

from __future__ import annotations

import re

# Index de classe de hauteur (0 = C ... 11 = B) -> numéro Camelot
_MAJOR = {0: 8, 1: 3, 2: 10, 3: 5, 4: 12, 5: 7, 6: 2, 7: 9, 8: 4, 9: 11, 10: 6, 11: 1}
_MINOR = {0: 5, 1: 12, 2: 7, 3: 2, 4: 9, 5: 4, 6: 11, 7: 6, 8: 1, 9: 8, 10: 3, 11: 10}

_NOTES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def camelot_from_pitch(key: int | None, mode: int | None) -> str | None:
    """Format Spotify/ReccoBeats : key 0-11 (-1 = inconnu), mode 1 = majeur, 0 = mineur."""
    if key is None or mode is None or key < 0:
        return None
    return f"{_MAJOR[key]}B" if mode == 1 else f"{_MINOR[key]}A"


def camelot_from_text(text: str | None) -> str | None:
    """Accepte '8A', '11B', 'Am', 'A#m', 'Dbm', 'F#', 'Abmin'... (formats rekordbox)."""
    if not text:
        return None
    s = text.strip()
    m = re.fullmatch(r"(\d{1,2})\s*([ABab])", s)
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{int(m.group(1))}{m.group(2).upper()}"
    m = re.fullmatch(r"([A-Ga-g])([#b♯♭]?)\s*(m|min|minor)?", s)
    if not m:
        return None
    pitch = _NOTES[m.group(1).upper()]
    if m.group(2) in ("#", "♯"):
        pitch += 1
    elif m.group(2) in ("b", "♭"):
        pitch -= 1
    return camelot_from_pitch(pitch % 12, 0 if m.group(3) else 1)


def compare_keys(a: str | None, b: str | None) -> str:
    """Classe l'écart entre deux tonalités Camelot."""
    if not a or not b:
        return "inconnu"
    na, la, nb, lb = int(a[:-1]), a[-1], int(b[:-1]), b[-1]
    if a == b:
        return "identique"
    if na == nb:
        return "relative"  # même chiffre, A <-> B
    if la == lb and (abs(na - nb) % 12 in (1, 11)):
        return "voisine"
    return "différente"


def compare_bpm(a: float | None, b: float | None, tolerance: float = 1.0) -> str:
    if not a or not b:
        return "inconnu"
    if abs(a - b) <= tolerance:
        return "identique"
    if abs(a * 2 - b) <= tolerance or abs(a - b * 2) <= tolerance:
        return "demi/double"
    return "différent"
