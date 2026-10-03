# Tests de faisabilité

Scripts jetables écrits **avant** le code de l'application pour valider les hypothèses du plan.
Ils ne sont pas maintenus ; ils documentent pourquoi l'architecture est ce qu'elle est.

## 01 — Spotify + ReccoBeats (2 octobre 2026)

**Spotify, mode développement** — tout fonctionne :
lecture des playlists, des morceaux et des titres likés ; **création de playlist et ajout de morceaux** (HTTP 201) ;
**ISRC présent sur 32/32 morceaux** (retiré par Spotify en février 2026, rétabli en mars).

**ReccoBeats** — insuffisant :
couverture **19/32 (59 %)** sur une playlist DJ récente ; tonalité juste sur **3/9** morceaux vérifiés.

## 02 — Deezer (ISRC) + Essentia (2 octobre 2026)

**Deezer** : **32/32** morceaux retrouvés par ISRC, extrait de 30 s disponible pour tous.

**Essentia** (profil `edma`, sur l'extrait de 30 s) :
- BPM : concorde avec les références (écart max 1,9 BPM avec ReccoBeats)
- tonalité : **6/9 confirmées** par des transcriptions humaines (Hooktheory), 2 contestées, 1 erreur ;
  **tonique juste 9/9** — les erreurs sont des inversions majeur/mineur
- profils `bgate` et `temperley` moins bons → abandonnés

Point d'attention : Beatport (et donc Mixgraph) n'est **pas** une vérité terrain — il s'est trompé de mode
sur « Von dutch » face à la transcription humaine.

## Décisions qui en découlent

- Source principale : **Essentia sur l'extrait Deezer**, retrouvé par ISRC. ReccoBeats abandonné.
- Tonalité stockée avec **source et confiance** ; corrections manuelles et import rekordbox prioritaires.
- Bouton « inverser majeur/mineur » : corrige l'erreur la plus fréquente en un clic.
- Essentia n'a **pas de version Linux ARM** : le worker doit tourner sur x86_64.
