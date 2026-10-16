import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { PlaylistDetail, PlaylistSummary } from './api/playlist.service';
import { CURRENT_PLAYLIST_KEY, CurrentPlaylistService } from './current-playlist.service';

const MINE: PlaylistSummary = {
  id: 'mine',
  name: 'Set',
  source_provider: null,
  track_count: 1,
  updated_at: '2026-10-16T14:00:00Z',
};
const IMPORTED: PlaylistSummary = { ...MINE, id: 'mixy', name: 'Mixy', source_provider: 'spotify' };

/** Détail minimal d'une playlist contenant ces morceaux. */
function detail(id: string, trackIds: string[]): PlaylistDetail {
  return {
    ...MINE,
    id,
    spotify_export: null,
    items: trackIds.map((trackId, position) => ({
      item_id: position,
      position,
      transition_to_next: null,
      track: {
        id: trackId,
        title: trackId,
        artists: [],
        bpm: null,
        camelot: null,
        bpm_source: null,
        key_source: null,
        key_confidence: null,
        analysis_status: 'pending',
      },
    })),
  };
}

describe('CurrentPlaylistService', () => {
  let http: HttpTestingController;

  /** Crée le service, avec éventuellement une playlist déjà retenue dans le navigateur. */
  function create(storedId: string | null = null): CurrentPlaylistService {
    localStorage.clear();
    if (storedId !== null) {
      localStorage.setItem(CURRENT_PLAYLIST_KEY, storedId);
    }
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
    return TestBed.inject(CurrentPlaylistService);
  }

  afterEach(() => {
    http.verify();
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it('retrouve la playlist retenue et ses morceaux ; seules mes playlists créées ici sont proposées', () => {
    const service = create('mine');
    service.refresh();
    http.expectOne('/api/playlists').flush([MINE, IMPORTED]);
    http.expectOne('/api/playlists/mine').flush(detail('mine', ['t1']));

    expect(service.editable()?.map((p) => p.id)).toEqual(['mine']);
    expect(service.current()?.name).toBe('Set');
    expect(service.trackIds().has('t1')).toBe(true);
  });

  it("oublie une playlist retenue qui n'existe plus", () => {
    const service = create('deleted');
    service.refresh();
    http.expectOne('/api/playlists').flush([MINE]);

    expect(service.current()).toBeNull();
    expect(localStorage.getItem(CURRENT_PLAYLIST_KEY)).toBeNull();
  });

  it('ajoute un morceau à la playlist en cours', () => {
    const service = create();
    service.refresh();
    http.expectOne('/api/playlists').flush([MINE]);
    service.select('mine');
    http.expectOne('/api/playlists/mine').flush(detail('mine', []));
    expect(localStorage.getItem(CURRENT_PLAYLIST_KEY)).toBe('mine');

    service.add('t2').subscribe();
    const req = http.expectOne('/api/playlists/mine/items');
    expect(req.request.body).toEqual({ track_id: 't2' });
    req.flush({ item_id: 9, position: 1 });

    expect(service.trackIds().has('t2')).toBe(true);
    expect(service.current()?.track_count).toBe(2);
  });

  it('crée une playlist et la choisit', () => {
    const service = create();
    service.refresh();
    http.expectOne('/api/playlists').flush([]);

    service.create('Nouveau').subscribe();
    http.expectOne('/api/playlists').flush({ ...MINE, id: 'new', name: 'Nouveau', track_count: 0 });
    http.expectOne('/api/playlists/new').flush(detail('new', []));

    expect(service.current()?.name).toBe('Nouveau');
  });

  it('fonctionne quand le stockage du navigateur est bloqué', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('bloqué');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('bloqué');
    });
    const service = create();
    service.refresh();
    http.expectOne('/api/playlists').flush([MINE]);

    service.select('mine');
    http.expectOne('/api/playlists/mine').flush(detail('mine', []));
    expect(service.current()?.id).toBe('mine');
  });
});
