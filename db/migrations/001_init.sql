-- =============================================================================
-- Plateforme DJ — modèle de données V1 (PostgreSQL 16)
--
-- Principes :
--   1. Nos propres identifiants ; les ID Spotify/Deezer sont dans track_external_id.
--   2. Les playlists vivent ici ; Spotify n'est qu'une destination d'export.
--   3. Comptes utilisateurs à nous ; les services musicaux y sont *associés*.
--   4. BPM et tonalité : on garde TOUTES les valeurs (une ligne par source),
--      la valeur affichée est choisie à la lecture (effective_features).
--   5. Tonalité stockée en Camelot (numéro 1-12 + lettre A/B) pour les calculs.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS citext;

-- -----------------------------------------------------------------------------
-- Types
-- -----------------------------------------------------------------------------
CREATE TYPE user_role        AS ENUM ('user', 'admin');
CREATE TYPE music_provider   AS ENUM ('spotify', 'deezer');
CREATE TYPE analysis_source  AS ENUM ('manual', 'rekordbox', 'essentia');
CREATE TYPE analysis_status  AS ENUM ('pending', 'done', 'no_preview', 'failed');
CREATE TYPE playlist_visibility AS ENUM ('private', 'unlisted', 'public');
CREATE TYPE import_kind      AS ENUM ('spotify_playlist', 'spotify_liked', 'rekordbox_xml');
CREATE TYPE job_status       AS ENUM ('running', 'done', 'failed');

-- Clé Camelot : '8A' -> (8, 'A')
CREATE DOMAIN camelot_number AS smallint CHECK (VALUE BETWEEN 1 AND 12);
CREATE DOMAIN camelot_letter AS char(1)  CHECK (VALUE IN ('A', 'B'));  -- A = mineur, B = majeur

-- -----------------------------------------------------------------------------
-- Utilisateurs et comptes musicaux associés
-- -----------------------------------------------------------------------------
CREATE TABLE app_user (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email         citext NOT NULL UNIQUE,
    display_name  text   NOT NULL,
    password_hash text,                                  -- NULL si connexion uniquement via un tiers plus tard
    role          user_role NOT NULL DEFAULT 'user',
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE music_account (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    provider          music_provider NOT NULL,
    provider_user_id  text NOT NULL,
    access_token_enc  bytea NOT NULL,                    -- chiffré côté application, jamais en clair
    refresh_token_enc bytea,
    scopes            text[] NOT NULL DEFAULT '{}',
    expires_at        timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, provider),
    UNIQUE (provider, provider_user_id)
);

-- -----------------------------------------------------------------------------
-- Catalogue
-- -----------------------------------------------------------------------------
CREATE TABLE artist (
    id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL
);
CREATE INDEX artist_name_idx ON artist (lower(name));

