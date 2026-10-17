-- =============================================================================
-- 005 : Explorer — sources de découverte (tops et playlists éditoriales Deezer), partagées par tous.
--
-- Une source n'est PAS une playlist : elle n'a pas de propriétaire et ses morceaux ne comptent pas dans
-- « mes morceaux » (seuls mes playlists et mes favoris y comptent).
--
-- Idempotent : en dev,
--   docker compose exec -T db psql -U dj -d dj -f /docker-entrypoint-initdb.d/005_explore.sql
-- =============================================================================

CREATE TABLE IF NOT EXISTS explore_source (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    provider       music_provider NOT NULL,
    external_id    text NOT NULL,
    title          text NOT NULL,
    curator        text,                                    -- « Deezer Charts », « Laeti - Deezer Dance & EDM Editor »…
    added_by       uuid REFERENCES app_user(id) ON DELETE SET NULL,   -- NULL : source par défaut
    last_synced_at timestamptz,
    last_error     text,                                    -- dernier échec de synchronisation (NULL si réussie)
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (provider, external_id)
);

-- Classement actuel de chaque source ; un morceau sorti d'un top reste dans le catalogue (seule la ligne part).
CREATE TABLE IF NOT EXISTS explore_item (
    source_id uuid    NOT NULL REFERENCES explore_source(id) ON DELETE CASCADE,
    track_id  uuid    NOT NULL REFERENCES track(id)          ON DELETE CASCADE,
    position  integer NOT NULL CHECK (position >= 0),
    PRIMARY KEY (source_id, track_id)
);
CREATE INDEX IF NOT EXISTS explore_item_track_idx ON explore_item (track_id);

-- Sources par défaut (vérifiées le 17/10/2026 sur l'API publique de Deezer).
INSERT INTO explore_source (provider, external_id, title, curator) VALUES
    ('deezer', '1109890291',  'Top France',        'Deezer Charts'),
    ('deezer', '3155776842',  'Top Worldwide',     'Deezer Charts'),
    ('deezer', '2021502402',  'Melodic Techno',    'Laeti - Deezer Dance & EDM Editor'),
    ('deezer', '13577698981', 'Hard Techno',       'Laeti - Deezer Dance & EDM Editor'),
    ('deezer', '1275756721',  'Techno Tunnel',     'Laeti - Deezer Dance & EDM Editor'),
    ('deezer', '10578670022', 'Techno Essentials', 'Laeti - Deezer Dance & EDM Editor')
ON CONFLICT (provider, external_id) DO NOTHING;
