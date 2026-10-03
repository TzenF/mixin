import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { ImportOutcome, SpotifyPlaylist } from '../../core/api/spotify.service';
import { SpotifyPlaylistsPage } from './spotify-playlists.page';

const PLAYLISTS: SpotifyPlaylist[] = [
  { id: 'vib', name: 'vib', track_count: 32, imported: false },
  { id: 'old', name: 'Ancienne', track_count: 1, imported: true },
];

const OUTCOME: ImportOutcome = {
  import_job_id: 'job',
  playlist_id: 'pl',
  name: 'vib',
  created: true,
  total: 32,
  new: 30,
  known: 2,
  skipped: 0,
  queued: 30,
};

describe('SpotifyPlaylistsPage', () => {
  let http: HttpTestingController;

  /** Configure le module de test ; `query` simule les paramètres de l'URL. */
  function setup(query: Record<string, string> = {}): void {
    TestBed.configureTestingModule({
      imports: [SpotifyPlaylistsPage],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { queryParamMap: convertToParamMap(query) } },
        },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  }

  /** Affiche la page et répond à la demande des playlists. */
  async function render(respond: (req: ReturnType<HttpTestingController['expectOne']>) => void) {
    const fixture = TestBed.createComponent(SpotifyPlaylistsPage);
    fixture.detectChanges();
    respond(http.expectOne('/api/spotify/playlists'));
    await fixture.whenStable();
    return fixture;
  }

  /** Raccourci : élément portant ce data-testid. */
  function byTestId(root: HTMLElement, id: string): HTMLElement | null {
    return root.querySelector(`[data-testid="${id}"]`);
  }

  afterEach(() => http.verify());

  it("propose de connecter Spotify quand l'API répond 401", async () => {
    setup();
    const fixture = await render((req) =>
      req.flush({ detail: 'Non connecté' }, { status: 401, statusText: '' }),
    );

    const link = byTestId(fixture.nativeElement, 'connect-spotify');
    expect(link?.getAttribute('href')).toBe('/api/auth/spotify/login');
    expect(byTestId(fixture.nativeElement, 'playlists')).toBeNull();
  });

  it('liste les playlists avec leur nombre de titres', async () => {
    setup();
    const fixture = await render((req) => req.flush(PLAYLISTS));

    const vib = byTestId(fixture.nativeElement, 'playlist-vib');
    expect(vib?.textContent).toContain('32 titres');
    expect(byTestId(vib!, 'import')?.textContent).toContain('Importer');
    const old = byTestId(fixture.nativeElement, 'playlist-old');
    expect(old?.textContent).toContain('déjà importée');
    expect(byTestId(old!, 'import')?.textContent).toContain('Réimporter');
  });

  it('importe une playlist et affiche le bilan', async () => {
    setup();
    const fixture = await render((req) => req.flush(PLAYLISTS));
    const row = byTestId(fixture.nativeElement, 'playlist-vib')!;

    byTestId(row, 'import')!.click();
    fixture.detectChanges();
    expect(byTestId(row, 'import')?.hasAttribute('disabled')).toBe(true);

    const req = http.expectOne('/api/spotify/playlists/vib/import');
    expect(req.request.method).toBe('POST');
    req.flush(OUTCOME);
    await fixture.whenStable();

    const result = byTestId(row, 'import-result')?.textContent ?? '';
    expect(result).toContain('30 nouveaux');
    expect(result).toContain('2 déjà connus');
    expect(result).toContain("30 mis en file d'analyse");
    expect(byTestId(row, 'import')?.textContent).toContain('Réimporter');
  });

  it("affiche l'erreur de l'API sur la ligne de la playlist", async () => {
    setup();
    const fixture = await render((req) => req.flush(PLAYLISTS));
    const row = byTestId(fixture.nativeElement, 'playlist-vib')!;

    byTestId(row, 'import')!.click();
    http
      .expectOne('/api/spotify/playlists/vib/import')
      .flush({ detail: 'Spotify a répondu HTTP 500' }, { status: 502, statusText: '' });
    await fixture.whenStable();

    expect(byTestId(row, 'import-error')?.textContent).toContain('Spotify a répondu HTTP 500');
  });

  it("affiche l'échec de connexion lu dans l'URL", async () => {
    setup({ spotify_error: 'access_denied' });
    const fixture = await render((req) =>
      req.flush({ detail: 'Non connecté' }, { status: 401, statusText: '' }),
    );

    expect(byTestId(fixture.nativeElement, 'login-error')?.textContent).toContain('refusé');
  });

  it('se déconnecte', async () => {
    setup();
    const fixture = await render((req) => req.flush(PLAYLISTS));

    byTestId(fixture.nativeElement, 'logout')!.click();
    const req = http.expectOne('/api/auth/logout');
    expect(req.request.method).toBe('POST');
    req.flush(null, { status: 204, statusText: '' });
    await fixture.whenStable();

    expect(byTestId(fixture.nativeElement, 'connect-spotify')).not.toBeNull();
  });
});
