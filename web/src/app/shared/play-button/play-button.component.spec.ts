import { ComponentFixture, TestBed } from '@angular/core/testing';
import { AudioPlayerService } from '../../core/audio-player.service';
import { FakeAudioPlayerService } from '../../core/audio-player.service.fake';
import { PlayButtonComponent } from './play-button.component';

describe('PlayButtonComponent', () => {
  let player: FakeAudioPlayerService;

  /** Affiche le bouton du morceau t1. */
  async function render(noPreview = false): Promise<ComponentFixture<PlayButtonComponent>> {
    player = new FakeAudioPlayerService();
    TestBed.configureTestingModule({
      imports: [PlayButtonComponent],
      providers: [{ provide: AudioPlayerService, useValue: player }],
    });
    const fixture = TestBed.createComponent(PlayButtonComponent);
    fixture.componentRef.setInput('trackId', 't1');
    fixture.componentRef.setInput('noPreview', noPreview);
    fixture.detectChanges();
    await fixture.whenStable();
    return fixture;
  }

  /** Le bouton du composant. */
  function button(fixture: ComponentFixture<PlayButtonComponent>): HTMLButtonElement {
    return (fixture.nativeElement as HTMLElement).querySelector('button')!;
  }

  it('lance la lecture et affiche ⏸ avec la progression', async () => {
    const fixture = await render();
    expect(button(fixture).textContent?.trim()).toBe('▶');

    button(fixture).click();
    player.progress.set(0.5);
    fixture.detectChanges();

    expect(player.calls).toEqual(['toggle:t1']);
    expect(button(fixture).textContent?.trim()).toBe('⏸');
    const bar = (fixture.nativeElement as HTMLElement).querySelector<HTMLElement>(
      '[data-testid="play-progress"]',
    );
    expect(bar?.style.width).toBe('50%');
  });

  it("n'affiche rien d'autre quand un autre morceau joue", async () => {
    const fixture = await render();
    player.toggle('autre');
    fixture.detectChanges();
    expect(button(fixture).textContent?.trim()).toBe('▶');
    expect(
      (fixture.nativeElement as HTMLElement).querySelector('[data-testid="play-progress"]'),
    ).toBeNull();
  });

  it('est désactivé avec la raison quand il n’y a pas d’extrait', async () => {
    const known = await render(true);
    expect(button(known).disabled).toBe(true);
    expect(button(known).title).toBe("Pas d'extrait Deezer pour ce morceau");
  });

  it('se désactive après un 404, mais reste cliquable après une panne de Deezer', async () => {
    const fixture = await render();
    player.error.set({ trackId: 't1', message: 'Deezer est indisponible', final: false });
    fixture.detectChanges();
    expect([button(fixture).disabled, button(fixture).title]).toEqual([
      false,
      'Deezer est indisponible',
    ]);

    player.error.set({ trackId: 't1', message: "Pas d'extrait", final: true });
    fixture.detectChanges();
    expect([button(fixture).disabled, button(fixture).title]).toEqual([true, "Pas d'extrait"]);
  });
});
