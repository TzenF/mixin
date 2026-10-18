import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { KeyHeatmapComponent } from './key-heatmap.component';

describe('KeyHeatmapComponent', () => {
  /** Affiche la carte pour ces comptes. */
  async function render(
    counts: Record<string, number>,
  ): Promise<ComponentFixture<KeyHeatmapComponent>> {
    TestBed.configureTestingModule({
      imports: [KeyHeatmapComponent],
      providers: [provideRouter([])],
    });
    const fixture = TestBed.createComponent(KeyHeatmapComponent);
    fixture.componentRef.setInput('counts', counts);
    fixture.detectChanges();
    await fixture.whenStable();
    return fixture;
  }

  /** Raccourci : éléments portant ce data-testid. */
  function all(fixture: ComponentFixture<KeyHeatmapComponent>, id: string): Element[] {
    return Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll(`[data-testid="${id}"]`),
    );
  }

  it('colore les 24 tonalités par palier, du clair au foncé', async () => {
    const fixture = await render({ '8A': 10, '9A': 1, '3B': 5 });
    const cells = new Map(
      all(fixture, 'heat-key').map((g) => [
        g.textContent?.trim(),
        g.querySelector('circle')?.getAttribute('class'),
      ]),
    );

    expect(cells.size).toBe(24);
    expect([cells.get('8A'), cells.get('3B'), cells.get('9A'), cells.get('1A')]).toEqual([
      'cell step-5',
      'cell step-3',
      'cell step-1',
      'cell step-0', // aucun morceau
    ]);
  });

  it('liste les tonalités les moins fournies, avec un lien vers le catalogue filtré', async () => {
    const counts = Object.fromEntries(
      Array.from({ length: 12 }, (_, i) => [
        [`${i + 1}A`, 10],
        [`${i + 1}B`, 10],
      ]).flat(),
    );
    const fixture = await render({ ...counts, '3B': 1, '9B': 2 });
    const links = all(fixture, 'poor-key') as HTMLAnchorElement[];

    expect(links.slice(0, 2).map((a) => a.textContent?.trim())).toEqual(['3B (1)', '9B (2)']);
    expect(links[0].getAttribute('href')).toBe('/catalog?scope=all&key=3B');
  });

  it('au clavier, montre une tonalité et cherche avec Entrée', async () => {
    const fixture = await render({ '1A': 4 });
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    const svg = all(fixture, 'key-heatmap-svg')[0] as SVGElement;

    svg.dispatchEvent(new FocusEvent('focus'));
    fixture.detectChanges();
    expect(all(fixture, 'heat-tooltip')[0].textContent).toContain('4 morceaux');
    svg.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));

    expect(navigate).toHaveBeenCalledWith(['/catalog'], {
      queryParams: { scope: 'all', key: '1A' },
    });
  });
});
