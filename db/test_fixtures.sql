-- Données de test (valeurs Essentia réelles de la playlist « vib ») + vérifications.
-- Lancer :  psql -v ON_ERROR_STOP=1 -f schema.sql -f test.sql

\set ON_ERROR_STOP 1
\pset footer off

INSERT INTO app_user (id, email, display_name, role) VALUES
  ('00000000-0000-0000-0000-00000000000a', 'katia@example.com', 'Katia', 'admin'),
  ('00000000-0000-0000-0000-00000000000b', 'bob@example.com',   'Bob',   'user');

CREATE TEMP TABLE seed (title text, artist text, isrc text, bpm numeric, cam text, conf real);
INSERT INTO seed VALUES
  ('Where Have You Been',  'Rihanna',         'USUM71118074', 128.4, '5A',  0.95),
  ('Don''t Wake Me Up',    'James Hype',      'GBUM72500069', 130.1, '5A',  0.98),
  ('Von dutch',            'Charli xcx',      'USAT22313737', 129.7, '4A',  0.97),
  ('TESLA',                'Mau P',           'NL8RL2530184', 132.0, '4A',  0.96),
  ('Made My Night',        'LE SSERAFIM',     'USA2P2664283', 129.9, '7A',  0.92),
  ('Sweet Dreams',         'Perfect Pitch',   'DEMA61906894', 135.1, '7A',  0.91),
  ('Dernière danse',       'Indila',          'FRUM72302505', 141.9, '5A',  0.89),
  ('Losing It',            'FISHER',          'CA5KR1821202', 124.0, '6A',  0.60),
  ('FE!N',                 'ILYAA',           'NLT2H2601813', 162.2, '5B',  0.95),
  ('Free Your Mind',       'Prospa',          'QM6MZ2647619', 127.9, '10A', 0.60),
  ('Half-time test',       'Test',            'TEST00000001',  64.5, '5A',  0.90);

WITH t AS (
  INSERT INTO track (title, isrc, analysis_status)
  SELECT title, isrc, 'done' FROM seed RETURNING id, isrc
)
INSERT INTO track_analysis (track_id, source, bpm, camelot_num, camelot_letter, key_confidence, analyzer_version)
SELECT t.id, 'essentia', s.bpm, left(s.cam, -1)::smallint, right(s.cam, 1), s.conf, 'essentia-2.1b6/edma'
FROM t JOIN seed s USING (isrc);

CREATE TEMP VIEW tid AS SELECT title, id FROM track;

\echo '=== 1. Suggestions depuis « Where Have You Been » (128.4 BPM, 5A), vue globale ==='
SELECT t.title, s.bpm, s.camelot, s.key_move, s.half_double AS "demi/double", s.bpm_diff AS "écart %", s.score
FROM suggest_tracks(NULL, (SELECT id FROM tid WHERE title = 'Where Have You Been')) s
JOIN track t ON t.id = s.track_id;

\echo '=== 2. Katia importe son rekordbox : TESLA y est en 7B ==='
INSERT INTO track_analysis (track_id, source, user_id, bpm, camelot_num, camelot_letter)
VALUES ((SELECT id FROM tid WHERE title = 'TESLA'), 'rekordbox',
        '00000000-0000-0000-0000-00000000000a', 132.0, 7, 'B');

SELECT 'Katia' AS vue, t.title, s.camelot, s.key_move, s.score
FROM suggest_tracks('00000000-0000-0000-0000-00000000000a', (SELECT id FROM tid WHERE title = 'Where Have You Been')) s
JOIN track t ON t.id = s.track_id WHERE t.title = 'TESLA'
UNION ALL
SELECT 'Bob', t.title, s.camelot, s.key_move, s.score
FROM suggest_tracks('00000000-0000-0000-0000-00000000000b', (SELECT id FROM tid WHERE title = 'Where Have You Been')) s
JOIN track t ON t.id = s.track_id WHERE t.title = 'TESLA';

