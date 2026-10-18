import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { BpmHistogramComponent } from './bpm-histogram.component';

describe('BpmHistogramComponent', () => {
  /** Affiche l'histogramme de ces tranches. */
  async function render(
    counts: Record<string, number>,
  ): Promise<ComponentFixture<BpmHistogramComponent>> {
    TestBed.configureTestingModule({
      imports: [BpmHistogramComponent],
      providers: [provideRouter([])],
    });
    const fixture = TestBed.createComponent(BpmHistogramComponent);
    fixture.componentRef.setInput('counts', counts);
    fixture.detectChanges();
    await fixture.whenStable();
    return fixture;
  }

  /** Raccourci : éléments portant ce data-testid. */
  function all(fixture: ComponentFixture<BpmHistogramComponent>, id: string): HTMLElement[] {
    return Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll(`[data-testid="${id}"]`),
    );
  }

  it('montre chaque tranche, vides comprises, avec un lien vers le catalogue filtré', async () => {
    const fixture = await render({ '120': 4, '126': 2 });
    const bins = all(fixture, 'bpm-bin') as HTMLAnchorElement[];

    expect(bins.length).toBe(4); // 120, 122, 124, 126
    expect(all(fixture, 'bpm-hole').length).toBe(2);
    expect(bins[0].title).toBe('120–122 BPM : 4 morceaux');
    expect(bins[0].getAttribute('href')).toBe('/catalog?scope=all&bpm_min=120&bpm_max=121.99');
    expect((bins[3].querySelector('.bar') as HTMLElement).style.height).toBe('50%');
  });

  it('regroupe les plages vides entre 90 et 160 BPM', async () => {
    const fixture = await render({ '80': 1, '84': 1, '120': 4, '128': 2 });

    // 82 à 88 sont vides mais hors de la zone ; 90 à 120 et 122 à 128 sont deux plages vides
    expect(all(fixture, 'bpm-gap').map((a) => a.textContent?.trim())).toEqual([
      '90–120 BPM',
      '122–128 BPM',
    ]);
  });
});
