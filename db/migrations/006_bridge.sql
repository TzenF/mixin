-- =============================================================================
-- 006 : morceau pont. Pour un enchaînement refusé A -> B, les morceaux C tels que A -> C et C -> B passent.
--
-- La formule du score sort de suggest_tracks dans transition_score, pour servir aussi aux ponts.
-- suggest_tracks garde sa signature et ses résultats (vérifié avant/après en REPEATABLE READ).
-- Score d'un pont = le plus faible de ses deux enchaînements : un pont vaut ce que vaut son pire côté.
--
-- Idempotent (CREATE OR REPLACE) : en dev,
--   docker compose exec -T db psql -U dj -d dj -f /docker-entrypoint-initdb.d/006_bridge.sql
-- =============================================================================

-- Score d'un enchaînement compatible (0 à 1) : 60 % tonalité (pondérée par la confiance), 40 % tempo.
CREATE OR REPLACE FUNCTION transition_score(
    p_key_move    text,
    p_half_double boolean,
    p_rel_diff    numeric,
    p_confidence  double precision,  -- key_confidence est un real : même calcul qu'avant (en double precision)
    p_tolerance   numeric
)
RETURNS numeric
LANGUAGE sql IMMUTABLE AS $$
    SELECT round((0.6 * CASE p_key_move WHEN 'same'         THEN 1.00
                                        WHEN 'adjacent'     THEN 0.90
                                        WHEN 'relative'     THEN 0.85
                                        WHEN 'diagonal'     THEN 0.75
                                        WHEN 'energy_shift' THEN 0.50 END
                        * (0.5 + 0.5 * p_confidence)
                  + 0.4 * (1 - p_rel_diff / p_tolerance)
                        * CASE WHEN p_half_double THEN 0.5 ELSE 1 END)::numeric, 3)
$$;

-- Comme en 004 ; le score passe par transition_score.
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
               LEAST(COALESCE(c.key_confidence, 0.5), COALESCE(s.key_confidence, 0.5)) AS conf
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
           transition_score(s.move, s.is_half_double, s.rel_diff, s.conf, p_bpm_tolerance)
    FROM scored s
    ORDER BY 7 DESC
    LIMIT p_limit
$$;

-- Morceaux C qui font le pont entre A et B (A -> C et C -> B compatibles), du meilleur au moins bon.
CREATE OR REPLACE FUNCTION bridge_tracks(
    p_user          uuid,
    p_from          uuid,
    p_to            uuid,
    p_bpm_tolerance numeric DEFAULT 0.06,
    p_limit         integer DEFAULT 20
)
RETURNS TABLE (
    track_id         uuid,
    bpm              numeric,
    camelot          text,
    score            numeric,
    in_key_move      text,
    in_key_distance  smallint,
    in_half_double   boolean,
    in_bpm_diff      numeric,
    in_bpm_change    numeric,
    in_score         numeric,
    out_key_move     text,
    out_key_distance smallint,
    out_half_double  boolean,
    out_bpm_diff     numeric,
    out_bpm_change   numeric,
    out_score        numeric
)
LANGUAGE sql STABLE AS $$
    WITH f AS (SELECT * FROM effective_features(p_user)),
    a AS (SELECT * FROM f WHERE f.track_id = p_from),
    b AS (SELECT * FROM f WHERE f.track_id = p_to),
    legs AS (
        SELECT c.track_id AS id, c.bpm AS cand_bpm, c.camelot_num || c.camelot_letter AS cand_camelot,
               t_in.key_move AS in_move, t_in.key_distance AS in_dist, t_in.half_double AS in_hd,
               t_in.bpm_diff AS in_diff, t_in.bpm_change AS in_change,
               transition_score(t_in.key_move, t_in.half_double, t_in.bpm_diff,
                                LEAST(COALESCE(c.key_confidence, 0.5), COALESCE(a.key_confidence, 0.5)),
                                p_bpm_tolerance) AS in_sc,
               t_out.key_move AS out_move, t_out.key_distance AS out_dist, t_out.half_double AS out_hd,
               t_out.bpm_diff AS out_diff, t_out.bpm_change AS out_change,
               transition_score(t_out.key_move, t_out.half_double, t_out.bpm_diff,
                                LEAST(COALESCE(c.key_confidence, 0.5), COALESCE(b.key_confidence, 0.5)),
                                p_bpm_tolerance) AS out_sc
        FROM f c
        CROSS JOIN a
        CROSS JOIN b
        CROSS JOIN LATERAL transition(a.bpm, a.camelot_num, a.camelot_letter::text,
                                      c.bpm, c.camelot_num, c.camelot_letter::text, p_bpm_tolerance) t_in
        CROSS JOIN LATERAL transition(c.bpm, c.camelot_num, c.camelot_letter::text,
                                      b.bpm, b.camelot_num, b.camelot_letter::text, p_bpm_tolerance) t_out
        WHERE c.track_id NOT IN (a.track_id, b.track_id) AND t_in.compatible AND t_out.compatible
    )
    SELECT l.id, l.cand_bpm, l.cand_camelot, LEAST(l.in_sc, l.out_sc),
           l.in_move, l.in_dist, l.in_hd, l.in_diff, l.in_change, l.in_sc,
           l.out_move, l.out_dist, l.out_hd, l.out_diff, l.out_change, l.out_sc
    FROM legs l
    ORDER BY 4 DESC, 1
    LIMIT p_limit
$$;
