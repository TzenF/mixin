import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { LibraryPage } from './library.page';

describe('LibraryPage', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [LibraryPage],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('affiche la carte des tonalités et l’histogramme des BPM', async () => {
    const fixture = TestBed.createComponent(LibraryPage);
    fixture.detectChanges();
    http
      .expectOne('/api/tracks/library-map')
      .flush({ tracks: 3, keys: { '8A': 2 }, bpm_bins: { '124': 3 } });
    await fixture.whenStable();
    fixture.detectChanges();
    const page = fixture.nativeElement as HTMLElement;

    expect(page.querySelector('[data-testid="library-total"]')?.textContent).toContain(
      '3 morceaux',
    );
    expect(page.querySelector('[data-testid="key-heatmap"]')).not.toBeNull();
    expect(page.querySelector('[data-testid="bpm-histogram"]')).not.toBeNull();
  });

  it('propose de se connecter sur une réponse 401', async () => {
    const fixture = TestBed.createComponent(LibraryPage);
    fixture.detectChanges();
    http
      .expectOne('/api/tracks/library-map')
      .flush({ detail: 'Non connecté' }, { status: 401, statusText: '' });
    await fixture.whenStable();
    fixture.detectChanges();

    expect(
      (fixture.nativeElement as HTMLElement).querySelector('[data-testid="connect-spotify"]'),
    ).not.toBeNull();
  });
});
