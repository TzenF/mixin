import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { FavoriteButtonComponent } from './favorite-button.component';

describe('FavoriteButtonComponent', () => {
  let http: HttpTestingController;

  /** Affiche le bouton pour le morceau t1, favori ou non. */
  async function render(favorite: boolean): Promise<ComponentFixture<FavoriteButtonComponent>> {
    TestBed.configureTestingModule({
      imports: [FavoriteButtonComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(FavoriteButtonComponent);
    fixture.componentRef.setInput('trackId', 't1');
    fixture.componentRef.setInput('favorite', favorite);
    fixture.detectChanges();
    await fixture.whenStable();
    return fixture;
  }

  /** Le bouton du composant. */
  function button(fixture: ComponentFixture<FavoriteButtonComponent>): HTMLButtonElement {
    return (fixture.nativeElement as HTMLElement).querySelector('button')!;
  }

  afterEach(() => http.verify());

  it('ajoute aux favoris : ★ tout de suite, puis PUT', async () => {
    const fixture = await render(false);
    expect(button(fixture).textContent?.trim()).toBe('☆');

    button(fixture).click();
    fixture.detectChanges();
    expect(button(fixture).textContent?.trim()).toBe('★');
    expect(button(fixture).getAttribute('aria-pressed')).toBe('true');
    const req = http.expectOne('/api/tracks/t1/favorite');
    expect(req.request.method).toBe('PUT');
    req.flush(null, { status: 204, statusText: '' });
  });

  it('retire des favoris avec DELETE', async () => {
    const fixture = await render(true);
    button(fixture).click();
    const req = http.expectOne('/api/tracks/t1/favorite');
    expect(req.request.method).toBe('DELETE');
    req.flush(null, { status: 204, statusText: '' });
    fixture.detectChanges();
    expect(button(fixture).textContent?.trim()).toBe('☆');
  });

  it("revient en arrière si l'API refuse", async () => {
    const fixture = await render(false);
    button(fixture).click();
    http
      .expectOne('/api/tracks/t1/favorite')
      .flush({ detail: 'Morceau inconnu' }, { status: 404, statusText: '' });
    fixture.detectChanges();

    expect(button(fixture).textContent?.trim()).toBe('☆');
    expect(button(fixture).title).toContain('Échec');
  });
});
