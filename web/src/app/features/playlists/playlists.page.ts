import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { apiErrorMessage } from '../../core/api/api-error';
import { SPOTIFY_LOGIN_URL } from '../../core/api/auth.service';
import { PlaylistService, PlaylistSummary } from '../../core/api/playlist.service';

type State =
  | { kind: 'loading' }
  | { kind: 'disconnected' }
  | { kind: 'ready'; playlists: PlaylistSummary[] }
  | { kind: 'error'; message: string };

/** Page « Playlists » : mes playlists, créées ici ou importées de Spotify. */
@Component({
  selector: 'app-playlists-page',
  templateUrl: './playlists.page.html',
  styleUrl: './playlists.page.scss',
})
export class PlaylistsPage {
  private readonly service = inject(PlaylistService);
  private readonly router = inject(Router);

  protected readonly loginUrl = SPOTIFY_LOGIN_URL;
  protected readonly state = signal<State>({ kind: 'loading' });

  /** Playlists affichées, ou null tant qu'elles ne sont pas chargées. */
  protected readonly playlists = computed(() => {
    const s = this.state();
    return s.kind === 'ready' ? s.playlists : null;
  });

  /** Message d'erreur de chargement, ou null. */
  protected readonly errorMessage = computed(() => {
    const s = this.state();
    return s.kind === 'error' ? s.message : null;
  });

  constructor() {
    this.load();
  }

  /** Charge mes playlists ; 401 = pas connectée. */
  protected load(): void {
    this.state.set({ kind: 'loading' });
    this.service.list().subscribe({
      next: (playlists) => this.state.set({ kind: 'ready', playlists }),
      error: (err: HttpErrorResponse) =>
        this.state.set(
          err.status === 401
            ? { kind: 'disconnected' }
            : {
                kind: 'error',
                message: apiErrorMessage(err, 'Impossible de charger les playlists.'),
              },
        ),
    });
  }

  /** Ouvre le détail d'une playlist. */
  protected open(playlist: PlaylistSummary): void {
    void this.router.navigate(['/playlists', playlist.id]);
  }
}
