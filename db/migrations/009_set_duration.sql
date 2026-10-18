-- =============================================================================
-- 009 : durée du set. Créneau visé et part jouée de chaque morceau, enregistrés avec la playlist.
--
-- slot_minutes   : durée du créneau (NULL : pas de créneau).
-- played_percent : part de chaque morceau réellement jouée en mixant (100 = en entier) ; les heures de passage
--                  et le total en tiennent compte. La durée vient de track.duration_ms (Spotify ou Deezer).
--
-- Idempotent : en dev,
--   docker compose exec -T db psql -U dj -d dj -f /docker-entrypoint-initdb.d/009_set_duration.sql
-- =============================================================================

ALTER TABLE playlist
    ADD COLUMN IF NOT EXISTS slot_minutes integer CHECK (slot_minutes BETWEEN 1 AND 1440),
    ADD COLUMN IF NOT EXISTS played_percent smallint NOT NULL DEFAULT 100
        CHECK (played_percent BETWEEN 50 AND 100);
