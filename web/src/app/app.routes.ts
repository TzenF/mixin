import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () => import('./features/home/home.page').then((m) => m.HomePage),
    title: 'DJ Platform',
  },
  {
    path: 'status',
    loadComponent: () => import('./features/status/status.page').then((m) => m.StatusPage),
    title: 'État des services · DJ Platform',
  },
  {
    path: 'spotify',
    loadComponent: () =>
      import('./features/spotify/spotify-playlists.page').then((m) => m.SpotifyPlaylistsPage),
    title: 'Mes playlists Spotify · DJ Platform',
  },
  {
    path: 'catalog',
    loadComponent: () => import('./features/catalog/catalog.page').then((m) => m.CatalogPage),
    title: 'Catalogue · DJ Platform',
  },
  {
    path: 'suggestions/:trackId',
    loadComponent: () =>
      import('./features/suggestions/suggestions.page').then((m) => m.SuggestionsPage),
    title: 'Suggestions · DJ Platform',
  },
  {
    path: 'playlists',
    loadComponent: () => import('./features/playlists/playlists.page').then((m) => m.PlaylistsPage),
    title: 'Playlists · DJ Platform',
  },
  {
    path: 'playlists/:playlistId',
    loadComponent: () =>
      import('./features/playlists/playlist-detail.page').then((m) => m.PlaylistDetailPage),
    title: 'Playlist · DJ Platform',
  },
  { path: '**', redirectTo: '' },
];
