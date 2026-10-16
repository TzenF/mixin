import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { HomePage } from './home.page';

describe('HomePage', () => {
  it('propose un bouton vers chaque page', async () => {
    TestBed.configureTestingModule({ imports: [HomePage], providers: [provideRouter([])] });
    const fixture = TestBed.createComponent(HomePage);
    fixture.detectChanges();
    await fixture.whenStable();

    const root = fixture.nativeElement as HTMLElement;
    const hrefs = Array.from(root.querySelectorAll('[data-testid="home-links"] a')).map((a) =>
      a.getAttribute('href'),
    );
    expect(hrefs).toEqual(['/catalog', '/playlists', '/spotify', '/status']);
  });
});
