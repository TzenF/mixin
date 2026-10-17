import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

/** Une entrée du menu d'accueil. */
interface HomeLink {
  path: string;
  label: string;
  description: string;
}

const LINKS: HomeLink[] = [
  {
    path: '/catalog',
    label: 'Catalogue',
    description: 'Mes morceaux avec BPM et tonalité ; bouton « Suggestions » pour enchaîner',
  },
  {
    path: '/explore',
    label: 'Explorer',
    description: 'Tops et playlists éditoriales Deezer : de nouveaux morceaux à découvrir',
  },
  {
    path: '/playlists',
    label: 'Playlists',
    description: 'Mes playlists et la qualité de chaque enchaînement',
  },
  {
    path: '/spotify',
    label: 'Mes playlists Spotify',
    description: 'Connexion à Spotify et import des playlists',
  },
  { path: '/status', label: 'État des services', description: 'Base de données et file de tâches' },
];

/** Page d'accueil : un bouton par page de l'application. */
@Component({
  selector: 'app-home-page',
  imports: [RouterLink],
  templateUrl: './home.page.html',
  styleUrl: './home.page.scss',
})
export class HomePage {
  protected readonly links = LINKS;
}
