# CLAUDE.md

Plateforme web d'aide à la préparation de sets DJ : suggestions de morceaux compatibles (BPM + tonalité Camelot),
playlists exportées vers Spotify (visibles ensuite dans rekordbox), analyse audio maison.
Projet personnel et de portfolio, développé seule, 15–20 h/semaine. L'autrice est aussi la première utilisatrice.

## Règles absolues

1. **Ne jamais faire `git commit` ni `git push` sans autorisation explicite pour ce commit précis.**
   Même chose pour tout ce qui réécrit ou détruit l'historique ou des fichiers (`reset --hard`, `rebase`,
   `push --force`, suppression de branche, `checkout -- .`). À la fin d'une tâche : résumer les changements et
   **proposer** un message de commit, puis attendre.
2. **Demander avant d'ajouter une dépendance** (pip, npm, image Docker) : dire pourquoi, et ce qu'on ferait sans.
3. **Ne jamais modifier une migration existante** dans `db/migrations/` : ajouter un fichier numéroté.
4. **Aucun secret** dans le code, les logs ou les commits (jetons, Client ID, mots de passe) : `.env` uniquement.
5. **Ne jamais stocker d'audio** : les extraits sont analysés puis supprimés ; on garde seulement les chiffres.

## Façon de travailler

- Répondre en **français**. Code, commentaires, docstrings, messages d'erreur visibles et commits en français ;
  identifiants (variables, fonctions, tables) en anglais.
- Donner un avis **critique et direct** : signaler les mauvaises idées, les hypothèses non vérifiées, les limites.
  Ne pas valider une proposition juste pour aller dans le sens de la demande.
- **Vérifier avant d'affirmer** dès que ça touche une API externe (Spotify, Deezer…) : elles changent souvent.
- Petits pas : une fonctionnalité à la fois, testée, avant la suivante. Pas d'abstraction « pour plus tard ».
- Avant de dire « c'est fini » : `make lint` et `make test` passent. Dire clairement ce qui **n'a pas** été vérifié.
- Si une décision de ce fichier change, ou si on découvre un nouveau piège : **proposer** la mise à jour du
  CLAUDE.md dans la même tâche.

## Conventions de code

### Docstrings — sur chaque fonction
- **Chaque fonction, méthode et classe a une docstring d'une phrase simple** qui dit *ce qu'elle fait*
  (pas comment). Pas besoin de détailler chaque paramètre.
- Python : `"""…"""`. Vérifié automatiquement par ruff (règles D101–D103) en CI pour tout ce qui est public ;
  les fonctions privées (`_nom`) en ont une aussi, par convention. Exception : les `test_*`, dont le nom suffit.
- TypeScript : `/** … */` au-dessus de chaque classe, méthode, `computed` et fonction exportée.

