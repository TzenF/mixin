import { ComponentFixture, TestBed } from '@angular/core/testing';
import { AudioPlayerService } from '../../core/audio-player.service';
import { FakeAudioPlayerService } from '../../core/audio-player.service.fake';
import { PlayTransitionButtonComponent } from './play-transition-button.component';

describe('PlayTransitionButtonComponent', () => {
  let player: FakeAudioPlayerService;

  /** Affiche le bouton de l'enchaînement a -> b. */
  async function render(): Promise<ComponentFixture<PlayTransitionButtonComponent>> {
    player = new FakeAudioPlayerService();
    TestBed.configureTestingModule({
      imports: [PlayTransitionButtonComponent],
      providers: [{ provide: AudioPlayerService, useValue: player }],
    });
    const fixture = TestBed.createComponent(PlayTransitionButtonComponent);
    fixture.componentRef.setInput('fromId', 'a');
    fixture.componentRef.setInput('toId', 'b');
    fixture.detectChanges();
    await fixture.whenStable();
    return fixture;
  }

  /** Le bouton du composant. */
  function button(fixture: ComponentFixture<PlayTransitionButtonComponent>): HTMLButtonElement {
    return (fixture.nativeElement as HTMLElement).querySelector('button')!;
  }

  it('lance l’enchaînement, puis propose de l’arrêter', async () => {
    const fixture = await render();
    expect(button(fixture).textContent).toContain("Écouter l'enchaînement");

    button(fixture).click();
    fixture.detectChanges();
    expect(player.calls).toEqual(['transition:a>b']);
    expect(button(fixture).textContent).toContain('Arrêter');
  });

  it('dit honnêtement que ce ne sont pas la vraie fin ni le vrai début', async () => {
    const fixture = await render();
    expect(button(fixture).title).toContain("ce n'est pas la vraie fin de A ni le vrai début de B");
  });

  it('affiche l’erreur de A ou de B', async () => {
    const fixture = await render();
    player.error.set({ trackId: 'b', message: "Pas d'extrait", final: true });
    fixture.detectChanges();
    expect(
      (fixture.nativeElement as HTMLElement).querySelector('[data-testid="transition-error"]')
        ?.textContent,
    ).toBe("Pas d'extrait");
  });
});
