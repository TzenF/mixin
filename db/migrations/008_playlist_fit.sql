-- =============================================================================
-- 008 : « ce qui rentre dans mon set » : avec combien de morceaux d'une playlist chaque morceau s'enchaîne.
--
-- Pour chaque morceau analysé qui n'est PAS déjà dans la playlist : nombre de morceaux de la playlist avec
-- lesquels il s'enchaîne dans un sens ou dans l'autre (il peut venir avant ou après). Règle `transition`.
-- Sert au filtre « S'enchaîne avec ma playlist en cours » du catalogue et de l'Explorer.
--
-- Idempotent (CREATE OR REPLACE) : en dev,
--   docker compose exec -T db psql -U dj -d dj -f /docker-entrypoint-initdb.d/008_playlist_fit.sql
-- =============================================================================

CREATE OR REPLACE FUNCTION playlist_fit(
    p_user          uuid,
    p_playlist      uuid,
    p_bpm_tolerance numeric DEFAULT 0.06
)
RETURNS TABLE (
    track_id  uuid,
    fit_count integer
)
LANGUAGE sql STABLE AS $$
    WITH f AS (
        SELECT * FROM effective_features(p_user) WHERE bpm IS NOT NULL AND camelot_num IS NOT NULL
    ),
    inside AS (
        SELECT DISTINCT f.* FROM f JOIN playlist_item pi ON pi.track_id = f.track_id
        WHERE pi.playlist_id = p_playlist
    )
    SELECT c.track_id, count(*)::integer
    FROM f c
    JOIN inside p ON p.track_id <> c.track_id
    CROSS JOIN LATERAL transition(p.bpm, p.camelot_num, p.camelot_letter::text,
                                  c.bpm, c.camelot_num, c.camelot_letter::text, p_bpm_tolerance) after_it
    CROSS JOIN LATERAL transition(c.bpm, c.camelot_num, c.camelot_letter::text,
                                  p.bpm, p.camelot_num, p.camelot_letter::text, p_bpm_tolerance) before_it
    WHERE c.track_id NOT IN (SELECT track_id FROM inside)
      AND (after_it.compatible OR before_it.compatible)
    GROUP BY c.track_id
$$;