CREATE TABLE track (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title           text NOT NULL,                       -- "Dernière danse"
    mix_name        text,                                -- "Techno Mix", "Extended Mix"...
    duration_ms     integer CHECK (duration_ms > 0),
    isrc            text UNIQUE,                         -- clé de correspondance entre plateformes
    analysis_status analysis_status NOT NULL DEFAULT 'pending',
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE track_artist (
    track_id  uuid NOT NULL REFERENCES track(id)  ON DELETE CASCADE,
    artist_id uuid NOT NULL REFERENCES artist(id) ON DELETE RESTRICT,
    position  smallint NOT NULL,                         -- ordre d'affichage (0 = artiste principal)
    PRIMARY KEY (track_id, artist_id)
);
CREATE INDEX track_artist_artist_idx ON track_artist (artist_id);

CREATE TABLE track_external_id (
    track_id    uuid NOT NULL REFERENCES track(id) ON DELETE CASCADE,
    provider    music_provider NOT NULL,
    external_id text NOT NULL,
    PRIMARY KEY (provider, external_id),
    UNIQUE (track_id, provider)
);

CREATE TABLE genre (
    id        serial PRIMARY KEY,
    name      text NOT NULL UNIQUE,                      -- "Tech House"
    parent_id integer REFERENCES genre(id)               -- "House"
);

CREATE TABLE track_genre (
    track_id uuid    NOT NULL REFERENCES track(id) ON DELETE CASCADE,
    genre_id integer NOT NULL REFERENCES genre(id) ON DELETE CASCADE,
    source   text    NOT NULL,                           -- 'deezer' | 'manual' ...
    PRIMARY KEY (track_id, genre_id)
);
CREATE INDEX track_genre_genre_idx ON track_genre (genre_id);

-- -----------------------------------------------------------------------------
-- Analyse : une ligne par (morceau, source, portée)
--   user_id NULL  -> valeur globale du catalogue (Essentia, ou correction admin)
--   user_id = X   -> valeur propre à l'utilisateur X (son rekordbox, sa correction)
-- Une colonne NULL veut dire « cette source n'a pas d'avis » sur ce champ.
-- -----------------------------------------------------------------------------
CREATE TABLE track_analysis (
    id               bigserial PRIMARY KEY,
    track_id         uuid NOT NULL REFERENCES track(id) ON DELETE CASCADE,
    source           analysis_source NOT NULL,
    user_id          uuid REFERENCES app_user(id) ON DELETE CASCADE,
    bpm              numeric(5,1) CHECK (bpm BETWEEN 40 AND 250),
    camelot_num      camelot_number,
    camelot_letter   camelot_letter,
    key_confidence   real CHECK (key_confidence BETWEEN 0 AND 1),
    analyzer_version text,                               -- ex. 'essentia-2.1b6/edma' : permet de réanalyser
    created_by       uuid REFERENCES app_user(id) ON DELETE SET NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    CHECK ((camelot_num IS NULL) = (camelot_letter IS NULL)),
    CHECK (bpm IS NOT NULL OR camelot_num IS NOT NULL),
    -- seul le manuel peut être global ET venir d'un humain ; rekordbox est toujours personnel
    CHECK (source <> 'rekordbox' OR user_id IS NOT NULL),
    CHECK (source <> 'essentia'  OR user_id IS NULL)
);
-- Une seule valeur courante par (morceau, source, portée) : on remplace, l'historique part en audit si besoin.
CREATE UNIQUE INDEX track_analysis_one_per_scope
    ON track_analysis (track_id, source, COALESCE(user_id, '00000000-0000-0000-0000-000000000000'));

-- -----------------------------------------------------------------------------
-- Bibliothèque utilisateur
-- -----------------------------------------------------------------------------
CREATE TABLE favorite (
    user_id    uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    track_id   uuid NOT NULL REFERENCES track(id)    ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, track_id)
);

