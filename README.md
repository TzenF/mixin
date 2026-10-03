# DJ Platform

Plateforme web d'aide à la préparation de sets DJ : suggestions de morceaux compatibles (BPM et tonalité
Camelot), playlists exportées vers Spotify (et donc rekordbox), analyse audio maison.

> Projet personnel — inspiré de [Mixgraph](https://www.mixgraph.io), en gratuit et avec ses propres choix.

## Démarrer

Prérequis : Docker et Docker Compose. Sur Chromebook, `DOCKER_BUILDKIT=0` est nécessaire (le Makefile le fait).

```bash
cp .env.example .env      # puis renseigner SPOTIFY_CLIENT_ID
make up                   # premier lancement : quelques minutes (Essentia + dépendances npm)
```

| Service | Adresse |
|---|---|
| Front (Angular) | http://localhost:4200 |
| API (documentation interactive) | http://localhost:8000/docs |
| PostgreSQL | `localhost:5432` (dj / dj) — ou `make psql` |

La page d'accueil affiche l'état de la base et de la file de tâches : si tout est vert, la chaîne
navigateur → Angular → API → PostgreSQL / Redis fonctionne.

Autres commandes : `make test`, `make lint`, `make logs`, `make down`, `make reset-db`.

## Architecture

```
web/        Angular 22        -> appelle /api/* (proxy de dev vers l'API)
backend/    FastAPI + worker  -> une base de code, deux images (api / worker)
db/         migrations SQL    -> chargées au premier démarrage de PostgreSQL
spikes/     tests de faisabilité (historique des décisions)
```

Le backend est découpé en couches ; **une couche ne dépend que de celles en dessous** :

| Couche | Rôle | Exemple |
|---|---|---|
| `app/api` | Routes HTTP, validation des entrées/sorties | `tracks.py` |
| `app/services` | Cas d'usage (importer, suggérer, exporter) | *à venir* |
| `app/domain` | Logique métier pure, testable sans base ni réseau | `camelot.py`, `music_provider.py` |
| `app/adapters` | Monde extérieur : PostgreSQL, Redis, Spotify, Deezer | `db.py`, `queue.py` |
| `app/worker` | Tâches longues (analyse audio) exécutées hors requête HTTP | `main.py` |

### Données

Schéma complet : [`db/migrations/001_init.sql`](db/migrations/001_init.sql). Points clés :

- **Nos propres identifiants** ; Spotify/Deezer dans `track_external_id`, l'ISRC sert de clé commune.
- **Les playlists vivent ici** ; Spotify n'est qu'une destination d'export.
- **BPM et tonalité : une ligne par source** (`track_analysis`), jamais écrasée. La valeur affichée est
  choisie à la lecture par `effective_features(user)` : correction perso > rekordbox perso > correction admin > Essentia.
- **Suggestions** : `suggest_tracks(user, morceau)` — roue Camelot, ±6 % de BPM, demi/double tempo,
  score pondéré par la confiance de la tonalité.

`db/test_fixtures.sql` insère 11 morceaux réels avec leurs valeurs Essentia et affiche des suggestions,
les priorités entre sources et les contraintes. Pour le lancer (il **ajoute des données** à la base) :

```bash
docker compose exec -T db psql -U dj -d dj < db/test_fixtures.sql
```

## État

- [x] Tests de faisabilité ([`spikes/`](spikes/README.md))
- [x] Modèle de données V1
- [x] Squelette : Compose, API, worker, front, CI
- [ ] Connexion Spotify (OAuth) et import des playlists
- [ ] Worker : Deezer par ISRC + Essentia
- [ ] Catalogue filtrable, suggestions, playlists, favoris
- [ ] Export Spotify / TXT / M3U, import rekordbox, corrections manuelles
