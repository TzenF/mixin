import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { Component } from '@angular/core';
import { App } from './app';
import { AudioPlayerService } from './core/audio-player.service';
import { FakeAudioPlayerService } from './core/audio-player.service.fake';

/** Page vide pour les routes de test. */
@Component({ template: '' })
class EmptyPage {}

describe('App (menu)', () => {
  let player: FakeAudioPlayerService;

  /** Affiche l'application sur cette URL. */
  async function render(url: string) {
    player = new FakeAudioPlayerService();
    TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideRouter(
          ['', 'catalog', 'explore', 'playlists', 'spotify', 'status'].map((path) => ({
            path,
            component: EmptyPage,
          })),
        ),
        { provide: AudioPlayerService, useValue: player },
      ],
    });
    const fixture = TestBed.createComponent(App);
    await TestBed.inject(Router).navigateByUrl(url);
    fixture.detectChanges();
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  }

  it('propose un lien vers chaque page et vers l’accueil', async () => {
    const root = await render('/');
    const hrefs = Array.from(root.querySelectorAll('nav a')).map((a) => a.getAttribute('href'));
    expect(hrefs).toEqual(['/', '/catalog', '/explore', '/playlists', '/spotify', '/status']);
  });

  it('signale la page active', async () => {
    const root = await render('/playlists');
    expect(root.querySelector('[data-testid="nav-playlists"]')?.getAttribute('aria-current')).toBe(
      'page',
    );
    expect(
      root.querySelector('[data-testid="nav-catalog"]')?.getAttribute('aria-current'),
    ).toBeNull();
  });

  it('coupe le son quand on change de page', async () => {
    await render('/catalog');
    player.toggle('t1');
    await TestBed.inject(Router).navigateByUrl('/explore');

    expect(player.state()).toBe('idle');
  });

  it('laisse jouer le son quand seuls les paramètres de l’URL changent', async () => {
    await render('/explore?source=a');
    player.toggle('t1');
    await TestBed.inject(Router).navigateByUrl('/explore?source=b');

    expect(player.state()).toBe('playing');
  });
});
