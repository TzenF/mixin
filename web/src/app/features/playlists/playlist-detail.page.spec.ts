import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap } from '@angular/router';
import { CatalogTrack } from '../../core/api/catalog.service';
import { PlaylistDetail, Transition } from '../../core/api/playlist.service';
import { PlaylistDetailPage, describeTransition } from './playlist-detail.page';

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
const TOO_FAST: Transition = {
  ...GOOD,
  key_move: 'same',
  key_distance: 0,
  bpm_change: 8,
  tempo_ok: false,
  compatible: false,
};

/** Playlist de trois morceaux : un bon enchaînement, puis un ⚠. */
const PLAYLIST: PlaylistDetail = {
  id: 'set',
  name: 'Set du samedi',
  source_provider: null,
  track_count: 3,
  updated_at: '2026-10-16T14:00:00Z',
  items: [
    { item_id: 1, position: 0, track: TRACK, transition_to_next: GOOD },
    {
      item_id: 2,
      position: 1,
      track: { ...TRACK, id: 't2', title: 'Rock That Body' },
      transition_to_next: TOO_FAST,
    },
    {
      item_id: 3,
      position: 2,
      track: { ...TRACK, id: 't3', title: 'Trop rapide', bpm: 135 },
      transition_to_next: null,
    },
  ],
};

describe('describeTransition', () => {
  it('décrit un bon enchaînement avec l’écart signé', () => {
    expect(describeTransition(GOOD)).toEqual({ kind: 'ok', text: '→ +0,8 % · Tonalité voisine' });
    expect(describeTransition({ ...GOOD, bpm_change: -3 }).text).toBe(
      '→ −3,0 % · Tonalité voisine',
    );
    expect(describeTransition({ ...GOOD, half_double: true }).text).toBe(
      '→ ½ / ×2 tempo · Tonalité voisine',
    );
  });

  it('explique pourquoi un enchaînement est à vérifier', () => {
    expect(describeTransition(TOO_FAST)).toEqual({ kind: 'warn', text: '⚠ tempo +8,0 %' });
    const farKey = { ...GOOD, key_move: null, key_distance: 5, compatible: false };
    expect(describeTransition(farKey).text).toBe('⚠ tonalité éloignée (5 crans)');
    expect(describeTransition({ ...farKey, tempo_ok: false, bpm_change: -9.1 }).text).toBe(
      '⚠ tonalité éloignée (5 crans) et tempo −9,1 %',
    );
    // 6B -> 8A : deux crans ET changement de mode (la diagonale, elle, n'est qu'à un cran)
    const farAndOtherMode = { ...farKey, key_distance: 2, same_mode: false };
    expect(describeTransition(farAndOtherMode).text).toBe(
      '⚠ tonalité incompatible (2 crans et mineur ↔ majeur)',
    );
  });

  it('accepte la diagonale', () => {
    const diagonal = { ...GOOD, key_move: 'diagonal' as const, same_mode: false };
    expect(describeTransition(diagonal).text).toBe('→ +0,8 % · Diagonale (±1 et mineur ↔ majeur)');
  });

  it('signale un enchaînement inconnu', () => {
    expect(describeTransition(null).kind).toBe('unknown');
  });
});

describe('PlaylistDetailPage', () => {
  let http: HttpTestingController;
  let navigate: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    navigate = vi.fn().mockResolvedValue(true);
    TestBed.configureTestingModule({
      imports: [PlaylistDetailPage],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: Router, useValue: { navigate } },
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: convertToParamMap({ playlistId: 'set' }) } },
        },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  /** Affiche la page et répond à la requête du détail. */
  async function render(
    respond: (req: ReturnType<HttpTestingController['expectOne']>) => void,
  ): Promise<ComponentFixture<PlaylistDetailPage>> {
    const fixture = TestBed.createComponent(PlaylistDetailPage);
    fixture.detectChanges();
    respond(http.expectOne('/api/playlists/set'));
    await fixture.whenStable();
    return fixture;
  }

  /** Raccourci : éléments portant ce data-testid. */
  function all(fixture: ComponentFixture<PlaylistDetailPage>, id: string): HTMLElement[] {
    return Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll(`[data-testid="${id}"]`),
    );
  }

  it('affiche les morceaux et un enchaînement entre chaque paire', async () => {
    const fixture = await render((req) => req.flush(PLAYLIST));

    expect(all(fixture, 'item').map((i) => i.querySelector('.title')?.textContent)).toEqual([
      'Losing It',
      'Rock That Body',
      'Trop rapide',
    ]);
    const transitions = all(fixture, 'transition');
    expect(transitions.map((t) => t.textContent?.trim())).toEqual([
      '→ +0,8 % · Tonalité voisine',
      '⚠ tempo +8,0 %',
    ]);
    expect(transitions[1].classList).toContain('warn');
    expect(all(fixture, 'summary')[0].textContent).toContain('1 enchaînement ⚠');
    expect(all(fixture, 'imported').length).toBe(0);
  });

  it('signale une playlist importée et ouvre les suggestions d’un morceau', async () => {
    const fixture = await render((req) => req.flush({ ...PLAYLIST, source_provider: 'spotify' }));

    expect(all(fixture, 'imported')[0].textContent).toContain('lecture seule');
    all(fixture, 'open-suggestions')[1].click();
    expect(navigate).toHaveBeenCalledWith(['/suggestions', 't2'], {
      queryParams: { scope: 'all' },
    });
  });

  it('gère une playlist inconnue', async () => {
    const fixture = await render((req) =>
      req.flush({ detail: 'Playlist inconnue' }, { status: 404, statusText: '' }),
    );
    expect(all(fixture, 'not-found').length).toBe(1);
  });
});
