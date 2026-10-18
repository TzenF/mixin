import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { PlaylistSummary } from '../../core/api/playlist.service';
import { PlaylistsPage } from './playlists.page';
import { CurrentPlaylistService } from '../../core/current-playlist.service';
import { FakeCurrentPlaylistService } from '../../core/current-playlist.service.fake';

const SET: PlaylistSummary = {
  id: 'set',
  name: 'Set du samedi',
  source_provider: null,
  track_count: 12,
  updated_at: '2026-10-16T14:00:00Z',
  slot_minutes: null,
  played_percent: 100,
};
const MIXY: PlaylistSummary = {
  ...SET,
  id: 'mixy',
  name: 'Mixy',
  source_provider: 'spotify',
  track_count: 1,
};

describe('PlaylistsPage', () => {
  let http: HttpTestingController;
  let navigate: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    navigate = vi.fn().mockResolvedValue(true);
    TestBed.configureTestingModule({
      imports: [PlaylistsPage],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: CurrentPlaylistService, useValue: new FakeCurrentPlaylistService() },
        { provide: Router, useValue: { navigate } },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  /** Affiche la page et répond à la requête de la liste. */
  async function render(
    respond: (req: ReturnType<HttpTestingController['expectOne']>) => void,
    count = 0,
  ): Promise<ComponentFixture<PlaylistsPage>> {
    const fixture = TestBed.createComponent(PlaylistsPage);
    fixture.detectChanges();
    respond(http.expectOne('/api/playlists'));
    http.expectOne('/api/transitions/ratings/count').flush({ count });
    await fixture.whenStable();
    return fixture;
  }

  /** Raccourci : éléments portant ce data-testid. */
  function all(fixture: ComponentFixture<PlaylistsPage>, id: string): HTMLElement[] {
    return Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll(`[data-testid="${id}"]`),
    );
  }

  it('liste mes playlists, en signalant les importées', async () => {
    const fixture = await render((req) => req.flush([SET, MIXY]));

    const rows = all(fixture, 'playlist');
    expect(rows.map((r) => r.querySelector('.name')?.textContent)).toEqual([
      'Set du samedi',
      'Mixy',
    ]);
    expect(rows[0].textContent).toContain('12 titres');
    expect(rows[1].textContent).toContain('1 titre');
    expect(rows[0].querySelector('[data-testid="imported"]')).toBeNull();
    expect(rows[1].querySelector('[data-testid="imported"]')).not.toBeNull();
  });

  it('ouvre le détail au clic', async () => {
    const fixture = await render((req) => req.flush([SET]));
    all(fixture, 'playlist')[0].click();
    expect(navigate).toHaveBeenCalledWith(['/playlists', 'set']);
  });

  it('explique quoi faire sans playlist, et propose de se connecter sur un 401', async () => {
    const empty = await render((req) => req.flush([]));
    expect(all(empty, 'empty').length).toBe(1);

    const disconnected = await render((req) =>
      req.flush({ detail: 'Non connecté' }, { status: 401, statusText: '' }),
    );
    expect(all(disconnected, 'connect-spotify').length).toBe(1);
  });

  it('crée une playlist, qui devient la playlist en cours', async () => {
    const fixture = await render((req) => req.flush([]));
    const root = fixture.nativeElement as HTMLElement;

    root.querySelector<HTMLInputElement>('[data-testid="new-playlist-name"]')!.value = 'Samedi';
    root.querySelector<HTMLButtonElement>('[data-testid="create-playlist"]')!.click();
    http.expectOne('/api/playlists').flush([]); // la liste est rechargée

    const current = TestBed.inject(CurrentPlaylistService) as unknown as FakeCurrentPlaylistService;
    expect(current.current()?.name).toBe('Samedi');
  });

  it('choisit la playlist en cours (pas une importée)', async () => {
    const fixture = await render((req) => req.flush([{ ...SET, id: 'current' }, MIXY]));
    const rows = all(fixture, 'playlist-row');
    expect(rows[1].querySelector('[data-testid="make-current"]')).toBeNull();

    rows[0].querySelector<HTMLButtonElement>('[data-testid="make-current"]')!.click();
    fixture.detectChanges();

    expect(all(fixture, 'is-current').length).toBe(1);
  });

  it('duplique une playlist', async () => {
    const fixture = await render((req) => req.flush([MIXY]));
    all(fixture, 'duplicate')[0].click();

    expect(http.expectOne('/api/playlists/mixy/copy').request.method).toBe('POST');
  });

  it('supprime après confirmation seulement', async () => {
    const fixture = await render((req) => req.flush([SET]));
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);

    all(fixture, 'delete')[0].click();
    http.expectNone('/api/playlists/set');

    confirm.mockReturnValue(true);
    all(fixture, 'delete')[0].click();
    const req = http.expectOne('/api/playlists/set');
    expect(req.request.method).toBe('DELETE');
    req.flush(null, { status: 204, statusText: '' });
    http.expectOne('/api/playlists').flush([]);
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('Set du samedi'));
    confirm.mockRestore();
  });

  it('affiche combien d’enchaînements j’ai notés', async () => {
    const fixture = await render((req) => req.flush([SET]), 12);
    expect(all(fixture, 'rated-count')[0].textContent).toContain('12 enchaînements notés');
  });
});
