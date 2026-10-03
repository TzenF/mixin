"""Analyse audio avec Essentia : BPM + tonalité (plusieurs profils comparés)."""

from __future__ import annotations

import essentia
import essentia.standard as es

from keys import camelot_from_text

essentia.log.infoActive = False
essentia.log.warningActive = False

SAMPLE_RATE = 44100
# Profils de détection de tonalité : 'edma' est conçu pour la musique électronique,
# 'bgate' et 'temperley' sont des profils généralistes. On les compare.
KEY_PROFILES = ("edma", "bgate", "temperley")


def analyze(path: str) -> dict:
    audio = es.MonoLoader(filename=path, sampleRate=SAMPLE_RATE)()
    bpm, _, beats_confidence, _, _ = es.RhythmExtractor2013(method="multifeature")(audio)

    result = {"bpm": round(float(bpm), 1), "bpm_confidence": round(float(beats_confidence), 2)}
    for profile in KEY_PROFILES:
        key, scale, strength = es.KeyExtractor(profileType=profile, sampleRate=SAMPLE_RATE)(audio)
        result[f"key_{profile}"] = camelot_from_text(f"{key}{'m' if scale == 'minor' else ''}")
        result[f"strength_{profile}"] = round(float(strength), 2)
    return result
