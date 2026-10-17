import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, ParamMap, Router, convertToParamMap } from '@angular/router';
import { BehaviorSubject } from 'rxjs';
import { CatalogTrack, Suggestion } from '../../core/api/catalog.service';
import { SuggestionsPage } from './suggestions.page';
import { CurrentPlaylistService } from '../../core/current-playlist.service';
import { FakeCurrentPlaylistService } from '../../core/current-playlist.service.fake';
import { AudioPlayerService } from '../../core/audio-player.service';
import { FakeAudioPlayerService } from '../../core/audio-player.service.fake';

const SEED: CatalogTrack = {
  id: 'seed',
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
const ROCK: Suggestion = {
  track_id: 'rock',
  title: 'Rock That Body',
  artists: ['Black Eyed Peas'],
  bpm: 125,
  camelot: '7A',
  key_move: 'adjacent',
  half_double: false,
  bpm_diff_pct: 0.8,
  score: 0.777,
  favorite: false,
  my_rating: null,
};
const DOUBLE: Suggestion = {
  ...ROCK,
  track_id: 'double',
  title: 'Double',
  key_move: 'same',
  half_double: true,
};

describe('SuggestionsPage', () => {
  let http: HttpTestingController;
  let navigate: ReturnType<typeof vi.fn>;
  let params: BehaviorSubject<ParamMap>;

  /** Configure le module de test ; `query` simule les paramètres de l'URL. */
  function setup(query: Record<string, string> = {}): void {
    navigate = vi.fn().mockResolvedValue(true);
    params = new BehaviorSubject(convertToParamMap({ trackId: 'seed' }));
    TestBed.configureTestingModule({
      imports: [SuggestionsPage],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: CurrentPlaylistService, useValue: new FakeCurrentPlaylistService() },
        { provide: AudioPlayerService, useValue: new FakeAudioPlayerService() },
        { provide: Router, useValue: { navigate } },
        {
          provide: ActivatedRoute,
          useValue: { paramMap: params, snapshot: { queryParamMap: convertToParamMap(query) } },
        },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  }

  /** Répond aux deux requêtes d'un chargement (morceau de départ, puis suggestions). */
  async function answer(
    fixture: ComponentFixture<SuggestionsPage>,
    seed: CatalogTrack = SEED,
    suggestions: Suggestion[] = [ROCK, DOUBLE],
    id = 'seed',
  ): Promise<void> {
    http.expectOne(`/api/tracks/${id}`).flush(seed);
    http.expectOne((req) => req.url === `/api/tracks/${id}/suggestions`).flush(suggestions);
    await fixture.whenStable();
  }

  /** Affiche la page (sans répondre aux requêtes). */
  function create(): ComponentFixture<SuggestionsPage> {
    const fixture = TestBed.createComponent(SuggestionsPage);
    fixture.detectChanges();
    return fixture;
  }

  /** Raccourci : élément portant ce data-testid. */
  function byTestId<T extends HTMLElement = HTMLElement>(
    fixture: ComponentFixture<SuggestionsPage>,
    id: string,
  ): T | null {
    return (fixture.nativeElement as HTMLElement).querySelector<T>(`[data-testid="${id}"]`);
  }

  /** Paramètres de la requête de suggestions en attente. */
  function suggestionParams(id = 'seed'): Record<string, string | null> {
    const req = http.expectOne((r) => r.url === `/api/tracks/${id}/suggestions`);
    const p = req.request.params;
    const result = { scope: p.get('scope'), bpm_tolerance: p.get('bpm_tolerance') };
    req.flush([]);
    return result;
  }

  afterEach(() => http.verify());

  it('affiche le morceau de départ et les suggestions', async () => {
    setup();
    const fixture = create();
    await answer(fixture);

    expect(byTestId(fixture, 'seed')?.textContent).toContain('Losing It');
    expect(byTestId(fixture, 'seed-camelot')?.textContent).toBe('6A');
    const items = (fixture.nativeElement as HTMLElement).querySelectorAll(
      '[data-testid="suggestion"]',
    );
    expect(items.length).toBe(2);
    expect(items[0].textContent).toContain('Rock That Body');
    expect(items[0].textContent).toContain('Black Eyed Peas');
    expect(items[0].textContent).toContain('Tonalité voisine');
    expect(items[0].querySelector('[data-testid="half-double"]')).toBeNull();
    expect(items[1].querySelector('[data-testid="half-double"]')).not.toBeNull();
  });

  it('demande mes morceaux avec ±6 % par défaut, ou les réglages de l’URL', async () => {
    setup();
    create();
    http.expectOne('/api/tracks/seed').flush(SEED);
    expect(suggestionParams()).toEqual({ scope: 'mine', bpm_tolerance: '0.06' });
  });

  it('ne suggère que mes favoris si demandé (case ou URL)', async () => {
    setup({ favorites: '1' });
    const fixture = create();
    http.expectOne('/api/tracks/seed').flush(SEED);
    const req = http.expectOne((r) => r.url === '/api/tracks/seed/suggestions');
    expect(req.request.params.get('favorites')).toBe('true');
    req.flush([{ ...ROCK, favorite: true }]);
    await fixture.whenStable();

    expect(byTestId<HTMLInputElement>(fixture, 'favorites-only')?.checked).toBe(true);
    const stars = (fixture.nativeElement as HTMLElement).querySelectorAll(
      '[data-testid="favorite"]',
    );
    expect(Array.from(stars).map((s) => s.textContent?.trim())).toEqual(['☆', '★']); // départ, suggestion
  });

  it("reprend les réglages présents dans l'URL", async () => {
    setup({ scope: 'all', tolerance: '0.1' });
    const fixture = create();
    http.expectOne('/api/tracks/seed').flush(SEED);
    expect(suggestionParams()).toEqual({ scope: 'all', bpm_tolerance: '0.1' });
    await fixture.whenStable();
    expect(byTestId<HTMLInputElement>(fixture, 'show-all')?.checked).toBe(true);
  });

  it('enchaîne : la suggestion choisie devient le point de départ', async () => {
    setup();
    const fixture = create();
    await answer(fixture);

    byTestId(fixture, 'suggestion')!.click();
    expect(navigate).toHaveBeenCalledWith(['/suggestions', 'rock'], {
      queryParamsHandling: 'preserve',
    });

    params.next(convertToParamMap({ trackId: 'rock' }));
    await answer(fixture, { ...SEED, id: 'rock', title: 'Rock That Body' }, [], 'rock');
    expect(byTestId(fixture, 'seed')?.textContent).toContain('Rock That Body');
  });

  it("change l'écart de BPM et l'inscrit dans l'URL", async () => {
    setup();
    const fixture = create();
    await answer(fixture);

    const select = byTestId<HTMLSelectElement>(fixture, 'tolerance')!;
    select.value = '0.1';
    select.dispatchEvent(new Event('change'));

    http.expectOne('/api/tracks/seed').flush(SEED);
    expect(suggestionParams()).toEqual({ scope: 'mine', bpm_tolerance: '0.1' });
    expect(navigate).toHaveBeenLastCalledWith(
      [],
      expect.objectContaining({
        queryParams: { scope: null, tolerance: 0.1, favorites: null },
        replaceUrl: true,
      }),
    );
  });

  it('explique pourquoi il n’y a pas de suggestion', async () => {
    setup();
    const notAnalysed = create();
    await answer(notAnalysed, { ...SEED, bpm: null, camelot: null }, []);
    expect(byTestId(notAnalysed, 'not-analysed')).not.toBeNull();
    expect(byTestId<HTMLButtonElement>(notAnalysed, 'flip-mode')?.disabled).toBe(true);
  });

  it('propose « + Ajouter » pour le morceau de départ et chaque suggestion', async () => {
    setup();
    const fixture = create();
    await answer(fixture);
    const root = fixture.nativeElement as HTMLElement;

    expect(root.querySelector('app-current-playlist-bar')).not.toBeNull();
    expect(
      root.querySelectorAll('[data-testid="seed"] [data-testid="add-to-playlist"]').length,
    ).toBe(1);
    expect(root.querySelectorAll('.suggestion-row [data-testid="add-to-playlist"]').length).toBe(2);
  });

  it('recalcule les suggestions après une correction du morceau de départ', async () => {
    setup();
    const fixture = create();
    await answer(fixture);
    const seed = byTestId(fixture, 'seed')!;
    seed.querySelector<HTMLButtonElement>('[data-testid="correct"]')!.click();
    fixture.detectChanges();
    seed.querySelector<HTMLButtonElement>('[data-testid="double"]')!.click();
    seed.querySelector<HTMLButtonElement>('[data-testid="correction-save"]')!.click();
    http
      .expectOne('/api/tracks/seed/correction')
      .flush({ ...SEED, bpm: 248, bpm_source: 'manual' });

    await answer(fixture, { ...SEED, bpm: 248, bpm_source: 'manual' }, []);
    expect(byTestId(fixture, 'seed-bpm')?.textContent).toContain('248.0');
  });

  it('propose d’écouter le départ, chaque suggestion et l’enchaînement', async () => {
    setup();
    const fixture = create();
    await answer(fixture);
    const root = fixture.nativeElement as HTMLElement;

    expect(root.querySelectorAll('[data-testid="seed"] [data-testid="play"]').length).toBe(1);
    expect(root.querySelectorAll('.suggestion-row [data-testid="play"]').length).toBe(2);
    root
      .querySelector<HTMLButtonElement>('.suggestion-row [data-testid="play-transition"]')!
      .click();
    const player = TestBed.inject(AudioPlayerService) as unknown as FakeAudioPlayerService;
    expect(player.calls).toEqual(['transition:seed>rock']);
    expect(root.querySelector('[data-testid="listen-disclaimer"]')?.textContent).toContain(
      'pas la vraie fin',
    );
  });

  it('propose de noter l’enchaînement départ → chaque suggestion', async () => {
    setup();
    const fixture = create();
    await answer(fixture, SEED, [
      { ...ROCK, my_rating: { rating: 5, comment: 'parfait' } },
      DOUBLE,
    ]);
    const ratings = (fixture.nativeElement as HTMLElement).querySelectorAll(
      '.suggestion-row [data-testid="transition-rating"]',
    );

    expect(ratings.length).toBe(2);
    expect(ratings[0].querySelector('[aria-pressed="true"]')?.textContent?.trim()).toBe('5');
  });

  it('signale quand aucun morceau n’est compatible', async () => {
    setup();
    const fixture = create();
    await answer(fixture, SEED, []);
    expect(byTestId(fixture, 'empty')).not.toBeNull();
  });

  it('inverse majeur/mineur du morceau de départ puis recalcule', async () => {
    setup();
    const fixture = create();
    await answer(fixture);

    byTestId(fixture, 'flip-mode')!.click();
    http.expectOne('/api/tracks/seed/key/flip-mode').flush({ camelot: '9B', key_source: 'manual' });
    await answer(fixture, { ...SEED, camelot: '9B', key_source: 'manual' }, []);

    expect(byTestId(fixture, 'seed-camelot')?.textContent).toBe('9B');
    expect(byTestId(fixture, 'seed')?.textContent).toContain('corrigée');
  });

  it('gère un morceau inconnu et une session absente', async () => {
    setup();
    const fixture = create();
    http
      .expectOne('/api/tracks/seed')
      .flush({ detail: 'Morceau inconnu' }, { status: 404, statusText: '' });
    http.expectOne((r) => r.url === '/api/tracks/seed/suggestions');
    await fixture.whenStable();
    expect(byTestId(fixture, 'not-found')).not.toBeNull();

    params.next(convertToParamMap({ trackId: 'other' }));
    http
      .expectOne('/api/tracks/other')
      .flush({ detail: 'Non connecté' }, { status: 401, statusText: '' });
    http.expectOne((r) => r.url === '/api/tracks/other/suggestions');
    await fixture.whenStable();
    expect(byTestId(fixture, 'connect-spotify')).not.toBeNull();
  });
});
