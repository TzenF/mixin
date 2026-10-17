import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { apiErrorMessage } from '../../core/api/api-error';
import { SPOTIFY_LOGIN_URL } from '../../core/api/auth.service';
import { PlaylistService, PlaylistSummary } from '../../core/api/playlist.service';
import { RatingService } from '../../core/api/rating.service';
import { CurrentPlaylistService } from '../../core/current-playlist.service';

type State =
  | { kind: 'loading' }
  | { kind: 'disconnected' }
  | { kind: 'ready'; playlists: PlaylistSummary[] }
  | { kind: 'error'; message: string };

/** Page « Playlists » : mes playlists (créées ici ou importées) ; créer, dupliquer, supprimer, choisir celle en cours. */
@Component({
  selector: 'app-playlists-page',
  templateUrl: './playlists.page.html',
  styleUrl: './playlists.page.scss',
})
export class PlaylistsPage {
  private readonly service = inject(PlaylistService);
  private readonly router = inject(Router);
  protected readonly currentPlaylist = inject(CurrentPlaylistService);

  protected readonly loginUrl = SPOTIFY_LOGIN_URL;
  /** Nombre d'enchaînements que j'ai notés, ou null tant qu'il n'est pas connu. */
  protected readonly ratedCount = signal<number | null>(null);
  protected readonly state = signal<State>({ kind: 'loading' });
  /** Échec de la dernière action (créer, dupliquer, supprimer), ou null. */
  protected readonly actionError = signal<string | null>(null);

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
    this.currentPlaylist.refresh();
    inject(RatingService)
      .count()
      .subscribe({
        next: (count) => this.ratedCount.set(count),
        error: () => this.ratedCount.set(null),
      });
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

  /** Crée une playlist avec ce nom ; elle devient la playlist en cours. */
  protected create(nameInput: HTMLInputElement): void {
    const name = nameInput.value.trim();
    if (name === '') {
      return;
    }
    this.currentPlaylist.create(name).subscribe({
      next: () => {
        nameInput.value = '';
        this.load();
      },
      error: (err: HttpErrorResponse) => this.fail(err, 'Impossible de créer la playlist.'),
    });
  }

  /** Fait de cette playlist la playlist en cours. */
  protected makeCurrent(playlist: PlaylistSummary): void {
    this.currentPlaylist.select(playlist.id);
  }

  /** Duplique la playlist (une importée devient ainsi modifiable). */
  protected duplicate(playlist: PlaylistSummary): void {
    this.service.copy(playlist.id).subscribe({
      next: () => {
        this.load();
        this.currentPlaylist.refresh();
      },
      error: (err: HttpErrorResponse) => this.fail(err, 'Impossible de dupliquer la playlist.'),
    });
  }

  /** Supprime la playlist après confirmation (les morceaux restent dans le catalogue). */
  protected remove(playlist: PlaylistSummary): void {
    if (!confirm(`Supprimer « ${playlist.name} » ? Les morceaux restent dans le catalogue.`)) {
      return;
    }
    this.service.delete(playlist.id).subscribe({
      next: () => {
        this.load();
        this.currentPlaylist.refresh();
      },
      error: (err: HttpErrorResponse) => this.fail(err, 'Impossible de supprimer la playlist.'),
    });
  }

  /** Affiche l'échec d'une action ; 401 = pas connectée. */
  private fail(err: HttpErrorResponse, fallback: string): void {
    if (err.status === 401) {
      this.state.set({ kind: 'disconnected' });
    } else {
      this.actionError.set(apiErrorMessage(err, fallback));
    }
  }
}