### Réutiliser l'existant
- **Avant de créer** une fonction, un service, un composant, un style ou une requête : chercher s'il existe déjà
  (voir l'inventaire ci-dessous, puis `grep`). Étendre l'existant plutôt que dupliquer.
- Un même motif écrit deux fois → on le factorise (fonction, mixin, composant partagé).
- Ne pas recoder en Python ce que fait déjà une fonction SQL (`effective_features`, `suggest_tracks`), et
  inversement.

### Styles — tokens et mixins
- Toutes les valeurs (couleurs, espacements, rayons, polices, largeurs) viennent de `web/src/styles/_tokens.scss`.
  **Aucune valeur en dur** dans un composant (`#fff`, `12px`…).
- Les motifs de style viennent de `web/src/styles/_mixins.scss` : `@use 'mixins' as m;` puis `@include m.panel;`.
  Un motif utilisé par deux composants **devient un mixin** dans ce fichier, avec un commentaire `///`.
- Couleurs = variables CSS (`var(--color-…)`), pour permettre un thème sombre plus tard.
- **Boutons de base définis une seule fois** dans `web/src/styles.scss` : `button` / `.button` (bleu), `.secondary`
  (encadré), `.accent` (jaune, **une** action phare par page). Les pages ne les redéfinissent pas (sinon le même CSS
  est recopié dans chaque page et dépasse le budget de 4 ko). Un composant qui veut autre chose (carte cliquable,
  petit bouton ▶ ★…) le redéfinit dans son style, en fixant aussi son fond au survol.
- Boutons et champs ont la même hauteur (`$control-height`, `$control-height-sm`, mixin `control`) ; les groupes
  d'actions utilisent le mixin `toolbar` (espacement par `gap`, pas de `margin-left` dans les boutons).
- Thème **temporaire** bleu et jaune (17/10/2026), en attendant la maquette Figma : on le remplace dans les tokens
  et les mixins, pas dans les pages. Jamais de texte jaune sur fond clair (≈ 1,6:1).

### Python (backend)
- Annotations de type partout. Modèles Pydantic pour les entrées/sorties de l'API.
- **Le SQL vit uniquement dans `app/adapters/`** (dépôts comme `TrackRepository`). Routes, services et worker
  appellent un dépôt, jamais `db.fetch_*` directement.
- Paramètres SQL nommés (`%(x)s`) et castés quand ils vont vers une fonction SQL (`%(x)s::uuid`).

### Angular (frontend)
- Composants standalone, `signal` / `computed`, `inject()`, syntaxe `@if` / `@for`.
- **Pas de `any` ni de `$any`** : typer, ou dériver un `computed` qui renvoie le bon type.
- Une page = un dossier dans `features/`, chargé à la demande dans `app.routes.ts`.
- Appels HTTP uniquement via des services de `core/api/` ; toujours vers `/api/…` (proxy de dev).
- Les éléments testés portent un `data-testid`. Chaque composant a son `.spec.ts`.

## Inventaire de ce qui existe déjà (à réutiliser)

| Besoin | Utiliser |
|---|---|
| Convertir / parser une tonalité (`Fm`, `8A`, note + mode) | `app/domain/camelot.py` → `CamelotKey.parse`, `.from_pitch`, `.parallel()` |
| Contrat d'un service musical | `app/domain/music_provider.py` → `MusicProvider`, `ProviderTrack`, `ProviderPlaylist` |
| Requêtes SQL | `app/adapters/db.py` → `Database.fetch_all` / `fetch_one` (depuis un dépôt uniquement) |
| Plusieurs écritures atomiques | `Database.transaction()` → objet `Transaction` ; les dépôts acceptent un `Queryable` (base ou transaction) |
| Morceaux en base | `app/adapters/track_repository.py` → `TrackRepository` (dont `find_by_isrc`, `find_by_external_id`, `set_artists`) |
| Catalogue filtré (mes morceaux ou tous) | `TrackRepository.catalog(user, CatalogFilters)` ; routes `GET /tracks`, `GET /tracks/{id}` (`CatalogFilters.track_id`) |
| Utilisateurs, comptes musicaux | `app/adapters/user_repository.py` → `UserRepository` |
| Sessions de connexion | `app/services/sessions.py` → `SessionService` (dépôt : `SessionRepository`) |
| Playlists en base | `app/adapters/playlist_repository.py` → `PlaylistRepository` (dont `list_for_owner`, `get_for_owner`, `items_with_transitions`) ; routes `GET /playlists`, `GET /playlists/{id}` |
| Modifier mes playlists (créer, renommer, ajouter, réordonner, retirer, dupliquer, supprimer) | `app/services/playlist_editor.py` → `PlaylistEditor` (importée = lecture seule → 409 ; pas à moi → 404 ; ordre périmé → 422, via `api/errors.py`). Écritures : verrou `PlaylistRepository.lock` dans une transaction ; réglages (nom, créneau, part jouée) : `update(changes)` → `PlaylistRepository.update` (colonnes d'une liste fermée), `PATCH /playlists/{id}` (champ absent = inchangé) ; `remove_items` (tout ou rien, `POST /playlists/{id}/items/remove`) ; `add_track(…, position)` insère à une place (`POST /playlists/{id}/items` avec `position`), `insert_tracks` plusieurs d'un coup, tout ou rien (`POST /playlists/{id}/items/batch`) ; tout passe par `PlaylistRepository.insert_items` |
| Journal des imports | `app/adapters/import_job_repository.py` → `ImportJobRepository` |
| Appel HTTP vers une API externe | `app/adapters/http_retry.py` → `request_with_retry` (gère les 429 / `Retry-After`) |
| Chiffrer un jeton avant stockage | `app/adapters/token_cipher.py` → `TokenCipher` (clé `TOKEN_ENCRYPTION_KEY`) |
| Jeton Spotify valide pour un utilisateur | `app/services/spotify_connection.py` → `SpotifyConnection.access_token(user_id)` |
| Lire Spotify, y créer / remplacer une playlist | `app/adapters/spotify_provider.py` → `SpotifyProvider` (`create_playlist`, `replace_playlist_items`, `playlist_url`, `find_track_by_isrc`) |
| Exporter une playlist vers Spotify | `app/services/playlist_export.py` → `PlaylistExporter` (lien gardé dans `playlist_export` ; morceau sans identifiant Spotify cherché par ISRC, identifiant gardé dans `track_external_id`) ; route `POST /playlists/{id}/export/spotify` |
| Importer une playlist | `app/services/playlist_import.py` → `PlaylistImporter` |
| Lancer une analyse | `app/adapters/queue.py` → `TaskQueue.enqueue_analysis` (déjà dédoublonné) |
| Analyser un morceau (exécuté par le worker) | `app/services/track_analysis.py` → `TrackAnalyzer` |
| Relancer les morceaux en attente | `make analyze-pending` → `track_analysis.enqueue_pending` |
| Savoir si on est en production | `Settings.is_production` (`ENVIRONMENT`) |
| Extrait Deezer par ISRC | `app/adapters/deezer_client.py` → `DeezerClient` (`DeezerUnavailableError` = réessayer plus tard) |
| Valeurs Essentia en base | `app/adapters/analysis_repository.py` → `AnalysisRepository` |
| Corriger un morceau pour moi (BPM, tonalité, annuler) | `services/track_correction.py` → `correct` (`CorrectionChanges`), `flip_mode` ; `AnalysisRepository.personal_correction`, `.save_personal_correction`, `.effective_key` ; route `PATCH /tracks/{id}/correction` (champ absent = inchangé, `null` = annuler) |
| Test d'une route qui exige une session | fixture `logged_in_client` (`tests/conftest.py`) |
| Dépendances de route | `app/api/deps.py` → `get_db`, `get_queue`, `get_track_repository`, `get_current_user_id` (exige une session) |
| Erreur de service musical → HTTP | `app/api/errors.py` (404 / 401 / 502, déjà branché) |
| Valeur BPM/tonalité à afficher | SQL `effective_features(user)` |
| Règle d'enchaînement entre deux morceaux | SQL `transition(a_bpm, a_num, a_letter, b_bpm, b_num, b_letter, tolerance)` (migrations 003–004) : utilisée par `suggest_tracks`, `bridge_tracks` et les playlists ; score d'un enchaînement : SQL `transition_score` (006) ; ligne Python `TransitionRow` (`track_repository.py`), modèle d'API `Transition` (`api/transitions.py`) |
| Morceaux compatibles | SQL `suggest_tracks(user, seed, tolerance, limit)`, via `TrackRepository.suggestions` (filtre « mes morceaux » appliqué avant la limite) |
| Chemin de A à B (1 à 4 morceaux) | SQL `transition_edges(user, ids, tolerance)` (graphe des enchaînements compatibles) via `TrackRepository.transition_graph` / `.transitions_between` ; recherche `app/domain/set_path.py` → `find_paths` ; `services/set_path.py` → `PathFinder` ; route `GET /tracks/{a}/paths/{b}` ; front `CatalogService.paths`, `PlaylistService.insertTracks`, dans `bridge-finder` |
| Courbe du BPM d'une playlist (SVG, sans dépendance) | `web/src/app/features/playlists/playlist-curve/` (segments colorés par `describeTransition`, ⚠ sur les refusés, survol et clavier, largeur mesurée par `ResizeObserver`) ; jetons `$chart-stroke-width`, `$chart-hairline`, `$chart-ring-width`, `$width-tooltip` |
| Roue de Camelot d'une playlist (SVG, sans dépendance) | `web/src/app/features/playlists/camelot-wheel/` (tonalités jouées, un trait par paire, épaisseur = passages répétés, rouge + ⚠ si tonalité incompatible, début / fin) ; à côté de la courbe (`.charts` dans la page de détail) |
| Durée du set, tenir le créneau | `playlist.slot_minutes`, `.played_percent` (migration 009) ; `app/domain/set_cut.py` → `suggest_cuts`, `set_quality` ; `services/set_duration.py` → `SetCutter` ; route `GET /playlists/{id}/cut-proposal` ; front `web/src/app/shared/duration.ts` (`formatDuration`, `formatClock`, `playedDuration`), composant `features/playlists/set-duration/` |
| Proposer un ordre pour une playlist | `app/domain/reorder.py` → `best_order`, `order_quality` ; `services/playlist_reorder.py` → `PlaylistReorderer` ; route `GET /playlists/{id}/order/proposal` (appliquer = `PUT /playlists/{id}/order`) ; front `PlaylistService.proposeOrder`, composant `features/playlists/order-proposal/` |
| Plusieurs morceaux par identifiant (valeurs vues par moi) | `TrackRepository.by_ids(user, ids)` |
| Morceau pont entre A et B | SQL `bridge_tracks(user, a, b, tolerance, limit)` (score = le plus faible des deux enchaînements), via `TrackRepository.bridges` ; route `GET /tracks/{a}/bridges/{b}` ; front `CatalogService.bridges`, composant `features/playlists/bridge-finder/` |
| SQL partagé du dépôt des morceaux | `track_repository.py` → `_ARTISTS_SQL` (artistes dans l'ordre), `_MINE_SQL` (« mes morceaux » = mes playlists + mes favoris), `_FAVORITE_SQL`, `_FAVORITES_ONLY_SQL` |
| Favoris | `TrackRepository.set_favorite` ; routes `PUT` / `DELETE /tracks/{id}/favorite` ; champ `favorite` et filtre `favorites=true` (catalogue, suggestions) |
| Styles | `web/src/styles/_tokens.scss`, `_mixins.scss` (`page`, `panel`, `status`, `reset-list`, `control`, `button-primary`, `button-secondary`, `button-accent`, `icon-button`, `icon-button-on`, `toolbar`, `card-button`, `badge`, `status(success | danger | accent)`, `progress-bar`, `field`, `filter-bar`, `focus-ring`, `text-muted`, `text-danger`, `transition-kinds` (texte d'un enchaînement), `chart-transition-color(propriété)` (trait / flèche / légende d'un enchaînement dans un graphique)) ; jeton `$font-size-xs` |
| Message d'erreur d'API (front) | `web/src/app/core/api/api-error.ts` → `apiErrorMessage` |
| Session côté front | `web/src/app/core/api/auth.service.ts` → `AuthService`, `SPOTIFY_LOGIN_URL` |
| Menu principal | `web/src/app/app.ts` → `NAV_LINKS` (ajouter une page ici et dans `app.routes.ts`) |
| Sources de l'Explorer (front) | `web/src/app/core/api/explore.service.ts` → `ExploreService` |
| Playlists côté front | `web/src/app/core/api/playlist.service.ts` → `PlaylistService` |
| Playlist « en cours » (front) | `web/src/app/core/current-playlist.service.ts` → `CurrentPlaylistService` (`add(trackId, position?)`) ; pour les tests des pages : `FakeCurrentPlaylistService` (`current-playlist.service.fake.ts`) |
| Bouton ★ / ☆ (front) | `web/src/app/shared/favorite-button/` |
| URL d'un extrait Deezer (à l'écoute, jamais stockée) | `services/preview.py` → `PreviewService` ; route `GET /tracks/{id}/preview` (`no-store`, 404 avec `reason`, 503 si Deezer flanche) ; `DeezerClient.get_track`, `preview_expiry` |
| Lecture des extraits (front, un seul son à la fois) | `web/src/app/core/audio-player.service.ts` → `AudioPlayerService` (`toggle`, `toggleTransition`, `AUDIO_FACTORY`) ; pour les tests : `FakeAudioPlayerService` |
| Notes des transitions (1 à 5, commentaire) | `app/adapters/rating_repository.py` → `RatingRepository`, `RATING_JOIN_SQL` (ma note dans les playlists et les suggestions : `my_rating`) ; routes `PUT` / `DELETE /transitions/{a}/{b}/rating`, `GET /transitions/ratings/count` |
| Noter un enchaînement (front) | `web/src/app/core/api/rating.service.ts` → `RatingService` ; composant `web/src/app/shared/transition-rating/` (mis en avant après l'écoute : `AudioPlayerService.lastFinished`) |
| Boutons ▶ / ⏸ et « Écouter l'enchaînement » | `web/src/app/shared/play-button/`, `web/src/app/shared/play-transition-button/` (`TRANSITION_DISCLAIMER`) |
| Bouton « Corriger » (BPM ×2 / ÷2, tonalité, annuler) | `web/src/app/shared/track-correction/` (émet le morceau corrigé) |
| Bouton « + Ajouter », barre « Playlist en cours » | `web/src/app/shared/add-to-playlist/`, `web/src/app/shared/current-playlist-bar/` |
| Libellés et texte d'un enchaînement, écart de BPM signé (front) | `web/src/app/shared/key-moves.ts` → `KEY_MOVE_LABELS`, `formatBpmChange`, `describeTransition` |
| Playlist en texte (TXT détaillé ou tracklist) | `web/src/app/shared/playlist-text.ts` → `playlistText`, `playlistFileName` (généré côté front : pas de route API) |
| Explorer : sources (tops, éditoriales Deezer) | `app/adapters/explore_repository.py` → `ExploreRepository` ; `services/explore.py` → `ExploreSync` (tâche worker `sync_explore_source`, cron quotidien 5 h UTC) ; routes `GET /explore/sources`, `POST /explore/sources/{id}/refresh` ; ajout par lien `ExploreSync.add_source` (`POST /explore/sources`, refus 422 `InvalidSourceError`) ; retrait de mes sources `ExploreRepository.remove` (`DELETE /explore/sources/{id}`) ; morceaux d'une source = `GET /tracks?source=…&scope=all&sort=rank` |
| Enregistrer des morceaux venus d'un service (ISRC, puis identifiant) | `services/track_import.py` → `save_provider_tracks` (import Spotify et Explorer) |
| Lire une playlist publique Deezer | `DeezerClient.playlist` (dont `public`), `.playlist_tracks` (ISRC, extrait, artiste principal) |
| Lien de playlist Deezer collé (site, app, ID seul) | `app/domain/deezer_link.py` → `playlist_id_from_link`, `is_short_link` ; lien de l'app : `DeezerClient.resolve_short_link` |
| Liste de morceaux filtrable (front) | `web/src/app/shared/track-browser/` (`mode="catalog"` ou `"explore"`, `[source]`) : utilisée par le Catalogue et l'Explorer |
| Faire télécharger un fichier par le navigateur | `web/src/app/core/file-download.service.ts` → `FileDownloadService.saveText` |
| Catalogue côté front | `web/src/app/core/api/catalog.service.ts` → `CatalogService` (`tracks`, `track`, `suggestions`, `flipMode`, `bridges`, `paths`, `placements`) |
| Liens d'un morceau avec une playlist (« ce qui rentre dans mon set ») | SQL `playlist_fit(user, playlist, tolerance)` (migration 008) ; `GET /tracks?fits=<playlist>&fits_only=true` → champ `fit_count` (`CatalogFilters.fits_playlist` / `fits_only`) ; case et badge dans `track-browser` |
| Où insérer un morceau dans ma playlist | `app/domain/placement.py` → `find_placements` ; `services/placement.py` → `PlacementFinder` ; route `GET /tracks/{id}/placements?playlist=` ; composant `web/src/app/shared/placement-finder/` |

Tenir ce tableau à jour quand on ajoute un élément réutilisable.

## Commandes

Tout tourne dans Docker. Sur la machine de dev (Chromebook / Crostini), **`DOCKER_BUILDKIT=0` est obligatoire**
(le Makefile l'exporte).

```bash
make up          # construit et démarre tout — front http://127.0.0.1:4200, API :8000/docs
make test        # tests back (pytest) + front (vitest)
make lint        # ruff check + ruff format --check (dont docstrings)
make logs | make down | make psql
make reset-db    # efface la base et rejoue les migrations
make analyze-pending  # met en file d'analyse les morceaux restés « pending » (sans doublon)
```

Un test backend seul : `docker compose exec api pytest -q tests/test_api.py::test_suggestions`

## Structure

```
backend/app/
  api/        routes FastAPI : validation entrée/sortie, rien d'autre
  services/   cas d'usage (importer, suggérer, exporter) — orchestrent domaine + adaptateurs
  domain/     logique pure, sans I/O ni FastAPI
  adapters/   PostgreSQL (dépôts), Redis (arq), Spotify, Deezer
  worker/     tâches longues (analyse audio), lancées par arq
web/src/
  styles/     _tokens.scss, _mixins.scss
  app/core/   services transverses (clients API)
  app/features/ une page = un dossier
db/migrations/ SQL numéroté : 001_init.sql, 002_….sql
spikes/       tests de faisabilité — historique, pas maintenus
```

**Règle de dépendance** : `api → services → domain ← adapters`. Le domaine n'importe jamais un adaptateur.

## Choix techniques et alternatives écartées

Ne pas reproposer ces alternatives sans élément nouveau.

| Choix | Pourquoi | Écarté |
|---|---|---|
| **Python / FastAPI** pour le back | Tout l'écosystème audio est en Python (Essentia, librosa, pyrekordbox) ; un seul langage serveur | Quarkus/Java (maîtrisé, mais imposerait un 2e langage pour l'analyse) |
| **Angular** | Choix d'apprentissage de l'autrice ; structure imposée | React |
| **PostgreSQL** (+ pgvector en V3) | Relationnel + fonctions SQL + vecteurs dans une seule base | Base graphe, base vectorielle séparée |
| **Redis + arq** | Analyses longues hors requête HTTP ; simple | Celery (plus lourd) |
| **Spotify** fournisseur principal | Usage réel de l'autrice ; ses playlists apparaissent dans rekordbox | Passer à Deezer (possible plus tard grâce à `MusicProvider` + ISRC) |
| **Deezer** en coulisses | Extraits de 30 s et recherche par ISRC, sans compte utilisateur | — |
| **Essentia** (profil `edma`) | Meilleur résultat mesuré, couverture 100 % via Deezer | ReccoBeats (59 % de couverture, tonalité 3/9) |
| **LLM** (hors V2) | Uniquement pour **traduire une demande en filtres** ; le moteur choisit les morceaux | Laisser le LLM choisir les morceaux (enchaînements faux) |
| **Calcul des suggestions à la volée** en SQL | Suffisant à l'échelle actuelle | Pré-calculer toutes les paires |

## Modèle de données (décisions à respecter)

- **Nos propres UUID** partout. Les ID Spotify/Deezer vont dans `track_external_id`. L'**ISRC** est la clé
  de correspondance entre plateformes.
- **Les playlists vivent dans notre base** ; Spotify n'est qu'une destination d'export (`playlist_export`).
- **Comptes utilisateurs à nous** ; les services musicaux sont *associés* (`music_account`), jetons chiffrés.
- **BPM / tonalité : une ligne par source dans `track_analysis`, jamais écrasée.** La valeur affichée est
  calculée à la lecture par `effective_features(user)` avec la priorité :
  correction perso > rekordbox perso (inutilisé : import rekordbox retiré) > correction admin (globale) > Essentia.
- Tonalité stockée en Camelot (`camelot_num` 1–12 + `camelot_letter` A=mineur / B=majeur).
- **Règle d'enchaînement** (fonction SQL `transition`, seul endroit où elle est écrite) et score de tonalité :
  même tonalité 1.00, ±1 cran 0.90, relative (même numéro, autre lettre) 0.85, **diagonale** (±1 cran et autre
  lettre, acceptée le 16/10/2026 : une seule note change) 0.75, ±2 crans 0.50 ; tout le reste est refusé.
  Le score complet (60 % tonalité pondérée par la confiance, 40 % tempo) n'est écrit que dans `transition_score`.

Migrations : le dossier est monté dans `/docker-entrypoint-initdb.d`, donc **exécuté seulement sur un volume
vide**. Nouveau fichier numéroté. Pour ne pas effacer les données de dev (`make reset-db` efface tout) : écrire la
migration **idempotente** (`CREATE OR REPLACE`, `IF NOT EXISTS`) et l'appliquer avec
`docker compose exec -T db psql -U dj -d dj -f /docker-entrypoint-initdb.d/00X_….sql`. Une fonction SQL
réécrite se vérifie avant/après dans une transaction `REPEATABLE READ` (résultats identiques, sinon `ROLLBACK`).

## Pièges connus

- **psycopg + fonctions SQL** : caster les paramètres (`%(x)s::uuid`, `::numeric`, `::integer`), sinon
  PostgreSQL ne trouve pas la fonction.
- **Choisir des morceaux à retirer** : retirer un bout de set ne coûte qu'un enchaînement, un algorithme glouton
  retire alors toujours l'ouverture et la fin (vu le 18/10/2026) → les bouts sont protégés. Un enchaînement
  inconnu (morceau non analysé) compte comme un enchaînement moyen, pas 0 : sinon les morceaux pas encore
  analysés partent toujours en premier.
- **`key_confidence` est un `real`** : une fonction SQL qui le reçoit le prend en `double precision` (un paramètre
  `numeric` n'est pas trouvé, et convertir en `numeric` changerait le calcul du score).
- **Spotify, mode développement (règles de février 2026)** : Premium requis pour le propriétaire de l'app,
  5 utilisateurs max. `POST /me/playlists` et `/playlists/{id}/items` (plus `/tracks`) ; dans les réponses,
  `tracks` → `items` et `track` → `item`. Plus de `GET /tracks?ids=` groupé ; recherche limitée à 10 résultats.
  Pas de `audio-features`, `new-releases`, `popularity`. L'ISRC (`external_ids`) est disponible.
  Redirect URI : `127.0.0.1`, pas `localhost`. Gérer les HTTP 429 (`Retry-After`).
  Écriture (vérifié le 16/10/2026) : `POST /me/playlists` (`public: false` → droit `playlist-modify-private`,
  le seul demandé), `POST /playlists/{id}/items` et `PUT /playlists/{id}/items` (remplace tout) : **100 morceaux
  max par requête**. « Supprimer » une playlist dans Spotify = ne plus la suivre : elle reste modifiable par l'API
  mais invisible ; avant de réexporter, vérifier qu'elle est encore dans `GET /me/playlists`.
  Recherche par ISRC (vérifié le 18/10/2026) : `GET /search?q=isrc:<ISRC>&type=track` marche, 75/75 morceaux
  de l'Explorer retrouvés, environ 0,26 s chacun ; plusieurs résultats possibles (single, album) au même ISRC.
- **Essentia** : aucune version pour Linux ARM → le worker doit tourner en x86_64.
- « address already in use » au `make up` : changer `DB_PORT`, `REDIS_PORT`, `API_PORT` ou `WEB_PORT` dans `.env`
  (sur la machine de dev, `DB_PORT=5433`). Entre conteneurs, les ports internes ne changent pas.
- Ruff ne vérifie pas les docstrings dans un module dont le nom commence par `_`.
- **`pyproject.toml` n'est pas monté** dans le conteneur (seuls `app/` et `tests/` le sont) : après l'avoir
  modifié, `make up` pour reconstruire. `pip install .` laisse aussi une copie figée du code dans `build/lib`,
  exclue de ruff (`extend-exclude`).
- **Front sur `http://127.0.0.1:4200`, jamais `localhost`** : la redirect URI Spotify et le cookie de session en
  dépendent. L'OAuth passe par le proxy Angular (`/api/auth/spotify/callback`) pour que front et API partagent
  la même origine.
- **Artistes dédoublonnés par nom** (`lower(name)`) : deux homonymes sont fusionnés (on ne stocke pas l'ID
  Spotify des artistes).
- **Prettier** : ne pas le lancer sur tout `web/src`, il reformate des fichiers existants. Le cibler sur les
  fichiers modifiés.
- Changer `TOKEN_ENCRYPTION_KEY` rend les jetons stockés illisibles : il faut se reconnecter à Spotify.
- Le worker exécute peu de tâches en parallèle (`max_jobs = 2`) : Essentia est gourmand en CPU.
- **Worker et code monté** : l'image installe `app` dans `site-packages` (`pip install .`). Le worker tourne
  avec `PYTHONPATH=/app` (code monté prioritaire) et `watchfiles` (relance le processus). Ne pas revenir à
  `arq --watch` : il redémarre sans réimporter le code, les modifications ne sont jamais prises en compte.
- **arq dédoublonne aussi sur le résultat gardé** : avec un `_job_id` fixe, une tâche terminée bloque une
  nouvelle mise en file tant que son résultat existe. D'où `keep_result = 0` ; le statut est dans
  `track.analysis_status`.
- **Les tests utilisent la base Redis 15** (forcée dans `tests/conftest.py`) : le worker de dev, sur la
  base 0, n'exécute pas leurs tâches.
- **Écart de BPM : `bpm_diff` (absolu, sert au score) ≠ `bpm_change` (signé en %, sert à l'affichage)**. Un
  enchaînement refusé garde `key_distance` et `tempo_ok` / `same_mode` pour expliquer pourquoi.
- **Extraits Deezer** : URL signée valable **15 min** (`hdnea=exp=…`, vérifié le 17/10/2026) → redemandée à
  l'écoute, gardée seulement en mémoire de la page (jusqu'à 2 min avant l'expiration). Le CDN répond
  `Access-Control-Allow-Origin: *` et accepte les `Range`. Le **navigateur** garde le MP3 dans son propre cache
  (`max-age` ≈ 140 jours) : hors de notre serveur, la règle n°5 reste respectée. Fondu par le volume de deux
  `<audio>` : coupure sèche sur iOS (volume non réglable par le code) ; Safari peut refuser `play()` après une
  requête (non testé).
- **Dans un test, `expect((a, b))` ne vérifie que `b`** (opérateur virgule) : comparer un tableau,
  `expect([a, b]).toEqual([…])`.
- **Spotify refuse les playlists des autres** (vérifié le 17/10/2026) : ses playlists éditoriales (Top 50…)
  répondent 404, une playlist publique d'un autre utilisateur 403. Découverte = **Deezer**
  (`GET /playlist/{id}/tracks` : ISRC, extrait, mais **artiste principal seulement**, sans les « feat. »).
- **Liens Deezer partagés par l'app** (vérifié le 18/10/2026 sur de vrais liens) : `https://link.deezer.com/s/<code>`
  répond **301** vers `link.deezer.com/?dest=<URL du site encodée>&…` → une seule requête, sans suivre la suite.
  Lien mort ou expiré : 302 vers `www.deezer.com/deezer-links-404`. L'ancien format `deezer.page.link` est mort
  (404). Playlist privée : refusée si `public` est faux, **non testé** (pas de compte Deezer). Le créateur d'une
  playlist d'utilisateur peut s'appeler « Anonymous ».
- **Synchronisations de l'Explorer en série** (`ExploreRepository.lock_sync`) : deux tops qui partagent des morceaux,
  recopiés en parallèle, donnaient un `DeadlockDetected`. Elles passent **devant** les analyses dans la file
  (`TaskQueue.enqueue_explore_sync` : heure prévue 6 h dans le passé ; jamais un jour ou plus, Redis refuse).
- **Progression d'analyse = morceaux `pending`**, pas « non `done` » : un morceau sans extrait ne sera jamais analysé.
- **Formulaire avec nos propres messages d'erreur** : ajouter `novalidate`, sinon un `<input type="number" max>`
  bloque l'envoi (validation native du navigateur) avant notre contrôle.
- **Fixtures `client` et `logged_in_client` = le même objet** (la seconde ajoute le cookie à la première) : pour
  tester un 401, écrire un test séparé qui ne demande que `client`.
- **Les tests PostgreSQL tournent sur la base de dev** (choix assumé), qui contient de vrais morceaux
  analysés : un test ne vérifie que **ses propres lignes** (filtre sur ses ID ou son `test_prefix`), jamais
  « le résultat entier ».
- **Pas de navigateur sur la machine de dev** (ni Chrome headless, ni Claude in Chrome) : pour regarder un
  graphique, rendre le SVG du composant en image avec `@resvg/resvg-js` installé dans le dossier temporaire
  (jamais dans le projet), le SVG étant extrait par un test temporaire supprimé ensuite.
- Postgres et Redis ne sont publiés que sur `127.0.0.1` (mots de passe de dev, Redis sans authentification).

## Mise en ligne (pas encore faite : à revoir le jour d'un déploiement)

Hébergeur et reverse proxy pas encore choisis. Déjà en place : `ENVIRONMENT=production` refuse de démarrer
avec un réglage de dev (cookie non `Secure`, clé de chiffrement vide, redirect URI en HTTP, mot de passe de dev
de la base) et masque `/docs`.

Reste à faire au déploiement : vrais mots de passe Postgres et Redis, conteneurs non-root, pas de `--reload`
ni de `watchfiles`, aucun port de base ou de Redis publié, reverse proxy HTTPS qui sert le front et `/api` sur
la même origine, avec rate limiting sur `/auth/spotify/login` (sans session, il écrit une clé Redis à chaque
appel) et en-têtes de sécurité (CSP, HSTS ; la CSP doit autoriser `media-src https://cdnt-preview.dzcdn.net` pour les
extraits), sauvegardes PostgreSQL, worker sur x86_64.

## Analyse audio (résultats des spikes, voir spikes/README.md)

- Source : **extrait Deezer de 30 s, retrouvé par ISRC** (`GET api.deezer.com/track/isrc:<ISRC>`).
- Essentia : `RhythmExtractor2013(method="multifeature")` pour le BPM, `KeyExtractor(profileType="edma")` pour
  la tonalité.
- Erreur typique : **tonique juste, majeur/mineur inversé** → `CamelotKey.parallel()` et bouton
  « inverser majeur/mineur » dans l'interface.
- Beatport/Mixgraph ne sont pas une vérité terrain ; Hooktheory (transcriptions humaines) est la meilleure référence.

## Feuille de route

Fait : spikes, schéma, squelette (Compose, API, worker, front, CI), règles de code, OAuth Spotify + import des
playlists, worker d'analyse (Deezer + Essentia), catalogue filtrable (page `/catalog`), bouton
« inverser majeur/mineur », page d'accueil, page Suggestions (`/suggestions/:trackId`, enchaînement au clic), playlists (lecture avec
la qualité des enchaînements, playlist en cours + « + Ajouter », glisser-déposer `@angular/cdk`), export vers
Spotify (playlist privée, réexport = mise à jour), export TXT (détaillé ou tracklist),
favoris (★, filtre, comptent dans « mes morceaux » ; pas d'import des titres likés Spotify).
Corrections manuelles (BPM avec ×2 / ÷2, tonalité, annuler ma correction).

**V1 terminée** (17/10/2026). Vérifié en réel : export Spotify, mise à jour au réexport, visible dans rekordbox.

V2, dans l'ordre (une étape à la fois, plan validé avant de coder) :
1. ~~**Écouter les extraits**~~ : fait (17/10/2026). Le navigateur lit directement l'URL Deezer ; le serveur ne
   télécharge, ne stocke ni ne relaie l'audio.
2. ~~**Noter les transitions**~~ : fait (17/10/2026). 1 à 5 et commentaire facultatif, sens A → B, table
   `transition_rating` telle quelle, depuis une playlist et les suggestions ; boutons en chiffres (les étoiles ★
   sont les favoris) ; compteur sur la page Playlists ; rendu à soigner plus tard. Le score n'est pas modifié tant
   qu'il n'y a pas quelques dizaines de notes. Pas de photo de l'enchaînement au moment de la note : l'analyse
   recalculera les composantes avec `transition` et les valeurs actuelles (corrigées).
3. **Énergie : mise de côté (17/10/2026)**, à reprendre plus tard. Plan du spike prêt : noter à l'aveugle (1 à 5)
   l'énergie des 32 morceaux de « vib », puis comparer (corrélation de Spearman) sonie EBU R128, RMS, danceability,
   taux d'attaques, centroïde spectral, complexité dynamique, un composite, et le BPM seul comme référence ; extraits
   analysés puis supprimés. Ensuite seulement : colonne, `effective_features`, réanalyse, filtre, courbe d'énergie,
   sens monter / tenir / redescendre. Limite : l'énergie de 30 s d'extrait n'est pas celle du morceau entier.
4. **Filtre « BPM suspects » : mis de côté (17/10/2026)**, à reprendre plus tard. Mesuré sur la bibliothèque :
   le BPM de Deezer ne sert pas de second avis (60 % absent, le reste d'accord avec Essentia) ; le critère « décalé
   de ses voisins de playlist » n'ajoute rien. Plan prêt : suspect si BPM < 90 ou > 155 et pas encore vérifié
   (environ 29 morceaux), badge « ½ ? » / « ×2 ? », bouton « Ce BPM est bon » (= correction à la même valeur).

5. **Explorer** (`/explore`, demandé le 17/10/2026) : tops et playlists éditoriales **Deezer** (Spotify les refuse),
   recopiés chaque jour dans le catalogue et analysés ; badge « Nouveau » et « Nouveaux pour moi seulement ».
   Livraison 1 (lire) : faite. Livraison 2 (ajouter / retirer une source par lien, visible par tous ; refus
   au-delà de 2 000 titres, pas d'autre limite) : faite le 18/10/2026, vérifiée dans le navigateur avec un lien
   du site. Livraison 3 (export Spotify des morceaux venus de Deezer, identifiant retrouvé par ISRC à l'export) :
   faite le 18/10/2026 ; vrai export pas encore vérifié. Un morceau introuvable est recherché à chaque export.

Prochaines idées (proposées le 18/10/2026, dans l'ordre conseillé ; une à la fois, plan validé avant de coder) :
1. ~~**Morceau pont**~~ : fait (18/10/2026). Sur un enchaînement refusé A → B d'une playlist, « Trouver un pont »
   propose les morceaux C tels que A → C et C → B passent, puis « Insérer ici ». Mesuré : 36 ms pour 5 recherches
   sur tout le catalogue ; vérifié dans le navigateur.
2. ~~**Chemin entre deux morceaux**~~ : fait (18/10/2026). Quand aucun pont n'existe, « Chercher un chemin »
   propose jusqu'à 3 chemins de 2 à 4 morceaux (le plus court, puis le meilleur maillon faible), insérés d'un coup.
   Coût : 0,35 s dans mes morceaux, 1,8 s dans tout le catalogue (906 morceaux, 88 160 enchaînements), en
   carré du nombre de morceaux : à surveiller. Préférence « BPM toujours dans le même sens » écartée pour
   l'instant. Vérifié dans le navigateur.
3. ~~**Réordonner une playlist**~~ : fait (18/10/2026). « Proposer un ordre » (ouverture comprise) : le moins
   d'enchaînements refusés, puis la meilleure somme des scores ; aperçu, puis « Appliquer ». Heuristique limitée à
   5 passes (399 morceaux : 1,7 s, 330 → 3 refus ; 30 passes = 7,2 s pour le même résultat). Limite : sans
   énergie, ne sait pas construire une montée. Parcours dans le navigateur pas encore vérifié.
4. **Courbe de la playlist** : 4a ~~courbe du BPM~~ faite et vérifiée dans le navigateur (18/10/2026) : BPM
   morceau par morceau, enchaînements colorés (bleu / rouge + ⚠, couleurs passées au validateur dataviz), la
   liste en dessous sert de tableau équivalent. 4b ~~roue de Camelot~~ faite (18/10/2026), redessinée après un
   premier rendu « pâteux » : petits points, noms à côté, un trait par paire sans flèche, arcs sur un même anneau.
5. ~~**Ce qui rentre dans mon set**~~ (idée de départ : « compatibles avec mes favoris ») : fait et vérifié dans le
   navigateur (18/10/2026). Référence = **playlist en cours** : mesuré, 2 favoris seulement (58 morceaux sur 531)
   et « mes morceaux » laisse tout passer (513 sur 513), alors qu'une playlist de 22 trie la moitié (251 sur 522).
   Livraison 1 : case « S'enchaîne avec ma playlist en cours » et badge « ↔ N morceaux » (pas une place !) dans
   l'Explorer et le catalogue (66 ms par page, 111 ms filtré). Livraison 2 : « Où le placer ? » (réparation d'un ⚠,
   puis les deux côtés, puis un seul ; « Insérer ici » à la bonne position ; 18 à 39 ms). À faire plus tard
   (niveau 3) : trier l'Explorer par meilleure place possible dans mon set.

Idées suivantes (retenues le 18/10/2026, dans l'ordre ; une à la fois, plan validé avant de coder) :
1. ~~**Durée du set et « couper pour tenir le créneau »**~~ : fait (18/10/2026). Créneau et part jouée (50 à
   100 %) enregistrés avec la playlist ; heure de passage de chaque morceau ; « Proposer quoi retirer » (d'abord ce
   qui répare un ⚠, puis ce qui casse le moins, le plus long à égalité ; jamais l'ouverture ni le dernier
   morceau), puis « Retirer ces morceaux » (tout ou rien). Peut retirer un morceau de plus que nécessaire (choix
   par dégâts, pas par durée). Rendu dans le navigateur pas encore vérifié.
2. **Carte de ma bibliothèque** : roue de Camelot en carte de chaleur (morceaux par tonalité) et histogramme des
   BPM ; un trou (tonalité ou plage de BPM absente) ouvre l'Explorer filtré dessus.
3. **Annuler la dernière modification d'une playlist** (ordre appliqué, pont, chemin, « Insérer ici »).
4. **Compteur sur l'accueil** : « N nouveaux morceaux de l'Explorer rentrent dans ton set en cours »
   (`playlist_fit`).

Écartées (18/10/2026) : points de mix intro / outro (impossible avec 30 s d'extrait) ; « mode cabine » (le mix se
fait dans rekordbox). À décider : journal « déjà joué », version extended (recherche Spotify limitée à 10
résultats), « energy boost » +7 (changerait la règle d'enchaînement), corrections globales (admin).

Retirés (16/10/2026) : **import XML rekordbox** (l'autrice utilise rekordbox seulement comme destination, via
Spotify) et donc **export M3U** (sans import rekordbox, aucun chemin de fichier audio : un M3U serait vide).
La source `rekordbox` reste dans le schéma et dans la priorité de `effective_features`, inutilisée : ne pas la
retirer (migration sans bénéfice).

Hors V2 (ne pas anticiper) : partage/commentaires, embeddings (pgvector) et recherche par texte,
génération de playlist par LLM.
