import { CatalogTrack } from '../core/api/catalog.service';
import { PlaylistDetail, Transition } from '../core/api/playlist.service';
import { playlistFileName, playlistText } from './playlist-text';

const TRACK: CatalogTrack = {
  id: 't1',
  title: 'Losing It',
  artists: ['FISHER'],
  bpm: 124,
  camelot: '6A',
  bpm_source: 'essentia',
  key_source: 'essentia',
  key_confidence: 0.6,
  analysis_status: 'done',
  favorite: false,
};
const GOOD: Transition = {
  key_move: 'adjacent',
  key_distance: 1,
  half_double: false,
  bpm_diff: 0.008,
  bpm_change: 0.8,
  tempo_ok: true,
  same_mode: true,
  compatible: true,
};

const SET: PlaylistDetail = {
  id: 'set',
  name: 'Set du samedi',
  source_provider: null,
  track_count: 3,
  updated_at: '2026-10-16T14:00:00Z',
  spotify_export: null,
  items: [
    { item_id: 1, position: 0, track: TRACK, transition_to_next: GOOD },
    {
      item_id: 2,
      position: 1,
      track: {
        ...TRACK,
        title: 'Memories',
        artists: ['David Guetta', 'Kid Cudi'],
        bpm: 135,
        camelot: '7A',
      },
      transition_to_next: null,
    },
    {
      item_id: 3,
      position: 2,
      track: { ...TRACK, title: 'Inédit', artists: [], bpm: null, camelot: null },
      transition_to_next: null,
    },
  ],
};

describe('playlistText', () => {
  it('détaille BPM, tonalité et enchaînements pour préparer un set', () => {
    expect(playlistText(SET, 'detailed', new Date(2026, 9, 16))).toBe(
      [
        'Set du samedi',
        '3 titres · 0 enchaînement ⚠ · exportée le 16/10/2026',
        '',
        '01. FISHER – Losing It · 124.0 BPM · 6A',
        '    → +0,8 % · Tonalité voisine',
        '02. David Guetta, Kid Cudi – Memories · 135.0 BPM · 7A',
        '    ? Enchaînement inconnu (morceau non analysé)',
        '03. Inédit · ? BPM · ?',
        '',
      ].join('\n'),
    );
  });

  it('donne une simple tracklist à partager', () => {
    expect(playlistText(SET, 'tracklist')).toBe(
      [
        'Set du samedi',
        '',
        '01. FISHER – Losing It',
        '02. David Guetta, Kid Cudi – Memories',
        '03. Inédit',
        '',
      ].join('\n'),
    );
  });

  it('numérote sur trois chiffres au-delà de 99 titres', () => {
    const big = {
      ...SET,
      items: Array.from({ length: 120 }, (_, i) => ({ ...SET.items[0], item_id: i })),
    };
    const lines = playlistText(big, 'tracklist').split('\n');
    expect(lines[2]).toMatch(/^001\. /);
    expect(lines[121]).toMatch(/^120\. /);
  });
});

describe('playlistFileName', () => {
  it('retire les caractères interdits dans un nom de fichier', () => {
    expect(playlistFileName('Set 16/10 : "warm-up"?', 'detailed')).toBe(
      'Set 16-10 - -warm-up--.txt',
    );
    expect(playlistFileName('Set', 'tracklist')).toBe('Set (tracklist).txt');
    expect(playlistFileName('  ', 'detailed')).toBe('playlist.txt');
  });
});
