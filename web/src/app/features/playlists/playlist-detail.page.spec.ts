import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { CdkDropList } from '@angular/cdk/drag-drop';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { ActivatedRoute, Router, convertToParamMap } from '@angular/router';
import { CatalogTrack } from '../../core/api/catalog.service';
import { PlaylistDetail, Transition } from '../../core/api/playlist.service';
import { describeTransition } from '../../shared/key-moves';
import { PlaylistDetailPage } from './playlist-detail.page';
import { CurrentPlaylistService } from '../../core/current-playlist.service';
import { FakeCurrentPlaylistService } from '../../core/current-playlist.service.fake';
import { FileDownloadService } from '../../core/file-download.service';

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
  spotify_export: null,
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
  let saveText: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    navigate = vi.fn().mockResolvedValue(true);
    saveText = vi.fn();
    TestBed.configureTestingModule({
      imports: [PlaylistDetailPage],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: CurrentPlaylistService, useValue: new FakeCurrentPlaylistService() },
        { provide: FileDownloadService, useValue: { saveText } },
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

  it('renomme une playlist créée ici', async () => {
    const fixture = await render((req) => req.flush(PLAYLIST));
    all(fixture, 'rename')[0].click();
    fixture.detectChanges();

    const input = all(fixture, 'rename-input')[0] as HTMLInputElement;
    input.value = 'Set du dimanche';
    all(fixture, 'rename-save')[0].click();
    const req = http.expectOne('/api/playlists/set');
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual({ name: 'Set du dimanche' });
    req.flush({ ...PLAYLIST, name: 'Set du dimanche' });
    await fixture.whenStable();

    expect((fixture.nativeElement as HTMLElement).querySelector('h1')?.textContent).toBe(
      'Set du dimanche',
    );
  });

  it('une importée ne se renomme pas mais se duplique pour être modifiée', async () => {
    const fixture = await render((req) => req.flush({ ...PLAYLIST, source_provider: 'spotify' }));
    expect(all(fixture, 'rename').length).toBe(0);
    expect(all(fixture, 'make-current').length).toBe(0);

    const duplicate = all(fixture, 'duplicate')[0];
    expect(duplicate.textContent).toContain('Dupliquer pour modifier');
    duplicate.click();
    http
      .expectOne('/api/playlists/set/copy')
      .flush({ ...PLAYLIST, id: 'copy', source_provider: null });

    expect(navigate).toHaveBeenCalledWith(['/playlists', 'copy']);
  });

  it('supprime après confirmation puis revient à la liste', async () => {
    const fixture = await render((req) => req.flush(PLAYLIST));
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);

    all(fixture, 'delete')[0].click();
    http.expectOne('/api/playlists/set').flush(null, { status: 204, statusText: '' });

    expect(navigate).toHaveBeenCalledWith(['/playlists']);
    confirm.mockRestore();
  });

  /** Simule un glisser-déposer du morceau à la position `from` vers `to`. */
  function dragAndDrop(
    fixture: ComponentFixture<PlaylistDetailPage>,
    from: number,
    to: number,
  ): void {
    fixture.debugElement
      .query(By.directive(CdkDropList))
      .triggerEventHandler('cdkDropListDropped', { previousIndex: from, currentIndex: to });
    fixture.detectChanges();
  }

  /** Titres affichés, dans l'ordre. */
  function titles(fixture: ComponentFixture<PlaylistDetailPage>): (string | null | undefined)[] {
    return all(fixture, 'item').map((i) => i.querySelector('.title')?.textContent);
  }

  it('déplace un morceau : affiché tout de suite, enregistré, puis enchaînements recalculés', async () => {
    const fixture = await render((req) => req.flush(PLAYLIST));

    dragAndDrop(fixture, 2, 0);
    expect(titles(fixture)).toEqual(['Trop rapide', 'Losing It', 'Rock That Body']);

    const req = http.expectOne('/api/playlists/set/order');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual({ item_ids: [3, 1, 2] });
    req.flush(null, { status: 204, statusText: '' });
    // rechargement discret : la page ne repasse pas par « Chargement… »
    expect(all(fixture, 'loading').length).toBe(0);
    http.expectOne('/api/playlists/set').flush(PLAYLIST);
  });

  it('recharge si la playlist a changé entre-temps (422)', async () => {
    const fixture = await render((req) => req.flush(PLAYLIST));

    dragAndDrop(fixture, 0, 1);
    http
      .expectOne('/api/playlists/set/order')
      .flush({ detail: 'La playlist a changé' }, { status: 422, statusText: '' });
    http.expectOne('/api/playlists/set').flush(PLAYLIST);
    await fixture.whenStable();

    expect(all(fixture, 'action-error')[0].textContent).toContain('a changé entre-temps');
    expect(titles(fixture)).toEqual(['Losing It', 'Rock That Body', 'Trop rapide']);
  });

  it('retire un morceau', async () => {
    const fixture = await render((req) => req.flush(PLAYLIST));

    all(fixture, 'remove-item')[1].click();
    const req = http.expectOne('/api/playlists/set/items/2');
    expect(req.request.method).toBe('DELETE');
    req.flush(null, { status: 204, statusText: '' });
    http
      .expectOne('/api/playlists/set')
      .flush({ ...PLAYLIST, items: [PLAYLIST.items[0], PLAYLIST.items[2]] });
    await fixture.whenStable();

    expect(titles(fixture)).toEqual(['Losing It', 'Trop rapide']);
  });

  it('une importée ne se réordonne pas et ne se modifie pas', async () => {
    const fixture = await render((req) => req.flush({ ...PLAYLIST, source_provider: 'spotify' }));

    const dropList = fixture.debugElement
      .query(By.directive(CdkDropList))
      .injector.get(CdkDropList);
    expect(dropList.disabled).toBe(true);
    expect(all(fixture, 'remove-item').length).toBe(0);
    expect((fixture.nativeElement as HTMLElement).querySelector('.handle')).toBeNull();
  });

  it('exporte vers Spotify et affiche le bilan et le lien', async () => {
    const fixture = await render((req) => req.flush(PLAYLIST));
    const button = all(fixture, 'export-spotify')[0] as HTMLButtonElement;
    expect(button.textContent).toContain('Exporter vers Spotify');

    button.click();
    fixture.detectChanges();
    expect(button.disabled).toBe(true);
    const req = http.expectOne('/api/playlists/set/export/spotify');
    expect(req.request.method).toBe('POST');
    req.flush({
      url: 'https://open.spotify.com/playlist/sp1',
      created: true,
      exported: 2,
      skipped: 1,
      exported_at: '2026-10-16T15:00:00Z',
    });
    await fixture.whenStable();

    const result = all(fixture, 'export-result')[0].textContent ?? '';
    expect(result).toContain('Playlist créée sur Spotify');
    expect(result).toContain('2 titres');
    expect(result).toContain('1 ignoré (pas sur Spotify)');
    expect(all(fixture, 'open-spotify')[0].getAttribute('href')).toBe(
      'https://open.spotify.com/playlist/sp1',
    );
    expect(button.textContent).toContain('Mettre à jour sur Spotify');
  });

  it("propose « Mettre à jour » si elle est déjà exportée, et n'exporte pas une importée", async () => {
    const exported = await render((req) =>
      req.flush({
        ...PLAYLIST,
        spotify_export: {
          url: 'https://open.spotify.com/playlist/sp1',
          exported_at: '2026-10-16T15:00:00Z',
        },
      }),
    );
    expect(all(exported, 'export-spotify')[0].textContent).toContain('Mettre à jour sur Spotify');
    expect(all(exported, 'spotify-export')[0].textContent).toContain('Exportée le 16/10/2026');

    const imported = await render((req) => req.flush({ ...PLAYLIST, source_provider: 'spotify' }));
    expect(all(imported, 'export-spotify').length).toBe(0);
  });

  it("affiche l'erreur Spotify sans quitter la page (session Spotify expirée)", async () => {
    const fixture = await render((req) => req.flush(PLAYLIST));
    all(fixture, 'export-spotify')[0].click();
    http
      .expectOne('/api/playlists/set/export/spotify')
      .flush(
        { detail: 'Session Spotify expirée : reconnecte-toi' },
        { status: 401, statusText: '' },
      );
    await fixture.whenStable();

    expect(all(fixture, 'action-error')[0].textContent).toContain('reconnecte-toi');
    expect(all(fixture, 'item').length).toBe(3);
  });

  it('télécharge la playlist en TXT détaillé ou en tracklist', async () => {
    const fixture = await render((req) => req.flush({ ...PLAYLIST, source_provider: 'spotify' }));

    all(fixture, 'download-detailed')[0].click();
    expect(saveText).toHaveBeenLastCalledWith(
      'Set du samedi.txt',
      expect.stringContaining('⚠ tempo +8,0 %'),
    );
    all(fixture, 'download-tracklist')[0].click();
    expect(saveText).toHaveBeenLastCalledWith(
      'Set du samedi (tracklist).txt',
      expect.stringContaining('02. FISHER – Rock That Body\n'),
    );
  });
});
