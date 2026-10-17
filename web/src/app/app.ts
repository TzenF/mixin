import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

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

/** Composant racine : barre de menu, puis la page correspondant à l'URL. */
@Component({
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  selector: 'app-root',
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  protected readonly links = NAV_LINKS;
}
