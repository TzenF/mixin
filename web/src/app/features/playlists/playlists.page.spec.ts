import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { PlaylistSummary } from '../../core/api/playlist.service';
import { PlaylistsPage } from './playlists.page';

const SET: PlaylistSummary = {
  id: 'set',
  name: 'Set du samedi',
  source_provider: null,
  track_count: 12,
  updated_at: '2026-10-16T14:00:00Z',
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
        { provide: Router, useValue: { navigate } },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  /** Affiche la page et répond à la requête de la liste. */
  async function render(
    respond: (req: ReturnType<HttpTestingController['expectOne']>) => void,
  ): Promise<ComponentFixture<PlaylistsPage>> {
    const fixture = TestBed.createComponent(PlaylistsPage);
    fixture.detectChanges();
    respond(http.expectOne('/api/playlists'));
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
});
