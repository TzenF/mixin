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

  /** Configure le module de test ; `query` simule les paramètres de l'URL. */
  function setup(query: Record<string, string> = {}): void {
    navigate = vi.fn().mockResolvedValue(true);
    TestBed.configureTestingModule({
      imports: [CatalogPage],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
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
