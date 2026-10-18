import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap } from '@angular/router';
import { CatalogPage as Page, CatalogTrack } from '../../core/api/catalog.service';
import { CatalogPage, SEARCH_DELAY_MS } from './catalog.page';
import { CurrentPlaylistService } from '../../core/current-playlist.service';
import { FakeCurrentPlaylistService } from '../../core/current-playlist.service.fake';
import { AudioPlayerService } from '../../core/audio-player.service';
import { FakeAudioPlayerService } from '../../core/audio-player.service.fake';

const ALPHA: CatalogTrack = {
  id: 'a',
  title: 'Losing It',
  artists: ['FISHER'],
  bpm: 124,
  camelot: '6A',
  bpm_source: 'essentia',
  key_source: 'essentia',
  key_confidence: 0.6,
  analysis_status: 'done',
  favorite: false,
  mine: true,
};
const PENDING: CatalogTrack = {
  ...ALPHA,
  id: 'b',
  title: 'Pas encore analysé',
  bpm: null,
  camelot: null,
  analysis_status: 'pending',
};

describe('CatalogPage', () => {
  let http: HttpTestingController;
  let navigate: ReturnType<typeof vi.fn>;
  let currentPlaylist: FakeCurrentPlaylistService;

  /** Configure le module de test ; `query` simule les paramètres de l'URL. */
  function setup(query: Record<string, string> = {}): void {
    navigate = vi.fn().mockResolvedValue(true);
    currentPlaylist = new FakeCurrentPlaylistService();
    TestBed.configureTestingModule({
      imports: [CatalogPage],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: CurrentPlaylistService, useValue: currentPlaylist },
        { provide: AudioPlayerService, useValue: new FakeAudioPlayerService() },
        { provide: Router, useValue: { navigate } },
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { queryParamMap: convertToParamMap(query) } },
        },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  }

  /** La requête en attente vers le catalogue (il ne doit y en avoir qu'une). */
  function pending(): TestRequest {
    return http.expectOne((req) => req.url === '/api/tracks');
  }

  /** Paramètres envoyés à l'API, sous forme d'objet. */
  function paramsOf(req: TestRequest): Record<string, string> {
    const params = req.request.params;
    return Object.fromEntries(params.keys().map((k) => [k, params.get(k) ?? '']));
  }

  /** Affiche la page et répond à la première requête. */
  async function render(page: Page = { total: 2, items: [ALPHA, PENDING] }) {
    const fixture = TestBed.createComponent(CatalogPage);
    fixture.detectChanges();
    pending().flush(page);
    await fixture.whenStable();
    return fixture;
  }

  /** Répond à la requête suivante puis attend l'affichage. */
  async function respond(fixture: ComponentFixture<CatalogPage>, page: Page): Promise<void> {
    pending().flush(page);
    await fixture.whenStable();
  }

  /** Raccourci : élément portant ce data-testid. */
  function byTestId<T extends HTMLElement = HTMLElement>(
    fixture: ComponentFixture<CatalogPage>,
    id: string,
  ) {
    return (fixture.nativeElement as HTMLElement).querySelector<T>(`[data-testid="${id}"]`);
  }

  /** Change la valeur d'un champ et déclenche l'événement donné. */
  function type(
    field: HTMLInputElement | HTMLSelectElement,
    value: string,
    event = 'change',
  ): void {
    field.value = value;
    field.dispatchEvent(new Event(event));
  }

  afterEach(() => {
    vi.useRealTimers();
    http.verify();
  });

  it('demande mes morceaux par défaut et les affiche', async () => {
    setup();
    const fixture = TestBed.createComponent(CatalogPage);
    fixture.detectChanges();
    const req = pending();
    expect(paramsOf(req)).toEqual({ scope: 'mine', sort: 'title', limit: '50', offset: '0' });
    req.flush({ total: 2, items: [ALPHA, PENDING] });
    await fixture.whenStable();

    const rows = (fixture.nativeElement as HTMLElement).querySelectorAll(
      '[data-testid="track-row"]',
    );
    expect(rows.length).toBe(2);
    expect(rows[0].textContent).toContain('Losing It');
    expect(rows[0].textContent).toContain('FISHER');
    expect(rows[0].querySelector('[data-testid="bpm"]')?.textContent?.trim()).toBe('124.0');
    expect(rows[1].querySelector('[data-testid="bpm"]')?.textContent?.trim()).toBe('—');
    expect(rows[1].querySelector('[data-testid="status-badge"]')?.textContent).toContain(
      'En attente',
    );
    expect(byTestId(fixture, 'range')?.textContent).toContain('1–2 sur 2');
  });

  it("l'interrupteur affiche tous les morceaux et l'inscrit dans l'URL", async () => {
    setup();
    const fixture = await render();

    const toggle = byTestId<HTMLInputElement>(fixture, 'show-all')!;
    toggle.checked = true;
    toggle.dispatchEvent(new Event('change'));

    const req = pending();
    expect(paramsOf(req)['scope']).toBe('all');
    req.flush({ total: 0, items: [] });
    expect(navigate).toHaveBeenLastCalledWith(
      [],
      expect.objectContaining({
        queryParams: expect.objectContaining({ scope: 'all' }),
        replaceUrl: true,
      }),
    );
  });

  it("reprend les filtres présents dans l'URL", async () => {
    setup({ scope: 'all', key: '8A', bpm_min: '120', status: 'failed', sort: 'bpm', page: '3' });
    const fixture = TestBed.createComponent(CatalogPage);
    fixture.detectChanges();

    const req = pending();
    expect(paramsOf(req)).toEqual({
      scope: 'all',
      sort: 'bpm',
      limit: '50',
      offset: '100',
      bpm_min: '120',
      key: '8A',
      status: 'failed',
    });
    req.flush({ total: 0, items: [] });
    await fixture.whenStable();
    expect(byTestId<HTMLInputElement>(fixture, 'show-all')?.checked).toBe(true);
  });

  it('filtre par BPM et tonalité en revenant à la première page', async () => {
    setup({ page: '2' });
    const fixture = await render({ total: 120, items: [ALPHA] });

    type(byTestId<HTMLInputElement>(fixture, 'bpm-min')!, '124');
    expect(paramsOf(pending())).toMatchObject({ bpm_min: '124', offset: '0' });

    type(byTestId<HTMLInputElement>(fixture, 'key')!, 'Am');
    expect(paramsOf(pending())).toMatchObject({ bpm_min: '124', key: 'Am' });
  });

  it('attend la fin de la frappe avant de chercher', async () => {
    setup();
    const fixture = await render();
    vi.useFakeTimers();

    const search = byTestId<HTMLInputElement>(fixture, 'search')!;
    type(search, 'fis', 'input');
    type(search, 'fisher', 'input');
    http.expectNone((req) => req.url === '/api/tracks');

    vi.advanceTimersByTime(SEARCH_DELAY_MS);
    expect(paramsOf(pending())['q']).toBe('fisher');
  });

  it('pagine par 50', async () => {
    setup();
    const fixture = await render({ total: 120, items: [ALPHA] });
    expect(byTestId<HTMLButtonElement>(fixture, 'previous')?.disabled).toBe(true);

    byTestId(fixture, 'next')!.click();
    expect(paramsOf(pending())['offset']).toBe('50');
  });

  it('ouvre les suggestions d’un morceau en gardant « tous les morceaux »', async () => {
    setup({ scope: 'all' });
    const fixture = await render();

    byTestId(fixture, 'open-suggestions')!.click();
    expect(navigate).toHaveBeenLastCalledWith(['/suggestions', 'a'], {
      queryParams: { scope: 'all' },
    });
  });

  it('propose la barre de playlist en cours et « + Ajouter » sur chaque ligne', async () => {
    setup();
    const fixture = await render();
    const root = fixture.nativeElement as HTMLElement;

    expect(root.querySelector('app-current-playlist-bar')).not.toBeNull();
    expect(
      root.querySelectorAll('[data-testid="track-row"] [data-testid="add-to-playlist"]').length,
    ).toBe(2);
  });

  it('filtre sur mes favoris et l’inscrit dans l’URL', async () => {
    setup();
    const fixture = await render();
    const box = byTestId<HTMLInputElement>(fixture, 'favorites-only')!;
    box.checked = true;
    box.dispatchEvent(new Event('change'));

    expect(paramsOf(pending())).toMatchObject({ favorites: 'true', offset: '0' });
    expect(navigate).toHaveBeenLastCalledWith(
      [],
      expect.objectContaining({ queryParams: expect.objectContaining({ favorites: 1 }) }),
    );
  });

  it('sans playlist en cours, la case « S’enchaîne avec » est désactivée et rien n’est compté', async () => {
    setup();
    const fixture = await render();

    expect(byTestId<HTMLInputElement>(fixture, 'fits-only')?.disabled).toBe(true);
    expect(byTestId(fixture, 'fit-badge')).toBeNull();
  });

  it('compte les liens avec la playlist en cours, puis filtre dessus', async () => {
    setup();
    currentPlaylist.select('current');
    const fixture = TestBed.createComponent(CatalogPage);
    fixture.detectChanges();
    const first = pending();
    expect(paramsOf(first)).toMatchObject({ fits: 'current' });
    expect(paramsOf(first)['fits_only']).toBeUndefined();
    first.flush({ total: 2, items: [{ ...ALPHA, fit_count: 3 }, PENDING] });
    await fixture.whenStable();

    const badge = byTestId(fixture, 'fit-badge');
    expect(badge?.textContent?.trim()).toBe('↔ 3 morceaux'); // pas une place dans la playlist
    expect(badge?.title).toContain('3 morceaux de ta playlist en cours');

    const box = byTestId<HTMLInputElement>(fixture, 'fits-only')!;
    box.checked = true;
    box.dispatchEvent(new Event('change'));
    expect(paramsOf(pending())).toMatchObject({ fits: 'current', fits_only: 'true', offset: '0' });
    expect(navigate).toHaveBeenLastCalledWith(
      [],
      expect.objectContaining({ queryParams: expect.objectContaining({ fits: 1 }) }),
    );
  });

  it('« Où le placer ? » ouvre les places du morceau sous sa ligne', async () => {
    setup();
    currentPlaylist.select('current');
    const fixture = TestBed.createComponent(CatalogPage);
    fixture.detectChanges();
    pending().flush({ total: 2, items: [{ ...ALPHA, fit_count: 2 }, PENDING] });
    await fixture.whenStable();

    const buttons = (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>(
      '[data-testid="open-placements"]',
    );
    expect(buttons.length).toBe(1); // seulement sur le morceau qui s'enchaîne avec la playlist
    buttons[0].click();
    fixture.detectChanges();

    expect(byTestId(fixture, 'placements-row')).not.toBeNull();
    http.expectOne((r) => r.url === '/api/tracks/a/placements').flush([]);
  });

  it('recompte quand la playlist en cours change', async () => {
    setup();
    const fixture = await render();
    currentPlaylist.select('current');
    fixture.detectChanges();
    await fixture.whenStable();

    expect(paramsOf(pending())).toMatchObject({ fits: 'current' });
  });

  it('affiche ★ sur chaque ligne', async () => {
    setup();
    const fixture = await render({ total: 1, items: [{ ...ALPHA, favorite: true }] });
    expect(byTestId(fixture, 'favorite')?.textContent?.trim()).toBe('★');
  });

  it('met la ligne à jour après une correction, avec « corrigé » sur le BPM', async () => {
    setup();
    const fixture = await render();
    byTestId(fixture, 'correct')!.click();
    fixture.detectChanges();
    byTestId(fixture, 'half')!.click();
    byTestId(fixture, 'correction-save')!.click();
    http.expectOne('/api/tracks/a/correction').flush({ ...ALPHA, bpm: 62, bpm_source: 'manual' });
    await fixture.whenStable();

    const row = (fixture.nativeElement as HTMLElement).querySelector('[data-testid="track-row"]')!;
    expect(row.querySelector('[data-testid="bpm"]')?.textContent).toContain('62.0');
    expect(row.querySelector('[data-testid="bpm-corrected"]')).not.toBeNull();
  });

  it('propose ▶ sur chaque ligne, désactivé pour un morceau sans extrait', async () => {
    setup();
    const fixture = await render({
      total: 2,
      items: [ALPHA, { ...PENDING, analysis_status: 'no_preview' }],
    });
    const buttons = (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>(
      '[data-testid="track-row"] [data-testid="play"]',
    );
    expect(Array.from(buttons).map((b) => b.disabled)).toEqual([false, true]);
  });

  it('signale quand aucun morceau ne correspond', async () => {
    setup();
    const fixture = await render({ total: 0, items: [] });

    expect(byTestId(fixture, 'empty')).not.toBeNull();
    expect(byTestId(fixture, 'tracks')).toBeNull();
  });

  it("affiche l'erreur de l'API (tonalité inconnue)", async () => {
    setup();
    const fixture = await render();

    type(byTestId<HTMLInputElement>(fixture, 'key')!, '13Z');
    pending().flush({ detail: "Tonalité non reconnue : '13Z'" }, { status: 422, statusText: '' });
    await fixture.whenStable();

    expect(byTestId(fixture, 'error')?.textContent).toContain('Tonalité non reconnue');
  });

  it('propose de se connecter sur une réponse 401', async () => {
    setup();
    const fixture = TestBed.createComponent(CatalogPage);
    fixture.detectChanges();
    await respondError(fixture);

    expect(byTestId(fixture, 'connect-spotify')?.getAttribute('href')).toBe(
      '/api/auth/spotify/login',
    );
    expect(byTestId(fixture, 'tracks')).toBeNull();
  });

  /** Répond 401 à la requête en attente. */
  async function respondError(fixture: ComponentFixture<CatalogPage>): Promise<void> {
    pending().flush({ detail: 'Non connecté' }, { status: 401, statusText: '' });
    await fixture.whenStable();
  }

  it('abandonne une réponse devenue inutile', async () => {
    setup();
    const fixture = await render();

    type(byTestId<HTMLInputElement>(fixture, 'bpm-min')!, '120');
    const stale = pending();
    type(byTestId<HTMLInputElement>(fixture, 'bpm-min')!, '125');

    expect(stale.cancelled).toBe(true);
    await respond(fixture, { total: 1, items: [ALPHA] });
    expect(byTestId(fixture, 'range')?.textContent).toContain('1–1 sur 1');
  });
});

describe('CatalogPage — inversion majeur/mineur', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [CatalogPage],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: CurrentPlaylistService, useValue: new FakeCurrentPlaylistService() },
        { provide: AudioPlayerService, useValue: new FakeAudioPlayerService() },
        { provide: Router, useValue: { navigate: vi.fn().mockResolvedValue(true) } },
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { queryParamMap: convertToParamMap({}) } },
        },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  /** Affiche la page avec un morceau analysé (6A) et un sans tonalité. */
  async function render(): Promise<ComponentFixture<CatalogPage>> {
    const fixture = TestBed.createComponent(CatalogPage);
    fixture.detectChanges();
    http.expectOne((req) => req.url === '/api/tracks').flush({ total: 2, items: [ALPHA, PENDING] });
    await fixture.whenStable();
    return fixture;
  }

  /** Ligne du tableau à cette position. */
  function row(fixture: ComponentFixture<CatalogPage>, index: number): HTMLElement {
    return (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLElement>(
      '[data-testid="track-row"]',
    )[index];
  }

  it('met la ligne à jour avec la tonalité corrigée', async () => {
    const fixture = await render();
    const button = row(fixture, 0).querySelector<HTMLButtonElement>('[data-testid="flip-mode"]')!;

    button.click();
    fixture.detectChanges();
    expect(button.disabled).toBe(true);
    const req = http.expectOne('/api/tracks/a/key/flip-mode');
    expect(req.request.method).toBe('POST');
    req.flush({ camelot: '9B', key_source: 'manual' });
    await fixture.whenStable();

    expect(row(fixture, 0).querySelector('[data-testid="camelot"]')?.textContent).toBe('9B');
    expect(row(fixture, 0).querySelector('[data-testid="corrected"]')).not.toBeNull();
    expect(button.disabled).toBe(false);
  });

  it("n'est pas proposée sans tonalité", async () => {
    const fixture = await render();
    const button = row(fixture, 1).querySelector<HTMLButtonElement>('[data-testid="flip-mode"]');
    expect(button?.disabled).toBe(true);
  });

  it("affiche l'erreur de l'API", async () => {
    const fixture = await render();
    row(fixture, 0).querySelector<HTMLButtonElement>('[data-testid="flip-mode"]')!.click();
    http
      .expectOne('/api/tracks/a/key/flip-mode')
      .flush({ detail: "Ce morceau n'a pas encore de tonalité" }, { status: 409, statusText: '' });
    await fixture.whenStable();

    const error = (fixture.nativeElement as HTMLElement).querySelector(
      '[data-testid="correction-error"]',
    );
    expect(error?.textContent).toContain('pas encore de tonalité');
  });
});
