import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { CatalogTrack } from '../../../core/api/catalog.service';
import { OrderProposal, PlaylistDetail, Transition } from '../../../core/api/playlist.service';
import { OrderProposalComponent } from './order-proposal.component';

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

/** Morceau de test. */
function track(id: string, title: string): CatalogTrack {
  return {
    id,
    title,
    artists: ['Artiste'],
    bpm: 124,
    camelot: '6A',
    bpm_source: 'essentia',
    key_source: 'essentia',
    key_confidence: 0.9,
    analysis_status: 'done',
    favorite: false,
    mine: true,
  };
}

const PLAYLIST: PlaylistDetail = {
  id: 'set',
  name: 'Set',
  source_provider: null,
  track_count: 3,
  updated_at: '2026-10-18T10:00:00Z',
  slot_minutes: null,
  played_percent: 100,
  spotify_export: null,
  items: [
    {
      item_id: 1,
      position: 0,
      track: track('a', 'Alpha'),
      transition_to_next: null,
      my_rating: null,
    },
    {
      item_id: 2,
      position: 1,
      track: track('b', 'Bravo'),
      transition_to_next: null,
      my_rating: null,
    },
    {
      item_id: 3,
      position: 2,
      track: track('c', 'Charlie'),
      transition_to_next: null,
      my_rating: null,
    },
  ],
};

const PROPOSAL: OrderProposal = {
  item_ids: [3, 1, 2],
  before: { refused: 2, mean_score: 0 },
  after: { refused: 1, mean_score: 0.42 },
  unanalysed: 0,
  steps: [
    { transition: GOOD, score: 0.84 },
    { transition: null, score: null },
  ],
};

describe('OrderProposalComponent', () => {
  let http: HttpTestingController;

  /** Affiche le bouton pour la playlist de test. */
  async function render(): Promise<ComponentFixture<OrderProposalComponent>> {
    TestBed.configureTestingModule({
      imports: [OrderProposalComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(OrderProposalComponent);
    fixture.componentRef.setInput('playlist', PLAYLIST);
    fixture.detectChanges();
    await fixture.whenStable();
    return fixture;
  }

  afterEach(() => http.verify());

  /** Raccourci : éléments portant ce data-testid. */
  function all(fixture: ComponentFixture<OrderProposalComponent>, id: string): HTMLElement[] {
    return Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll(`[data-testid="${id}"]`),
    );
  }

  /** Demande une proposition et répond avec celle-ci. */
  function propose(
    fixture: ComponentFixture<OrderProposalComponent>,
    proposal: OrderProposal,
  ): void {
    all(fixture, 'propose-order')[0].click();
    http.expectOne('/api/playlists/set/order/proposal').flush(proposal);
    fixture.detectChanges();
  }

  it('montre le bilan et l’ordre proposé, avec chaque enchaînement', async () => {
    const fixture = await render();
    propose(fixture, PROPOSAL);

    const summary = all(fixture, 'order-summary')[0].textContent ?? '';
    expect(summary).toContain('2 → 1');
    expect(summary).toContain('0.00 → 0.42'); // DecimalPipe, comme les BPM des autres pages
    const items = all(fixture, 'proposed-item').map((li) => li.textContent ?? '');
    expect(items.map((t) => t.split('Artiste')[0].trim())).toEqual(['Charlie', 'Alpha', 'Bravo']);
    expect(items[0]).toContain('Tonalité voisine');
    expect(items[1]).toContain('⚠ enchaînement refusé');
  });

  it('applique l’ordre proposé puis prévient la page', async () => {
    const fixture = await render();
    const applied = vi.fn();
    fixture.componentInstance.applied.subscribe(applied);
    propose(fixture, PROPOSAL);

    all(fixture, 'apply-order')[0].click();
    const req = http.expectOne('/api/playlists/set/order');
    expect([req.request.method, req.request.body]).toEqual(['PUT', { item_ids: [3, 1, 2] }]);
    req.flush(null);
    fixture.detectChanges();

    expect(applied).toHaveBeenCalledTimes(1);
    expect(all(fixture, 'order-proposal').length).toBe(0);
  });

  it('prévient si la playlist a changé depuis la proposition', async () => {
    const fixture = await render();
    propose(fixture, PROPOSAL);
    all(fixture, 'apply-order')[0].click();
    http
      .expectOne('/api/playlists/set/order')
      .flush({ detail: 'La playlist a changé' }, { status: 422, statusText: '' });
    fixture.detectChanges();

    expect(all(fixture, 'order-error')[0].textContent).toContain('relance-la');
  });

  it('dit quand l’ordre actuel est déjà le meilleur', async () => {
    const fixture = await render();
    propose(fixture, { ...PROPOSAL, item_ids: [1, 2, 3] });

    expect(all(fixture, 'order-unchanged').length).toBe(1);
    expect(all(fixture, 'apply-order').length).toBe(0);
  });
});
