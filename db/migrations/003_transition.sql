-- =============================================================================
-- 003 : règle d'enchaînement partagée (transition) et suggest_tracks réécrite pour l'utiliser.
--
-- Idempotent (CREATE OR REPLACE) : en dev, s'applique sans effacer la base avec
--   docker compose exec -T db psql -U dj -d dj -f /docker-entrypoint-initdb.d/003_transition.sql
-- suggest_tracks garde sa signature, ses résultats et son score : seule la règle est sortie.
-- =============================================================================

-- Enchaînement du morceau A vers le morceau B.
--   key_move     : 'same' | 'adjacent' | 'relative' | 'energy_shift', NULL si la tonalité ne va pas
--   key_distance : crans sur la roue Camelot (0..6), toujours rempli : explique un enchaînement refusé
--   half_double  : vrai si le tempo direct dépasse la tolérance (on compare alors au demi/double tempo)
--   bpm_diff     : écart relatif absolu retenu (direct, sinon demi/double) : sert au score
--   bpm_change   : écart signé en % du tempo direct (+1.2 = on accélère) : sert à l'affichage
--   compatible   : tonalité acceptée ET écart dans la tolérance
-- Aucune ligne si un BPM ou une tonalité manque.
CREATE OR REPLACE FUNCTION transition(
    a_bpm       numeric,
    a_num       smallint,
    a_letter    text,
    b_bpm       numeric,
    b_num       smallint,
    b_letter    text,
    p_tolerance numeric DEFAULT 0.06
)
RETURNS TABLE (
    key_move     text,
    key_distance smallint,
    half_double  boolean,
    bpm_diff     numeric,
    bpm_change   numeric,
    compatible   boolean
)
LANGUAGE sql IMMUTABLE AS $$
    WITH measures AS (
        SELECT LEAST(abs(b_num - a_num), 12 - abs(b_num - a_num))::smallint AS dist,
               b_letter = a_letter AS same_letter,
               abs(b_bpm - a_bpm) / a_bpm AS direct_diff,
               LEAST(abs(b_bpm * 2 - a_bpm), abs(b_bpm / 2 - a_bpm)) / a_bpm AS half_double_diff
        WHERE a_bpm IS NOT NULL AND a_num IS NOT NULL AND a_letter IS NOT NULL
          AND b_bpm IS NOT NULL AND b_num IS NOT NULL AND b_letter IS NOT NULL
    ),
    judged AS (
        SELECT m.*,
               CASE WHEN m.dist = 0 AND m.same_letter     THEN 'same'
                    WHEN m.dist = 1 AND m.same_letter     THEN 'adjacent'
                    WHEN m.dist = 0 AND NOT m.same_letter THEN 'relative'
                    WHEN m.dist = 2 AND m.same_letter     THEN 'energy_shift' END AS move,
               (m.direct_diff > p_tolerance) AS is_half_double,
               CASE WHEN m.direct_diff <= p_tolerance THEN m.direct_diff ELSE m.half_double_diff END AS rel_diff
        FROM measures m
    )
    SELECT j.move, j.dist, j.is_half_double, j.rel_diff,
           round((b_bpm - a_bpm) / a_bpm * 100, 1),
           j.move IS NOT NULL AND j.rel_diff <= p_tolerance
    FROM judged j
$$;

-- Même signature et même score qu'en 001 ; la règle d'enchaînement vient maintenant de transition().
CREATE OR REPLACE FUNCTION suggest_tracks(
    p_user          uuid,
    p_seed          uuid,
    p_bpm_tolerance numeric DEFAULT 0.06,
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
    scored AS (
        SELECT c.track_id AS id, c.bpm AS cand_bpm, c.camelot_num, c.camelot_letter,
               tr.key_move AS move, tr.half_double AS is_half_double, tr.bpm_diff AS rel_diff,
               LEAST(COALESCE(c.key_confidence, 0.5), COALESCE(s.key_confidence, 0.5)) AS conf,
               CASE tr.key_move WHEN 'same'         THEN 1.00
                                WHEN 'adjacent'     THEN 0.90
                                WHEN 'relative'     THEN 0.85
                                WHEN 'energy_shift' THEN 0.50 END AS key_score
        FROM f c
        CROSS JOIN seed s
        CROSS JOIN LATERAL transition(s.bpm, s.camelot_num, s.camelot_letter::text,
                                      c.bpm, c.camelot_num, c.camelot_letter::text, p_bpm_tolerance) tr
        WHERE c.track_id <> s.track_id AND tr.compatible
    )
    SELECT s.id, s.cand_bpm,
           s.camelot_num || s.camelot_letter,
           s.move,
           s.is_half_double,
           round(s.rel_diff * 100, 1),
           round((0.6 * s.key_score * (0.5 + 0.5 * s.conf)
                + 0.4 * (1 - s.rel_diff / p_bpm_tolerance)
                      * CASE WHEN s.is_half_double THEN 0.5 ELSE 1 END)::numeric, 3)
    FROM scored s
    ORDER BY 7 DESC
    LIMIT p_limit
$$;
