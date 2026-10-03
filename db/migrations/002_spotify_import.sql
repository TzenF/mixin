-- =============================================================================
-- 002 — Connexion Spotify et import des playlists
--
--   1. L'utilisateur est créé à la connexion Spotify, qui ne fournit pas d'email
--      (scope user-read-email non demandé) : email devient facultatif.
--   2. Sessions de connexion : le cookie contient un jeton aléatoire, la base n'en garde que l'empreinte.
--   3. Playlist importée : on mémorise sa playlist d'origine pour qu'un réimport mette à jour la même.
-- =============================================================================

ALTER TABLE app_user ALTER COLUMN email DROP NOT NULL;   -- UNIQUE accepte plusieurs NULL

CREATE TABLE user_session (
    token_hash bytea PRIMARY KEY,                        -- SHA-256 du jeton du cookie, jamais le jeton lui-même
    user_id    uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);
CREATE INDEX user_session_user_idx ON user_session (user_id);

ALTER TABLE playlist
    ADD COLUMN source_provider    music_provider,        -- NULL : playlist créée dans l'application
    ADD COLUMN source_external_id text,
    ADD CONSTRAINT playlist_source_complete CHECK ((source_provider IS NULL) = (source_external_id IS NULL));

-- Une playlist d'origine n'est importée qu'une fois par utilisateur : le réimport met à jour la même.
CREATE UNIQUE INDEX playlist_source_uniq
    ON playlist (owner_id, source_provider, source_external_id)
    WHERE source_provider IS NOT NULL;