CREATE TABLE playlist (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id       uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    name           text NOT NULL,
    description    text,
    visibility     playlist_visibility NOT NULL DEFAULT 'private',
    forked_from_id uuid REFERENCES playlist(id) ON DELETE SET NULL,   -- duplication (V2), gratuit à prévoir
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX playlist_owner_idx ON playlist (owner_id);

CREATE TABLE playlist_item (
    id          bigserial PRIMARY KEY,                   -- un même morceau peut apparaître deux fois
    playlist_id uuid NOT NULL REFERENCES playlist(id) ON DELETE CASCADE,
    track_id    uuid NOT NULL REFERENCES track(id)    ON DELETE RESTRICT,
    position    integer NOT NULL CHECK (position >= 0),
    added_at    timestamptz NOT NULL DEFAULT now(),
    -- DEFERRABLE : on peut réordonner toute la playlist dans une transaction
    CONSTRAINT playlist_item_position_uniq UNIQUE (playlist_id, position) DEFERRABLE INITIALLY DEFERRED
);

-- Lien vers la playlist créée chez le fournisseur : un nouvel export met à jour la même playlist.
CREATE TABLE playlist_export (
    playlist_id          uuid NOT NULL REFERENCES playlist(id) ON DELETE CASCADE,
    provider             music_provider NOT NULL,
    external_playlist_id text NOT NULL,
    last_synced_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (playlist_id, provider)
);

-- Retours sur les transitions (dirigés : A -> B n'est pas B -> A)
CREATE TABLE transition_rating (
    user_id       uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    from_track_id uuid NOT NULL REFERENCES track(id)    ON DELETE CASCADE,
    to_track_id   uuid NOT NULL REFERENCES track(id)    ON DELETE CASCADE,
    rating        smallint NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment       text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, from_track_id, to_track_id),
    CHECK (from_track_id <> to_track_id)
);
CREATE INDEX transition_rating_pair_idx ON transition_rating (from_track_id, to_track_id);

-- -----------------------------------------------------------------------------
-- Imports
-- -----------------------------------------------------------------------------
CREATE TABLE import_job (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    kind        import_kind NOT NULL,
    status      job_status NOT NULL DEFAULT 'running',
    stats       jsonb NOT NULL DEFAULT '{}',              -- {"total": 412, "matched": 398, ...}
    created_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);

-- Écran « morceaux non reconnus » de l'import rekordbox
CREATE TABLE rekordbox_unmatched (
    id                bigserial PRIMARY KEY,
    import_job_id     uuid NOT NULL REFERENCES import_job(id) ON DELETE CASCADE,
    rb_title          text NOT NULL,
    rb_artist         text,
    rb_duration_ms    integer,
    rb_bpm            numeric(5,1),
    rb_tonality       text,                               -- tel quel : "Fm", "8A"...
    rb_location       text,
    resolved_track_id uuid REFERENCES track(id) ON DELETE SET NULL
);

-- =============================================================================
-- Valeurs effectives pour un utilisateur
--
-- Priorité, champ par champ (BPM et tonalité sont choisis indépendamment) :
--   1. correction manuelle de l'utilisateur
--   2. son import rekordbox
--   3. correction manuelle globale (admin)
--   4. Essentia
-- p_user NULL -> vue globale (visiteur non connecté)
-- =============================================================================
CREATE FUNCTION source_rank(src analysis_source, is_personal boolean) RETURNS smallint
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN src = 'manual'    AND is_personal     THEN 1
        WHEN src = 'rekordbox'                     THEN 2
        WHEN src = 'manual'    AND NOT is_personal THEN 3
        WHEN src = 'essentia'                      THEN 4
    END::smallint
$$;

CREATE FUNCTION effective_features(p_user uuid)
RETURNS TABLE (
    track_id       uuid,
    bpm            numeric,
    bpm_source     analysis_source,
    camelot_num    smallint,
    camelot_letter char(1),
    key_source     analysis_source,
    key_confidence real
)
LANGUAGE sql STABLE AS $$
    WITH visible AS (
        SELECT a.*, source_rank(a.source, a.user_id IS NOT NULL) AS rnk
        FROM track_analysis a
        WHERE a.user_id IS NULL OR a.user_id = p_user
    ),
    best_bpm AS (
        SELECT DISTINCT ON (v.track_id) v.track_id, v.bpm, v.source
        FROM visible v WHERE v.bpm IS NOT NULL
        ORDER BY v.track_id, v.rnk
    ),
    best_key AS (
        SELECT DISTINCT ON (v.track_id) v.track_id, v.camelot_num, v.camelot_letter, v.source,
               -- une valeur saisie par un humain est sûre ; sinon on garde la confiance calculée
               CASE WHEN v.source = 'manual' THEN 1.0::real
                    WHEN v.source = 'rekordbox' THEN COALESCE(v.key_confidence, 0.9::real)
                    ELSE v.key_confidence END AS conf
        FROM visible v WHERE v.camelot_num IS NOT NULL
        ORDER BY v.track_id, v.rnk
    )
    SELECT COALESCE(b.track_id, k.track_id), b.bpm, b.source,
           k.camelot_num, k.camelot_letter, k.source, k.conf
    FROM best_bpm b FULL JOIN best_key k ON k.track_id = b.track_id
$$;

-- =============================================================================
-- Suggestions : morceaux compatibles avec un morceau de départ
--
-- Tonalité (roue Camelot) :
--   même clé                         1.00  'same'
--   ±1 même lettre                   0.90  'adjacent'
--   même numéro, autre lettre        0.85  'relative'
--   ±2 même lettre                   0.50  'energy_shift'
--   autre                            exclu
--   -> pondéré par la confiance : une tonalité incertaine compte moins.
-- BPM : écart relatif ; le demi/double tempo (87 <-> 174) est accepté mais sa part
--       de score est divisée par deux (enchaînement plus délicat).
-- Score final = 0.6 * tonalité + 0.4 * BPM (à régler plus tard avec les retours).
-- =============================================================================
CREATE FUNCTION suggest_tracks(
    p_user          uuid,
    p_seed          uuid,
    p_bpm_tolerance numeric DEFAULT 0.06,                -- ±6 %
    p_limit         integer DEFAULT 20
)
RETURNS TABLE (
    track_id   uuid,
    bpm        numeric,
    camelot    text,
    key_move   text,
    half_double boolean,
    bpm_diff   numeric,
    score      numeric
)
LANGUAGE sql STABLE AS $$
    WITH f AS (SELECT * FROM effective_features(p_user)),
    seed AS (SELECT * FROM f WHERE f.track_id = p_seed),
    cand AS (
        SELECT c.*,
               -- distance circulaire sur la roue (0..6)
               LEAST(abs(c.camelot_num - s.camelot_num), 12 - abs(c.camelot_num - s.camelot_num)) AS dist,
               c.camelot_letter = s.camelot_letter AS same_letter,
               abs(c.bpm - s.bpm) / s.bpm AS direct_diff,
               LEAST(abs(c.bpm * 2 - s.bpm), abs(c.bpm / 2 - s.bpm)) / s.bpm AS half_double_diff,
               LEAST(COALESCE(c.key_confidence, 0.5), COALESCE(s.key_confidence, 0.5)) AS conf
        FROM f c CROSS JOIN seed s
        WHERE c.track_id <> s.track_id
          AND c.bpm IS NOT NULL AND c.camelot_num IS NOT NULL
    ),
    tempo AS (
        SELECT cand.*,
               -- on garde le tempo direct s'il passe, sinon le demi/double tempo
               (direct_diff > p_bpm_tolerance) AS half_double,
               CASE WHEN direct_diff <= p_bpm_tolerance THEN direct_diff ELSE half_double_diff END AS rel_diff
        FROM cand
    ),
    scored AS (
        SELECT tempo.*,
               CASE WHEN dist = 0 AND same_letter     THEN 'same'
                    WHEN dist = 1 AND same_letter     THEN 'adjacent'
                    WHEN dist = 0 AND NOT same_letter THEN 'relative'
                    WHEN dist = 2 AND same_letter     THEN 'energy_shift' END AS move,
               CASE WHEN dist = 0 AND same_letter     THEN 1.00
                    WHEN dist = 1 AND same_letter     THEN 0.90
                    WHEN dist = 0 AND NOT same_letter THEN 0.85
                    WHEN dist = 2 AND same_letter     THEN 0.50 END AS key_score
        FROM tempo
        WHERE rel_diff <= p_bpm_tolerance
    )
    SELECT s.track_id, s.bpm,
           s.camelot_num || s.camelot_letter,
           s.move,
           s.half_double,
           round(s.rel_diff * 100, 1),
           round((0.6 * s.key_score * (0.5 + 0.5 * s.conf)
                + 0.4 * (1 - s.rel_diff / p_bpm_tolerance)
                      * CASE WHEN s.half_double THEN 0.5 ELSE 1 END)::numeric, 3)
    FROM scored s
    WHERE s.move IS NOT NULL
    ORDER BY 7 DESC
    LIMIT p_limit
$$;
