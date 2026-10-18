import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Bridge, CatalogTrack, SetPath } from '../../../core/api/catalog.service';
import { Transition } from '../../../core/api/playlist.service';
import { AudioPlayerService } from '../../../core/audio-player.service';
import { FakeAudioPlayerService } from '../../../core/audio-player.service.fake';
import { BridgeFinderComponent } from './bridge-finder.component';

const LEG: Transition = {
  key_move: 'adjacent',
  key_distance: 1,
  half_double: false,
  bpm_diff: 0.004,
  bpm_change: 0.4,
  tempo_ok: true,
  same_mode: true,
  compatible: true,
};
const BRIDGE: Bridge = {
  track_id: 'p1',
  title: 'Pont',
  artists: ['Artiste'],
  bpm: 124.5,
  camelot: '7A',
  score: 0.8,
  favorite: false,
  mine: true,
  incoming: LEG,
  incoming_score: 0.9,
  outgoing: { ...LEG, key_move: 'diagonal', same_mode: false },
  outgoing_score: 0.8,
};

/** Morceau d'un chemin. */
function pathTrack(id: string, title: string): CatalogTrack {
  return {
    id,
    title,
    artists: ['Artiste'],
    bpm: 122,
    camelot: '7A',
    bpm_source: 'essentia',
    key_source: 'essentia',
    key_confidence: 0.9,
    analysis_status: 'done',
    favorite: false,
    mine: true,
  };
}
const PATH: SetPath = {
  tracks: [pathTrack('x', 'Premier'), pathTrack('y', 'Second')],
  steps: [
    { transition: LEG, score: 0.9 },
    { transition: { ...LEG, key_move: 'energy_shift' }, score: 0.5 },
    { transition: LEG, score: 0.9 },
  ],
  score: 0.5,
};

describe('BridgeFinderComponent', () => {
  let http: HttpTestingController;

  /** Affiche le bouton pour l'enchaînement a → b (b à la place 2 de la playlist « set »). */
  async function render(
    inPlaylist: string[] = [],
  ): Promise<ComponentFixture<BridgeFinderComponent>> {
    TestBed.configureTestingModule({
      imports: [BridgeFinderComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: AudioPlayerService, useValue: new FakeAudioPlayerService() },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(BridgeFinderComponent);
    fixture.componentRef.setInput('playlistId', 'set');
    fixture.componentRef.setInput('fromId', 'a');
    fixture.componentRef.setInput('toId', 'b');
    fixture.componentRef.setInput('position', 2);
    fixture.componentRef.setInput('playlistTrackIds', new Set(inPlaylist));
    fixture.detectChanges();
    await fixture.whenStable();
    return fixture;
  }

  afterEach(() => http.verify());

  /** Raccourci : éléments portant ce data-testid. */
  function all(fixture: ComponentFixture<BridgeFinderComponent>, id: string): HTMLElement[] {
    return Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll(`[data-testid="${id}"]`),
    );
  }

  /** Ouvre la liste et répond avec ces ponts. */
  async function open(
    fixture: ComponentFixture<BridgeFinderComponent>,
    bridges: Bridge[],
  ): Promise<void> {
    all(fixture, 'find-bridge')[0].click();
    const req = http.expectOne((r) => r.url === '/api/tracks/a/bridges/b');
    expect([req.request.params.get('scope'), req.request.params.get('limit')]).toEqual([
      'mine',
      '5',
    ]);
    req.flush(bridges);
    fixture.detectChanges();
    await fixture.whenStable();
  }

  it('propose les ponts avec leurs deux enchaînements', async () => {
    const fixture = await render(['p1']);
    await open(fixture, [BRIDGE]);

    const text = all(fixture, 'bridge')[0].textContent ?? '';
    expect(text).toContain('Pont');
    expect(text).toContain('Avant : → +0,4 % · Tonalité voisine');
    expect(text).toContain('Après : → +0,4 % · Diagonale');
    expect(text).toContain('déjà dans la playlist');
  });

  it('insère le pont à la place de B et prévient la page', async () => {
    const fixture = await render();
    const inserted = vi.fn();
    fixture.componentInstance.inserted.subscribe(inserted);
    await open(fixture, [BRIDGE]);

    all(fixture, 'insert-bridge')[0].click();
    const req = http.expectOne('/api/playlists/set/items');
    expect(req.request.body).toEqual({ track_id: 'p1', position: 2 });
    req.flush({ item_id: 9, position: 2 });
    fixture.detectChanges();

    expect(inserted).toHaveBeenCalledTimes(1);
    expect(all(fixture, 'bridges').length).toBe(0); // refermé
  });

  it('sans pont, cherche un chemin et insère tous ses morceaux', async () => {
    const fixture = await render(['y']);
    const inserted = vi.fn();
    fixture.componentInstance.inserted.subscribe(inserted);
    await open(fixture, []);

    all(fixture, 'find-path')[0].click();
    const req = http.expectOne((r) => r.url === '/api/tracks/a/paths/b');
    expect(req.request.params.get('scope')).toBe('mine');
    req.flush([PATH]);
    fixture.detectChanges();

    const text = all(fixture, 'path')[0].textContent ?? '';
    expect(text).toContain('Premier');
    expect(text).toContain("Saut de 2 (montée d'énergie)");
    expect(text).toContain('déjà dans la playlist'); // « Second »
    all(fixture, 'insert-path')[0].click();
    const insert = http.expectOne('/api/playlists/set/items/batch');
    expect(insert.request.body).toEqual({ track_ids: ['x', 'y'], position: 2 });
    insert.flush([
      { item_id: 9, position: 2 },
      { item_id: 10, position: 3 },
    ]);

    expect(inserted).toHaveBeenCalledTimes(1);
  });

  it('dit quand il n’y a aucun chemin', async () => {
    const fixture = await render();
    await open(fixture, []);
    all(fixture, 'find-path')[0].click();
    http.expectOne((r) => r.url === '/api/tracks/a/paths/b').flush([]);
    fixture.detectChanges();

    expect(all(fixture, 'no-path').length).toBe(1);
  });

  it('dit quand aucun morceau ne fait le pont, et cherche ailleurs sur demande', async () => {
    const fixture = await render();
    await open(fixture, []);
    expect(all(fixture, 'no-bridge')[0].textContent).toContain('parmi tes morceaux');

    const box = all(fixture, 'bridges-everywhere')[0] as HTMLInputElement;
    box.checked = true;
    box.dispatchEvent(new Event('change'));
    const req = http.expectOne((r) => r.url === '/api/tracks/a/bridges/b');
    expect(req.request.params.get('scope')).toBe('all');
    req.flush([BRIDGE]);
    fixture.detectChanges();

    expect(all(fixture, 'bridge').length).toBe(1);
  });
});
