import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () => import('./features/status/status.page').then((m) => m.StatusPage),
    title: 'DJ Platform',
  },
  {
    path: 'spotify',
    loadComponent: () =>
      import('./features/spotify/spotify-playlists.page').then((m) => m.SpotifyPlaylistsPage),
    title: 'Mes playlists Spotify · DJ Platform',
  },
  { path: '**', redirectTo: '' },
];
