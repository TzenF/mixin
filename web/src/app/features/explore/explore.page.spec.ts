import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap } from '@angular/router';
import { CatalogTrack } from '../../core/api/catalog.service';
import { ExploreSource } from '../../core/api/explore.service';
import { AudioPlayerService } from '../../core/audio-player.service';
import { FakeAudioPlayerService } from '../../core/audio-player.service.fake';
import { CurrentPlaylistService } from '../../core/current-playlist.service';
import { FakeCurrentPlaylistService } from '../../core/current-playlist.service.fake';
import { ExplorePage, PROGRESS_POLL_MS } from './explore.page';

const TOP: ExploreSource = {
  id: 'top',
  title: 'Top France',
  curator: 'Deezer Charts',
  track_count: 100,
  analysed_count: 97,
  pending_count: 0,
  last_synced_at: '2026-10-17T05:00:00Z',
  last_error: null,
  removable: false,
};
const TECHNO: ExploreSource = {
  ...TOP,
  id: 'techno',
  title: 'Hard Techno',
  track_count: 70,
  analysed_count: 52,
  pending_count: 18,
};

const TRACK: CatalogTrack = {
  id: 't1',
  title: 'Dai Dai',
  artists: ['Shakira'],
  bpm: 124,
  camelot: '6A',
  bpm_source: 'essentia',
  key_source: 'essentia',
  key_confidence: 0.8,
  analysis_status: 'done',
  favorite: false,
  mine: false,
  rank: 1,
};

describe('ExplorePage', () => {
  let http: HttpTestingController;
  let navigate: ReturnType<typeof vi.fn>;

  /** Configure le module ; `query` simule les paramètres de l'URL. */
  function setup(query: Record<string, string> = {}): void {
    navigate = vi.fn().mockResolvedValue(true);
    TestBed.configureTestingModule({
      imports: [ExplorePage],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: Router, useValue: { navigate } },
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { queryParamMap: convertToParamMap(query) } },
        },
        { provide: CurrentPlaylistService, useValue: new FakeCurrentPlaylistService() },
        { provide: AudioPlayerService, useValue: new FakeAudioPlayerService() },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  }

  afterEach(() => {
    vi.useRealTimers();
    http.verify();
  });

  /** Requête des morceaux d'une source, en attente. */
  function tracksRequest(): TestRequest {
    return http.expectOne((req) => req.url === '/api/tracks');
  }

  /** Affiche la page, répond avec ces sources puis avec les morceaux de la source affichée. */
  async function render(
    sources: ExploreSource[] = [TOP, TECHNO],
    items: CatalogTrack[] = [TRACK],
  ): Promise<ComponentFixture<ExplorePage>> {
    const fixture = TestBed.createComponent(ExplorePage);
    fixture.detectChanges();
    http.expectOne('/api/explore/sources').flush(sources);
    await fixture.whenStable();
    fixture.detectChanges();
    tracksRequest().flush({ total: items.length, items });
    await fixture.whenStable();
    return fixture;
  }

  /** Raccourci : éléments portant ce data-testid. */
  function all(fixture: ComponentFixture<ExplorePage>, id: string): HTMLElement[] {
    return Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll(`[data-testid="${id}"]`),
    );
  }

  it('affiche la première source : tous ses morceaux, par rang, avec « Nouveau »', async () => {
    setup();
    const fixture = TestBed.createComponent(ExplorePage);
    fixture.detectChanges();
    http.expectOne('/api/explore/sources').flush([TOP, TECHNO]);
    await fixture.whenStable();
    fixture.detectChanges();
    const req = tracksRequest();
    expect(req.request.params.get('source')).toBe('top');
    expect(req.request.params.get('scope')).toBe('all');
    expect(req.request.params.get('sort')).toBe('rank');
    req.flush({ total: 1, items: [TRACK] });
    await fixture.whenStable();

    expect(all(fixture, 'source').map((s) => s.getAttribute('aria-pressed'))).toEqual([
      'true',
      'false',
    ]);
    expect(all(fixture, 'rank')[0].textContent?.trim()).toBe('1');
    expect(all(fixture, 'new-badge').length).toBe(1);
    expect(all(fixture, 'source')[1].textContent).toContain("18 en cours d'analyse");
  });

  it("reprend la source de l'URL", async () => {
    setup({ source: 'techno' });
    const fixture = TestBed.createComponent(ExplorePage);
    fixture.detectChanges();
    http.expectOne('/api/explore/sources').flush([TOP, TECHNO]);
    await fixture.whenStable();
    fixture.detectChanges();
    expect(tracksRequest().request.params.get('source')).toBe('techno');
    http.match(() => true).forEach((r) => r.flush([]));
  });

  it('change de source : URL mise à jour, morceaux rechargés', async () => {
    setup();
    const fixture = await render();
    all(fixture, 'source')[1].click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(navigate).toHaveBeenCalledWith(
      [],
      expect.objectContaining({ queryParams: { source: 'techno' } }),
    );
    expect(tracksRequest().request.params.get('source')).toBe('techno');
  });

  it('filtre les morceaux qui ne sont pas encore à moi', async () => {
    setup();
    const fixture = await render();
    const box = all(fixture, 'new-only')[0] as HTMLInputElement;
    box.checked = true;
    box.dispatchEvent(new Event('change'));

    expect(tracksRequest().request.params.get('scope')).toBe('new');
  });

  it('actualise une source', async () => {
    setup();
    const fixture = await render();
    all(fixture, 'refresh')[0].click();
    http.expectOne('/api/explore/sources/top/refresh').flush({ queued: true });
    fixture.detectChanges();

    expect(all(fixture, 'notice')[0].textContent).toContain('Mise à jour demandée');
  });

  it('relit les compteurs tant que des analyses sont en cours', async () => {
    // Seuls les intervalles sont simulés : whenStable() a besoin des vrais minuteurs.
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
    setup();
    await render();

    vi.advanceTimersByTime(PROGRESS_POLL_MS);
    // 3 morceaux sans extrait ne seront jamais « analysés » : seul pending_count compte
    http
      .expectOne('/api/explore/sources')
      .flush([TOP, { ...TECHNO, analysed_count: 67, pending_count: 0 }]);
    vi.advanceTimersByTime(PROGRESS_POLL_MS);
    http.expectNone('/api/explore/sources'); // tout est analysé : on arrête de relire
  });

  it('montre une source en préparation et une erreur de mise à jour', async () => {
    setup();
    const fresh = {
      ...TOP,
      last_synced_at: null,
      track_count: 0,
      analysed_count: 0,
      pending_count: 0,
      last_error: 'Deezer indisponible',
    };
    const fixture = await render([fresh], []);

    expect(all(fixture, 'source')[0].textContent).toContain('en préparation');
    expect(all(fixture, 'source-error')[0].textContent).toContain('Deezer indisponible');
  });

  it('propose de se connecter sur une réponse 401', async () => {
    setup();
    const fixture = TestBed.createComponent(ExplorePage);
    fixture.detectChanges();
    http
      .expectOne('/api/explore/sources')
      .flush({ detail: 'Non connecté' }, { status: 401, statusText: '' });
    await fixture.whenStable();

    expect(all(fixture, 'connect-spotify').length).toBe(1);
  });
});
