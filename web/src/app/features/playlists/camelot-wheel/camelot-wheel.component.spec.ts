import { ComponentFixture, TestBed } from '@angular/core/testing';
import { CatalogTrack } from '../../../core/api/catalog.service';
import { PlaylistItem, Transition } from '../../../core/api/playlist.service';
import { CamelotWheelComponent } from './camelot-wheel.component';

const ADJACENT: Transition = {
  key_move: 'adjacent',
  key_distance: 1,
  half_double: false,
  bpm_diff: 0.008,
  bpm_change: 0.8,
  tempo_ok: true,
  same_mode: true,
  compatible: true,
};
const FAR_KEY: Transition = { ...ADJACENT, key_move: null, key_distance: 5, compatible: false };
const TOO_FAST: Transition = { ...ADJACENT, bpm_change: 9, tempo_ok: false, compatible: false };

/** Élément de playlist de test dans cette tonalité (null = pas analysé). */
function item(id: number, camelot: string | null, next: Transition | null): PlaylistItem {
  const track: CatalogTrack = {
    id: `t${id}`,
    title: `Titre ${id}`,
    artists: [],
    bpm: camelot === null ? null : 124,
    camelot,
    bpm_source: null,
    key_source: null,
    key_confidence: null,
    analysis_status: camelot === null ? 'pending' : 'done',
    favorite: false,
    mine: true,
  };
  return { item_id: id, position: id - 1, track, transition_to_next: next, my_rating: null };
}

describe('CamelotWheelComponent', () => {
  /** Affiche la roue de ces morceaux. */
  async function render(items: PlaylistItem[]): Promise<ComponentFixture<CamelotWheelComponent>> {
    TestBed.configureTestingModule({ imports: [CamelotWheelComponent] });
    const fixture = TestBed.createComponent(CamelotWheelComponent);
    fixture.componentRef.setInput('items', items);
    fixture.detectChanges();
    await fixture.whenStable();
    return fixture;
  }

  /** Raccourci : éléments portant ce data-testid. */
  function all(fixture: ComponentFixture<CamelotWheelComponent>, id: string): Element[] {
    return Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll(`[data-testid="${id}"]`),
    );
  }

  it('marque les tonalités jouées et trace un seul trait par paire, plus épais s’il revient', async () => {
    // 8A -> 9A -> 8A -> 9A -> 9A : trois passages entre 8A et 9A, dans un sens ou dans l'autre
    const fixture = await render([
      item(1, '8A', ADJACENT),
      item(2, '9A', ADJACENT),
      item(3, '8A', ADJACENT),
      item(4, '9A', ADJACENT),
      item(5, '9A', null),
    ]);

    expect(all(fixture, 'wheel-played').length).toBe(2);
    const moves = all(fixture, 'wheel-move');
    expect(moves.map((m) => [m.getAttribute('class'), m.getAttribute('stroke-width')])).toEqual([
      ['move ok', '4'],
    ]);
    expect(moves[0].getAttribute('d')).toContain('Q'); // même anneau : un arc
    expect(all(fixture, 'wheel-end').map((e) => e.textContent?.trim())).toEqual(['début', 'fin']);
  });

  it('signale une tonalité incompatible, mais pas un tempo trop loin', async () => {
    const fixture = await render([
      item(1, '8A', FAR_KEY),
      item(2, '1A', TOO_FAST),
      item(3, '2A', null),
    ]);

    expect(all(fixture, 'wheel-move').map((m) => m.getAttribute('class'))).toEqual([
      'move warn',
      'move ok', // refusé pour le tempo : c'est la courbe de BPM qui le montre
    ]);
    expect(all(fixture, 'wheel-warning').length).toBe(1);
  });

  it('montre les morceaux d’une tonalité au clavier', async () => {
    const fixture = await render([
      item(1, '8A', ADJACENT),
      item(2, '9A', ADJACENT),
      item(3, '8A', null),
    ]);
    const svg = all(fixture, 'wheel-svg')[0] as SVGElement;

    svg.dispatchEvent(new FocusEvent('focus'));
    fixture.detectChanges();
    const tooltip = all(fixture, 'wheel-tooltip')[0].textContent ?? '';
    expect(tooltip).toContain('8A · 2 morceaux');
    expect(tooltip).toContain('1. Titre 1');
    expect(tooltip).toContain('3. Titre 3');

    svg.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }));
    fixture.detectChanges();
    expect(all(fixture, 'wheel-tooltip')[0].textContent).toContain('9A · 1 morceau');
  });

  it('au-delà de 100 morceaux, garde les tonalités sans le parcours', async () => {
    const items = Array.from({ length: 101 }, (_, i) =>
      item(i + 1, i % 2 === 0 ? '8A' : '9A', ADJACENT),
    );
    const fixture = await render(items);

    expect(all(fixture, 'wheel-played').length).toBe(2);
    expect(all(fixture, 'wheel-move').length).toBe(0);
  });

  it('ne dessine rien avec moins de deux morceaux qui ont une tonalité', async () => {
    const fixture = await render([item(1, '8A', null), item(2, null, null)]);

    expect(all(fixture, 'wheel').length).toBe(0);
  });
});
