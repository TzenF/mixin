import { ComponentFixture, TestBed } from '@angular/core/testing';
import { CatalogTrack } from '../../../core/api/catalog.service';
import { PlaylistItem, Transition } from '../../../core/api/playlist.service';
import { PlaylistCurveComponent } from './playlist-curve.component';

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
const TOO_FAST: Transition = { ...GOOD, bpm_change: 8, tempo_ok: false, compatible: false };

/** Élément de playlist de test (bpm null = pas analysé). */
function item(id: number, bpm: number | null, next: Transition | null): PlaylistItem {
  const track: CatalogTrack = {
    id: `t${id}`,
    title: `Titre ${id}`,
    artists: [],
    bpm,
    camelot: bpm === null ? null : '6A',
    bpm_source: null,
    key_source: null,
    key_confidence: null,
    analysis_status: bpm === null ? 'pending' : 'done',
    favorite: false,
    mine: true,
  };
  return { item_id: id, position: id - 1, track, transition_to_next: next, my_rating: null };
}

describe('PlaylistCurveComponent', () => {
  /** Affiche la courbe de ces morceaux. */
  async function render(items: PlaylistItem[]): Promise<ComponentFixture<PlaylistCurveComponent>> {
    TestBed.configureTestingModule({ imports: [PlaylistCurveComponent] });
    const fixture = TestBed.createComponent(PlaylistCurveComponent);
    fixture.componentRef.setInput('items', items);
    fixture.detectChanges();
    await fixture.whenStable();
    return fixture;
  }

  /** Raccourci : éléments portant ce data-testid. */
  function all(fixture: ComponentFixture<PlaylistCurveComponent>, id: string): Element[] {
    return Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll(`[data-testid="${id}"]`),
    );
  }

  it('trace un segment par enchaînement, coloré par sa qualité, avec ⚠ sur les refusés', async () => {
    const fixture = await render([item(1, 124, GOOD), item(2, 125, TOO_FAST), item(3, 135, null)]);

    const segments = all(fixture, 'curve-segment').map((s) => s.getAttribute('class'));
    expect(segments).toEqual(['segment ok', 'segment warn']);
    expect(all(fixture, 'curve-warning').length).toBe(1);
    expect(all(fixture, 'curve-marker').length).toBe(3);
  });

  it('interrompt la courbe sur un morceau non analysé', async () => {
    const fixture = await render([item(1, 124, null), item(2, null, null), item(3, 126, null)]);

    expect(all(fixture, 'curve-segment').length).toBe(0);
    expect(all(fixture, 'curve-marker').length).toBe(2);
  });

  it('étiquette seulement le BPM le plus bas et le plus haut', async () => {
    const fixture = await render([item(1, 124, GOOD), item(2, 125, GOOD), item(3, 128, null)]);

    expect(all(fixture, 'curve-extreme').map((e) => e.textContent?.trim())).toEqual(['124', '128']);
  });

  it('montre le morceau et son enchaînement au clavier', async () => {
    const fixture = await render([item(1, 124, GOOD), item(2, 125, TOO_FAST), item(3, 135, null)]);
    const svg = all(fixture, 'curve-svg')[0] as SVGElement;

    svg.dispatchEvent(new FocusEvent('focus'));
    fixture.detectChanges();
    expect(all(fixture, 'curve-tooltip')[0].textContent).toContain('1. Titre 1');
    expect(all(fixture, 'curve-tooltip')[0].textContent).toContain('Tonalité voisine');

    svg.dispatchEvent(new KeyboardEvent('keydown', { key: 'End' }));
    fixture.detectChanges();
    const last = all(fixture, 'curve-tooltip')[0].textContent ?? '';
    expect(last).toContain('135.0 BPM');
    expect(last).not.toContain('→'); // pas d'enchaînement après le dernier
  });

  it('ne dessine rien avec moins de deux morceaux analysés', async () => {
    const fixture = await render([item(1, 124, null), item(2, null, null)]);

    expect(all(fixture, 'curve').length).toBe(0);
  });
});
