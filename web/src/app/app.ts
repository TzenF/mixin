import { Component, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter, map } from 'rxjs';
import { AudioPlayerService } from './core/audio-player.service';

/** Une entrée du menu principal. */
interface NavLink {
  path: string;
  label: string;
}

/** Pages du menu (l'accueil est le titre « DJ Platform »). */
export const NAV_LINKS: readonly NavLink[] = [
  { path: '/catalog', label: 'Catalogue' },
  { path: '/explore', label: 'Explorer' },
  { path: '/playlists', label: 'Playlists' },
  { path: '/spotify', label: 'Spotify' },
  { path: '/status', label: 'État' },
];

/** Chemin d'une URL, sans les paramètres ni le fragment (`/explore?source=x` → `/explore`). */
export function pagePath(url: string): string {
  return url.split(/[?#]/, 1)[0];
}

/** Composant racine : barre de menu, puis la page correspondant à l'URL. */
@Component({
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  selector: 'app-root',
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  protected readonly links = NAV_LINKS;

  /** Coupe le son quand on change de page (mais pas quand seuls les filtres de l'URL changent). */
  constructor() {
    const player = inject(AudioPlayerService);
    let previous: string | null = null;
    inject(Router)
      .events.pipe(
        filter((event): event is NavigationEnd => event instanceof NavigationEnd),
        map((event) => pagePath(event.urlAfterRedirects)),
        takeUntilDestroyed(),
      )
      .subscribe((path) => {
        if (previous !== null && path !== previous) {
          player.stop();
        }
        previous = path;
      });
  }
}
