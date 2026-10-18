import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Placement } from '../../core/api/catalog.service';
import { Transition } from '../../core/api/playlist.service';
import { CurrentPlaylistService } from '../../core/current-playlist.service';
import { FakeCurrentPlaylistService } from '../../core/current-playlist.service.fake';
import { PlacementFinderComponent } from './placement-finder.component';

const SAME: Transition = {
  key_move: 'same',
  key_distance: 0,
  half_double: false,
  bpm_diff: 0.008,
  bpm_change: 0.8,
  tempo_ok: true,
  same_mode: true,
  compatible: true,
};
const REPAIR: Placement = {
  position: 2,
  before: { place: 2, title: 'Bravo' },
  after: { place: 3, title: 'Charlie' },
  incoming: SAME,
  outgoing: SAME,
  repairs: true,
  score: 0.8,
};
const OPENING: Placement = {
  position: 0,
  before: null,
  after: { place: 1, title: 'Alpha' },
  incoming: null,
  outgoing: SAME,
  repairs: false,
  score: 0.9,
};
const ONE_SIDED: Placement = { ...REPAIR, position: 3, repairs: false, outgoing: null };

describe('PlacementFinderComponent', () => {
  let http: HttpTestingController;
  let currentPlaylist: FakeCurrentPlaylistService;

  /** Affiche les places du morceau x (avec ou sans playlist en cours). */
  async function render(withCurrent = true): Promise<ComponentFixture<PlacementFinderComponent>> {
    currentPlaylist = new FakeCurrentPlaylistService();
    if (withCurrent) {
      currentPlaylist.select('current');
    }
    TestBed.configureTestingModule({
      imports: [PlacementFinderComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: CurrentPlaylistService, useValue: currentPlaylist },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(PlacementFinderComponent);
    fixture.componentRef.setInput('trackId', 'x');
    fixture.detectChanges();
    await fixture.whenStable();
    return fixture;
  }

  afterEach(() => http.verify());

  /** Raccourci : éléments portant ce data-testid. */
  function all(fixture: ComponentFixture<PlacementFinderComponent>, id: string): HTMLElement[] {
    return Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll(`[data-testid="${id}"]`),
    );
  }

  it('liste les places, la réparation d’un ⚠ et l’état de chaque côté', async () => {
    const fixture = await render();
    const req = http.expectOne((r) => r.url === '/api/tracks/x/placements');
    expect(req.request.params.get('playlist')).toBe('current');
    req.flush([REPAIR, OPENING, ONE_SIDED]);
    fixture.detectChanges();

    const texts = all(fixture, 'placement').map((li) => li.textContent ?? '');
    expect(texts[0]).toContain('Entre 2. Bravo et 3. Charlie');
    expect(texts[0]).toContain('répare un ⚠');
    expect(texts[0]).toContain('✓ avant : +0,8 % · Même tonalité');
    expect(texts[1]).toContain('En ouverture, avant 1. Alpha');
    expect(texts[1]).not.toContain('avant :'); // rien à enchaîner avant l'ouverture
    expect(texts[2]).toContain('⚠ après : refusé');
  });

  it('insère à la place choisie puis prévient la liste', async () => {
    const fixture = await render();
    const inserted = vi.fn();
    fixture.componentInstance.inserted.subscribe(inserted);
    http.expectOne((r) => r.url === '/api/tracks/x/placements').flush([REPAIR]);
    fixture.detectChanges();

    all(fixture, 'insert-placement')[0].click();

    expect([currentPlaylist.added, currentPlaylist.positions]).toEqual([['x'], [2]]);
    expect(inserted).toHaveBeenCalledTimes(1);
  });

  it('sans playlist en cours, le dit sans rien demander', async () => {
    const fixture = await render(false);

    expect(all(fixture, 'placement-error')[0].textContent).toContain('playlist en cours');
  });
});
