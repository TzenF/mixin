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
| Morceaux en base | `app/adapters/track_repository.py` → `TrackRepository` |
| Lancer une analyse | `app/adapters/queue.py` → `TaskQueue.enqueue_analysis` (déjà dédoublonné) |
| Dépendances de route | `app/api/deps.py` → `get_db`, `get_queue`, `get_track_repository` |
| Valeur BPM/tonalité à afficher | SQL `effective_features(user)` |
| Morceaux compatibles | SQL `suggest_tracks(user, seed, tolerance, limit)` |
| Styles | `web/src/styles/_tokens.scss`, `_mixins.scss` (`page`, `panel`, `status`, `reset-list`, `button-primary`, `focus-ring`, `text-muted`) |

Tenir ce tableau à jour quand on ajoute un élément réutilisable.

## Commandes

Tout tourne dans Docker. Sur la machine de dev (Chromebook / Crostini), **`DOCKER_BUILDKIT=0` est obligatoire**
(le Makefile l'exporte).

```bash
make up          # construit et démarre tout — front :4200, API :8000/docs
make test        # tests back (pytest) + front (vitest)
make lint        # ruff check + ruff format --check (dont docstrings)
make logs | make down | make psql
make reset-db    # efface la base et rejoue les migrations
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
| **LLM** (hors V1) | Uniquement pour **traduire une demande en filtres** ; le moteur choisit les morceaux | Laisser le LLM choisir les morceaux (enchaînements faux) |
| **Calcul des suggestions à la volée** en SQL | Suffisant à l'échelle actuelle | Pré-calculer toutes les paires |

## Modèle de données (décisions à respecter)

- **Nos propres UUID** partout. Les ID Spotify/Deezer vont dans `track_external_id`. L'**ISRC** est la clé
  de correspondance entre plateformes.
- **Les playlists vivent dans notre base** ; Spotify n'est qu'une destination d'export (`playlist_export`).
- **Comptes utilisateurs à nous** ; les services musicaux sont *associés* (`music_account`), jetons chiffrés.
- **BPM / tonalité : une ligne par source dans `track_analysis`, jamais écrasée.** La valeur affichée est
  calculée à la lecture par `effective_features(user)` avec la priorité :
  correction perso > rekordbox perso > correction admin (globale) > Essentia.
- Tonalité stockée en Camelot (`camelot_num` 1–12 + `camelot_letter` A=mineur / B=majeur).

Migrations : le dossier est monté dans `/docker-entrypoint-initdb.d`, donc **exécuté seulement sur un volume
vide**. Nouveau fichier numéroté, puis `make reset-db` en dev.

## Pièges connus

- **psycopg + fonctions SQL** : caster les paramètres (`%(x)s::uuid`, `::numeric`, `::integer`), sinon
  PostgreSQL ne trouve pas la fonction.
- **Spotify, mode développement (règles de février 2026)** : Premium requis pour le propriétaire de l'app,
  5 utilisateurs max. `POST /me/playlists` et `/playlists/{id}/items` (plus `/tracks`) ; dans les réponses,
  `tracks` → `items` et `track` → `item`. Plus de `GET /tracks?ids=` groupé ; recherche limitée à 10 résultats.
  Pas de `audio-features`, `new-releases`, `popularity`. L'ISRC (`external_ids`) est disponible.
  Redirect URI : `127.0.0.1`, pas `localhost`. Gérer les HTTP 429 (`Retry-After`).
- **Essentia** : aucune version pour Linux ARM → le worker doit tourner en x86_64.
- « address already in use » au `make up` : changer `DB_PORT`, `REDIS_PORT`, `API_PORT` ou `WEB_PORT` dans `.env`
  (sur la machine de dev, `DB_PORT=5433`). Entre conteneurs, les ports internes ne changent pas.
- Ruff ne vérifie pas les docstrings dans un module dont le nom commence par `_`.
- Le worker exécute peu de tâches en parallèle (`max_jobs = 2`) : Essentia est gourmand en CPU.

## Analyse audio (résultats des spikes, voir spikes/README.md)

- Source : **extrait Deezer de 30 s, retrouvé par ISRC** (`GET api.deezer.com/track/isrc:<ISRC>`).
- Essentia : `RhythmExtractor2013(method="multifeature")` pour le BPM, `KeyExtractor(profileType="edma")` pour
  la tonalité.
- Erreur typique : **tonique juste, majeur/mineur inversé** → `CamelotKey.parallel()` et bouton
  « inverser majeur/mineur » dans l'interface.
- Beatport/Mixgraph ne sont pas une vérité terrain ; Hooktheory (transcriptions humaines) est la meilleure référence.

## Feuille de route V1

Fait : spikes, schéma, squelette (Compose, API, worker, front, CI), règles de code.
À faire, dans l'ordre : OAuth Spotify + import des playlists → worker Deezer + Essentia → catalogue filtrable,
suggestions, playlists, favoris → export Spotify / TXT / M3U → import XML rekordbox (avec écran des morceaux
non reconnus) et corrections manuelles.

Hors V1 (ne pas anticiper) : extraits audio dans le navigateur, partage/commentaires, page Discover,
embeddings (pgvector) et recherche par texte, génération de playlist par LLM.
