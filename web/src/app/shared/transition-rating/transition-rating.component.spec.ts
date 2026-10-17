import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TransitionRating } from '../../core/api/catalog.service';
import { AudioPlayerService } from '../../core/audio-player.service';
import { FakeAudioPlayerService } from '../../core/audio-player.service.fake';
import { TransitionRatingComponent } from './transition-rating.component';

const URL = '/api/transitions/a/b/rating';

describe('TransitionRatingComponent', () => {
  let http: HttpTestingController;
  let player: FakeAudioPlayerService;

  /** Affiche la notation de l'enchaînement a -> b, avec une note de départ éventuelle. */
  async function render(
    rating: TransitionRating | null = null,
  ): Promise<ComponentFixture<TransitionRatingComponent>> {
    player = new FakeAudioPlayerService();
    TestBed.configureTestingModule({
      imports: [TransitionRatingComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: AudioPlayerService, useValue: player },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(TransitionRatingComponent);
    fixture.componentRef.setInput('fromId', 'a');
    fixture.componentRef.setInput('toId', 'b');
    fixture.componentRef.setInput('rating', rating);
    fixture.detectChanges();
    await fixture.whenStable();
    return fixture;
  }

  /** Raccourci : élément portant ce data-testid, ou null. */
  function el<T extends HTMLElement = HTMLElement>(
    fixture: ComponentFixture<TransitionRatingComponent>,
    id: string,
  ) {
    return (fixture.nativeElement as HTMLElement).querySelector<T>(`[data-testid="${id}"]`);
  }

  /** Note actuellement allumée (aria-pressed), ou null. */
  function pressed(fixture: ComponentFixture<TransitionRatingComponent>): string | null {
    const on = (fixture.nativeElement as HTMLElement).querySelector('[aria-pressed="true"]');
    return on?.textContent?.trim() ?? null;
  }

  afterEach(() => http.verify());

  it('note tout de suite, puis enregistre', async () => {
    const fixture = await render();
    el(fixture, 'rate-4')!.click();
    fixture.detectChanges();
    expect(pressed(fixture)).toBe('4');

    const req = http.expectOne(URL);
    expect([req.request.method, req.request.body]).toEqual(['PUT', { rating: 4, comment: null }]);
    req.flush({ rating: 4, comment: null });
  });

  it('ajoute un commentaire en gardant la note', async () => {
    const fixture = await render({ rating: 2, comment: null });
    el(fixture, 'rating-comment-toggle')!.click();
    fixture.detectChanges();
    el<HTMLInputElement>(fixture, 'rating-comment')!.value = '  trop brusque  ';
    el(fixture, 'rating-comment-save')!.click();

    expect(http.expectOne(URL).request.body).toEqual({ rating: 2, comment: 'trop brusque' });
  });

  it('efface ma note', async () => {
    const fixture = await render({ rating: 5, comment: 'parfait' });
    el(fixture, 'rating-clear')!.click();
    fixture.detectChanges();

    expect(http.expectOne(URL).request.method).toBe('DELETE');
    expect(pressed(fixture)).toBeNull();
    expect(el(fixture, 'rating-clear')).toBeNull();
  });

  it("revient en arrière si l'API refuse", async () => {
    const fixture = await render({ rating: 3, comment: null });
    el(fixture, 'rate-1')!.click();
    http.expectOne(URL).flush({ detail: 'Morceau inconnu' }, { status: 404, statusText: '' });
    fixture.detectChanges();

    expect(pressed(fixture)).toBe('3');
    expect(el(fixture, 'rating-error')?.textContent).toContain('Morceau inconnu');
  });

  it('invite à noter juste après avoir écouté cet enchaînement', async () => {
    const fixture = await render();
    expect(el(fixture, 'rating-invite')).toBeNull();

    player.lastFinished.set({ fromId: 'a', toId: 'b' });
    fixture.detectChanges();
    expect(el(fixture, 'rating-invite')?.textContent).toContain('Note cet enchaînement');

    player.lastFinished.set({ fromId: 'a', toId: 'autre' });
    fixture.detectChanges();
    expect(el(fixture, 'rating-invite')).toBeNull();
  });
});
