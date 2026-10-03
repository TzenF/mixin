"""Tonalités en notation Camelot (roue harmonique des DJs)."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Classe de hauteur (0 = Do ... 11 = Si) -> numéro Camelot
_MAJOR = {0: 8, 1: 3, 2: 10, 3: 5, 4: 12, 5: 7, 6: 2, 7: 9, 8: 4, 9: 11, 10: 6, 11: 1}
_MINOR = {0: 5, 1: 12, 2: 7, 3: 2, 4: 9, 5: 4, 6: 11, 7: 6, 8: 1, 9: 8, 10: 3, 11: 10}
_NOTES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


@dataclass(frozen=True, slots=True)
class CamelotKey:
    """Une position sur la roue Camelot, par exemple 8A (La mineur)."""

    number: int  # 1..12
    letter: str  # 'A' = mineur, 'B' = majeur

    def __post_init__(self) -> None:
        """Refuse les clés qui n'existent pas sur la roue (13A, 8C...)."""
        if not 1 <= self.number <= 12 or self.letter not in ("A", "B"):
            raise ValueError(f"Clé Camelot invalide : {self.number}{self.letter}")

    def __str__(self) -> str:
        """Notation courte : '8A'."""
        return f"{self.number}{self.letter}"

    @property
    def is_minor(self) -> bool:
        """Vrai pour une tonalité mineure (lettre A)."""
        return self.letter == "A"

    @classmethod
    def from_pitch(cls, pitch_class: int, minor: bool) -> CamelotKey:
        """Convertit une note (0 = Do ... 11 = Si) et un mode en clé Camelot."""
        table = _MINOR if minor else _MAJOR
        return cls(table[pitch_class % 12], "A" if minor else "B")

    @classmethod
    def parse(cls, text: str) -> CamelotKey:
        """Accepte '8A', '11b', 'Am', 'F#m', 'Dbmin', 'Gb'... (formats rekordbox / Essentia)."""
        s = text.strip()
        if m := re.fullmatch(r"(\d{1,2})\s*([ABab])", s):
            return cls(int(m.group(1)), m.group(2).upper())
        if m := re.fullmatch(r"([A-Ga-g])([#b♯♭]?)\s*(m|min|minor)?", s):
            pitch = _NOTES[m.group(1).upper()]
            pitch += {"#": 1, "♯": 1, "b": -1, "♭": -1}.get(m.group(2), 0)
            return cls.from_pitch(pitch, minor=bool(m.group(3)))
        raise ValueError(f"Tonalité non reconnue : {text!r}")

    def parallel(self) -> CamelotKey:
        """Même tonique, mode inversé (Fa mineur <-> Fa majeur).

        C'est l'erreur la plus fréquente d'Essentia : sert au bouton « inverser majeur/mineur ».
        """
        return (
            CamelotKey((self.number + 3 - 1) % 12 + 1, "B")
            if self.is_minor
            else CamelotKey((self.number - 3 - 1) % 12 + 1, "A")
        )
