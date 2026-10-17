import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { CatalogTrack } from '../../core/api/catalog.service';
import { TrackCorrectionComponent } from './track-correction.component';

const BLADE: CatalogTrack = {
  id: 'blade',
  title: 'Blade',
  artists: ["D'Angello & Francis"],
  bpm: 150.2,
  camelot: '9B',
  bpm_source: 'essentia',
  key_source: 'essentia',
  key_confidence: 0.7,
  analysis_status: 'done',
  favorite: false,
  mine: true,
};

describe('TrackCorrectionComponent', () => {
  let http: HttpTestingController;
  let emitted: CatalogTrack[];

  /** Affiche le composant pour ce morceau, formulaire ouvert. */
  async function render(
    track: CatalogTrack = BLADE,
  ): Promise<ComponentFixture<TrackCorrectionComponent>> {
    TestBed.configureTestingModule({
      imports: [TrackCorrectionComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(TrackCorrectionComponent);
    fixture.componentRef.setInput('track', track);
    emitted = [];
    fixture.componentInstance.corrected.subscribe((t) => emitted.push(t));
    fixture.detectChanges();
    el(fixture, 'correct').click();
    fixture.detectChanges();
    return fixture;
  }

  /** Raccourci : élément portant ce data-testid (doit exister). */
  function el<T extends HTMLElement = HTMLElement>(
    fixture: ComponentFixture<TrackCorrectionComponent>,
    id: string,
  ): T {
    return (fixture.nativeElement as HTMLElement).querySelector<T>(`[data-testid="${id}"]`)!;
  }

  afterEach(() => http.verify());

  it('divise le BPM par deux et n’envoie que le champ modifié', async () => {
    const fixture = await render();
    el(fixture, 'half').click();
    expect(el<HTMLInputElement>(fixture, 'correction-bpm').value).toBe('75.1');

    el(fixture, 'correction-save').click();
    const req = http.expectOne('/api/tracks/blade/correction');
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual({ bpm: 75.1 });
    req.flush({ ...BLADE, bpm: 75.1, bpm_source: 'manual' });
    fixture.detectChanges();

    expect(emitted.map((t) => t.bpm)).toEqual([75.1]);
    expect(el(fixture, 'correct')).not.toBeNull(); // formulaire refermé
  });

  it('corrige la tonalité, et ne fait rien si rien ne change', async () => {
    const fixture = await render();
    el(fixture, 'correction-save').click(); // rien de modifié
    fixture.detectChanges();
    http.expectNone('/api/tracks/blade/correction');

    el(fixture, 'correct').click();
    fixture.detectChanges();
    el<HTMLInputElement>(fixture, 'correction-key').value = 'Am';
    el(fixture, 'correction-save').click();
    expect(http.expectOne('/api/tracks/blade/correction').request.body).toEqual({ key: 'Am' });
  });

  it('refuse un BPM hors limites sans appeler l’API', async () => {
    const fixture = await render();
    el<HTMLInputElement>(fixture, 'correction-bpm').value = '300';
    el(fixture, 'correction-save').click();
    fixture.detectChanges();

    expect(el(fixture, 'correction-error').textContent).toContain('entre 40 et 250');
  });

  it('propose d’annuler une correction existante', async () => {
    const fixture = await render({ ...BLADE, bpm: 75.1, bpm_source: 'manual' });
    expect(
      (fixture.nativeElement as HTMLElement).querySelector('[data-testid="cancel-key"]'),
    ).toBeNull();

    el(fixture, 'cancel-bpm').click();
    const req = http.expectOne('/api/tracks/blade/correction');
    expect(req.request.body).toEqual({ bpm: null });
    req.flush(BLADE);
    expect(emitted.map((t) => t.bpm_source)).toEqual(['essentia']);
  });

  it("affiche l'erreur de l'API", async () => {
    const fixture = await render();
    el<HTMLInputElement>(fixture, 'correction-key').value = '13Z';
    el(fixture, 'correction-save').click();
    http
      .expectOne('/api/tracks/blade/correction')
      .flush({ detail: "Tonalité non reconnue : '13Z'" }, { status: 422, statusText: '' });
    fixture.detectChanges();

    expect(el(fixture, 'correction-error').textContent).toContain('Tonalité non reconnue');
  });
});