\echo '=== 3. Priorités : admin corrige Losing It en 9B (global), Bob le remet en 6A pour lui ==='
INSERT INTO track_analysis (track_id, source, user_id, camelot_num, camelot_letter, created_by) VALUES
  ((SELECT id FROM tid WHERE title = 'Losing It'), 'manual', NULL, 9, 'B', '00000000-0000-0000-0000-00000000000a'),
  ((SELECT id FROM tid WHERE title = 'Losing It'), 'manual', '00000000-0000-0000-0000-00000000000b', 6, 'A', '00000000-0000-0000-0000-00000000000b');

SELECT v.vue, f.bpm, f.bpm_source, f.camelot_num || f.camelot_letter AS camelot, f.key_source, f.key_confidence
FROM (VALUES ('global', NULL::uuid),
             ('Katia',  '00000000-0000-0000-0000-00000000000a'),
             ('Bob',    '00000000-0000-0000-0000-00000000000b')) v(vue, uid)
CROSS JOIN LATERAL effective_features(v.uid) f
WHERE f.track_id = (SELECT id FROM tid WHERE title = 'Losing It');

\echo '=== 4. Contraintes (chaque ligne doit afficher REFUSÉ) ==='
DO $$
DECLARE tesla uuid := (SELECT id FROM track WHERE title = 'TESLA');
BEGIN
  BEGIN
    INSERT INTO track_analysis (track_id, source, bpm) VALUES (tesla, 'rekordbox', 130);
    RAISE NOTICE 'ACCEPTÉ (bug) : rekordbox global';
  EXCEPTION WHEN check_violation THEN RAISE NOTICE 'REFUSÉ : rekordbox sans utilisateur';
  END;
  BEGIN
    INSERT INTO track_analysis (track_id, source, bpm) VALUES (tesla, 'essentia', 131);
    RAISE NOTICE 'ACCEPTÉ (bug) : 2e ligne Essentia';
  EXCEPTION WHEN unique_violation THEN RAISE NOTICE 'REFUSÉ : deux valeurs Essentia pour un morceau';
  END;
  BEGIN
    INSERT INTO track_analysis (track_id, source, camelot_num) VALUES (tesla, 'manual', 8);
    RAISE NOTICE 'ACCEPTÉ (bug) : numéro sans lettre';
  EXCEPTION WHEN check_violation THEN RAISE NOTICE 'REFUSÉ : numéro Camelot sans lettre';
  END;
  BEGIN
    INSERT INTO track_analysis (track_id, source, camelot_num, camelot_letter) VALUES (tesla, 'manual', 13, 'A');
    RAISE NOTICE 'ACCEPTÉ (bug) : 13A';
  EXCEPTION WHEN check_violation THEN RAISE NOTICE 'REFUSÉ : 13A n''existe pas';
  END;
END $$;

\echo '=== 5. Playlist : création puis inversion de deux morceaux dans une transaction ==='
INSERT INTO playlist (id, owner_id, name)
VALUES ('00000000-0000-0000-0000-0000000000f1', '00000000-0000-0000-0000-00000000000a', 'Warm-up');
INSERT INTO playlist_item (playlist_id, track_id, position)
SELECT '00000000-0000-0000-0000-0000000000f1', id, n
FROM (VALUES ('Where Have You Been', 0), ('Don''t Wake Me Up', 1), ('Von dutch', 2)) v(title, n)
JOIN tid USING (title);

BEGIN;
UPDATE playlist_item SET position = CASE position WHEN 0 THEN 1 WHEN 1 THEN 0 END
WHERE playlist_id = '00000000-0000-0000-0000-0000000000f1' AND position IN (0, 1);
COMMIT;

SELECT pi.position, t.title FROM playlist_item pi JOIN track t ON t.id = pi.track_id
WHERE pi.playlist_id = '00000000-0000-0000-0000-0000000000f1' ORDER BY pi.position;
