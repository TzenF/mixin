import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { apiErrorMessage } from '../../core/api/api-error';
import { AuthService, SPOTIFY_LOGIN_URL } from '../../core/api/auth.service';
import { ImportOutcome, SpotifyPlaylist, SpotifyService } from '../../core/api/spotify.service';

type State =
  | { kind: 'loading' }
  | { kind: 'disconnected' }
  | { kind: 'ready'; playlists: SpotifyPlaylist[] }
  | { kind: 'error'; message: string };

/** Avancement de l'import d'une playlist. */
type ImportState =
  | { kind: 'importing' }
  | { kind: 'done'; outcome: ImportOutcome }
  | { kind: 'error'; message: string };

/** Messages des échecs de connexion renvoyés par l'API dans ?spotify_error=… */
const LOGIN_ERRORS: Record<string, string> = {
  access_denied: "Tu as refusé l'accès à Spotify.",
  spotify:
    "Spotify a refusé la connexion. Vérifie l'adresse de retour déclarée dans le dashboard Spotify.",
};
const LOGIN_ERROR_DEFAULT = 'La connexion à Spotify a été interrompue : recommence.';

/** Page « Mes playlists Spotify » : connexion à Spotify, liste des playlists et import. */
@Component({
  selector: 'app-spotify-playlists-page',
  templateUrl: './spotify-playlists.page.html',
  styleUrl: './spotify-playlists.page.scss',
})
export class SpotifyPlaylistsPage {
  private readonly spotify = inject(SpotifyService);
  private readonly auth = inject(AuthService);

  protected readonly loginUrl = SPOTIFY_LOGIN_URL;
  protected readonly state = signal<State>({ kind: 'loading' });
  /** Avancement des imports, par identifiant de playlist Spotify. */
  protected readonly imports = signal<Record<string, ImportState>>({});

  /** Échec de la dernière tentative de connexion, lu dans l'URL de retour. */
  protected readonly loginError: string | null = SpotifyPlaylistsPage.loginErrorFrom(
    inject(ActivatedRoute).snapshot.queryParamMap.get('spotify_error'),
  );

  /** Playlists à afficher, ou null tant qu'elles ne sont pas chargées. */
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

  /** Charge les playlists ; une réponse 401 veut dire « pas connectée ». */
  protected load(): void {
    this.state.set({ kind: 'loading' });
    this.spotify.playlists().subscribe({
      next: (playlists) => this.state.set({ kind: 'ready', playlists }),
      error: (err: HttpErrorResponse) =>
        this.onError(err, 'Impossible de lire tes playlists Spotify.'),
    });
  }

  /** Importe une playlist, puis affiche son bilan sur sa ligne. */
  protected importPlaylist(playlist: SpotifyPlaylist): void {
    this.setImport(playlist.id, { kind: 'importing' });
    this.spotify.importPlaylist(playlist.id).subscribe({
      next: (outcome) => {
        this.setImport(playlist.id, { kind: 'done', outcome });
        this.markImported(playlist.id);
      },
      error: (err: HttpErrorResponse) => {
        if (err.status === 401) {
          this.state.set({ kind: 'disconnected' });
        }
        this.setImport(playlist.id, {
          kind: 'error',
          message: apiErrorMessage(err, "L'import a échoué."),
        });
      },
    });
  }

  /** Ferme la session et revient à l'écran de connexion. */
  protected logout(): void {
    this.auth.logout().subscribe({
      next: () => {
        this.imports.set({});
        this.state.set({ kind: 'disconnected' });
      },
      error: (err: HttpErrorResponse) => this.onError(err, 'Déconnexion impossible.'),
    });
  }

  /** Indique si l'import de cette playlist est en cours. */
  protected isImporting(playlistId: string): boolean {
    return this.imports()[playlistId]?.kind === 'importing';
  }

  /** Bilan du dernier import de cette playlist, ou null. */
  protected outcomeOf(playlistId: string): ImportOutcome | null {
    const s = this.imports()[playlistId];
    return s?.kind === 'done' ? s.outcome : null;
  }

  /** Erreur du dernier import de cette playlist, ou null. */
  protected importErrorOf(playlistId: string): string | null {
    const s = this.imports()[playlistId];
    return s?.kind === 'error' ? s.message : null;
  }

  /** Bascule sur l'écran de connexion (401) ou affiche le message d'erreur. */
  private onError(err: HttpErrorResponse, fallback: string): void {
    this.state.set(
      err.status === 401
        ? { kind: 'disconnected' }
        : { kind: 'error', message: apiErrorMessage(err, fallback) },
    );
  }

  /** Met à jour l'avancement de l'import d'une playlist. */
  private setImport(playlistId: string, importState: ImportState): void {
    this.imports.update((all) => ({ ...all, [playlistId]: importState }));
  }

  /** Note qu'une playlist est désormais importée (le bouton devient « Réimporter »). */
  private markImported(playlistId: string): void {
    this.state.update((s) =>
      s.kind === 'ready'
        ? {
            ...s,
            playlists: s.playlists.map((p) => (p.id === playlistId ? { ...p, imported: true } : p)),
          }
        : s,
    );
  }

  /** Message correspondant au code d'échec de connexion, ou null s'il n'y en a pas. */
  private static loginErrorFrom(code: string | null): string | null {
    return code === null ? null : (LOGIN_ERRORS[code] ?? LOGIN_ERROR_DEFAULT);
  }
}
