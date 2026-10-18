-- =============================================================================
-- 007 : tous les enchaînements compatibles entre des morceaux donnés (le « graphe » des enchaînements).
--
-- Sert à chercher un chemin de A à B en plusieurs morceaux : le SQL donne les arêtes (règle `transition`,
-- score `transition_score`), la recherche elle-même se fait en Python (app/domain/set_path.py).
-- Mesuré le 18/10/2026 : 906 morceaux analysés -> 88 160 enchaînements compatibles en 1,2 s.
--
-- Idempotent (CREATE OR REPLACE) : en dev,
--   docker compose exec -T db psql -U dj -d dj -f /docker-entrypoint-initdb.d/007_transition_edges.sql
-- =============================================================================

-- Enchaînements compatibles entre les morceaux de p_ids (valeurs vues par p_user), dans les deux sens.
CREATE OR REPLACE FUNCTION transition_edges(
    p_user          uuid,
    p_ids           uuid[],
    p_bpm_tolerance numeric DEFAULT 0.06
)
RETURNS TABLE (
    from_id      uuid,
    to_id        uuid,
    key_move     text,
    key_distance smallint,
    half_double  boolean,
    bpm_diff     numeric,
    bpm_change   numeric,
    score        numeric
)
LANGUAGE sql STABLE AS $$
    WITH f AS (
        SELECT * FROM effective_features(p_user)
        WHERE track_id = ANY(p_ids) AND bpm IS NOT NULL AND camelot_num IS NOT NULL
    )
    SELECT a.track_id, b.track_id, tr.key_move, tr.key_distance, tr.half_double, tr.bpm_diff, tr.bpm_change,
           transition_score(tr.key_move, tr.half_double, tr.bpm_diff,
                            LEAST(COALESCE(a.key_confidence, 0.5), COALESCE(b.key_confidence, 0.5)),
                            p_bpm_tolerance)
    FROM f a
    JOIN f b ON b.track_id <> a.track_id
    CROSS JOIN LATERAL transition(a.bpm, a.camelot_num, a.camelot_letter::text,
                                  b.bpm, b.camelot_num, b.camelot_letter::text, p_bpm_tolerance) tr
    WHERE tr.compatible
$$;
