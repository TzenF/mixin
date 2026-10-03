import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { StatusPage } from './status.page';

describe('StatusPage', () => {
  let http: HttpTestingController;

  function render() {
    const fixture = TestBed.createComponent(StatusPage);
    fixture.detectChanges();
    return fixture;
  }

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [StatusPage],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('affiche les services quand tout va bien', async () => {
    const fixture = render();
    http.expectOne('/api/health').flush({ status: 'ok', database: true, queue: true });
    await fixture.whenStable();

    const text = fixture.nativeElement.querySelector('[data-testid="services"]').textContent;
    expect(text).toContain('Base de données : OK');
    expect(text).toContain('File de tâches : OK');
  });

  it("affiche le détail quand l'API répond 503", async () => {
    const fixture = render();
    http
      .expectOne('/api/health')
      .flush({ status: 'degraded', database: true, queue: false }, { status: 503, statusText: 'Unavailable' });
    await fixture.whenStable();

    const text = fixture.nativeElement.querySelector('[data-testid="services"]').textContent;
    expect(text).toContain('File de tâches : en panne');
  });

  it("affiche une erreur quand l'API est injoignable", async () => {
    const fixture = render();
    http.expectOne('/api/health').error(new ProgressEvent('error'), { status: 0 });
    await fixture.whenStable();

    expect(fixture.nativeElement.querySelector('[data-testid="error"]')).not.toBeNull();
  });
});
