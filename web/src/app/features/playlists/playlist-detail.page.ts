import { DecimalPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { apiErrorMessage } from '../../core/api/api-error';
import { SPOTIFY_LOGIN_URL } from '../../core/api/auth.service';
import { CatalogTrack } from '../../core/api/catalog.service';
import { PlaylistDetail, PlaylistService, Transition } from '../../core/api/playlist.service';
import { CurrentPlaylistService } from '../../core/current-playlist.service';
import { KEY_MOVE_LABELS, formatBpmChange } from '../../shared/key-moves';

type State =
  | { kind: 'loading' }
  | { kind: 'disconnected' }
  | { kind: 'not_found' }
  | { kind: 'ready'; playlist: PlaylistDetail }
  | { kind: 'error'; message: string };

/** Enchaînement affiché entre deux morceaux : bon, à vérifier (⚠) ou inconnu (morceau non analysé). */
export interface TransitionView {
  kind: 'ok' | 'warn' | 'unknown';
  text: string;
}

/** Page « Playlist » : morceaux dans l'ordre et qualité de chaque enchaînement. */
@Component({
  selector: 'app-playlist-detail-page',
  imports: [DecimalPipe],
  templateUrl: './playlist-detail.page.html',
  styleUrl: './playlist-detail.page.scss',
})
export class PlaylistDetailPage {
  private readonly service = inject(PlaylistService);
  private readonly router = inject(Router);
  protected readonly currentPlaylist = inject(CurrentPlaylistService);
  private readonly playlistId = inject(ActivatedRoute).snapshot.paramMap.get('playlistId') ?? '';

  protected readonly loginUrl = SPOTIFY_LOGIN_URL;
  protected readonly state = signal<State>({ kind: 'loading' });
  /** Vrai pendant la modification du nom. */
  protected readonly renaming = signal(false);
  /** Échec de la dernière action (renommer, dupliquer, supprimer), ou null. */
  protected readonly actionError = signal<string | null>(null);

  /** Playlist affichée, ou null tant qu'elle n'est pas chargée. */
  protected readonly playlist = computed(() => {
    const s = this.state();
    return s.kind === 'ready' ? s.playlist : null;
  });

  /** Morceaux avec l'enchaînement vers le suivant (null pour le dernier). */
  protected readonly rows = computed(() => {
    const items = this.playlist()?.items ?? [];
    return items.map((item, i) => ({
      item,
      transition: i < items.length - 1 ? describeTransition(item.transition_to_next) : null,
    }));
  });

  /** Nombre d'enchaînements à vérifier (⚠) et inconnus. */
  protected readonly counts = computed(() => {
    const transitions = this.rows().flatMap((r) => (r.transition ? [r.transition] : []));
    return {
      warn: transitions.filter((t) => t.kind === 'warn').length,
      unknown: transitions.filter((t) => t.kind === 'unknown').length,
    };
  });

  /** Message d'erreur de chargement, ou null. */
  protected readonly errorMessage = computed(() => {
    const s = this.state();
    return s.kind === 'error' ? s.message : null;
  });

  constructor() {
    this.load();
    this.currentPlaylist.refresh();
  }

  /** Charge la playlist ; 401 = pas connectée, 404 = pas à moi ou inexistante. */
  protected load(): void {
    this.state.set({ kind: 'loading' });
    this.service.get(this.playlistId).subscribe({
      next: (playlist) => this.state.set({ kind: 'ready', playlist }),
      error: (err: HttpErrorResponse) => {
        if (err.status === 401) {
          this.state.set({ kind: 'disconnected' });
        } else if (err.status === 404) {
          this.state.set({ kind: 'not_found' });
        } else {
          this.state.set({
            kind: 'error',
            message: apiErrorMessage(err, 'Impossible de charger la playlist.'),
          });
        }
      },
    });
  }

  /** Ouvre les suggestions d'enchaînement après ce morceau. */
  protected openSuggestions(track: CatalogTrack): void {
    void this.router.navigate(['/suggestions', track.id], { queryParams: { scope: 'all' } });
  }

  /** Renomme la playlist (playlists créées ici seulement). */
  protected rename(nameInput: HTMLInputElement): void {
    const name = nameInput.value.trim();
    if (name === '') {
      return;
    }
    this.service.rename(this.playlistId, name).subscribe({
      next: (renamed) => {
        this.renaming.set(false);
        this.state.update((s) =>
          s.kind === 'ready' ? { ...s, playlist: { ...s.playlist, name: renamed.name } } : s,
        );
        this.currentPlaylist.refresh();
      },
      error: (err: HttpErrorResponse) => this.fail(err, 'Impossible de renommer la playlist.'),
    });
  }

  /** Fait de cette playlist la playlist en cours. */
  protected makeCurrent(): void {
    this.currentPlaylist.select(this.playlistId);
  }

  /** Duplique la playlist et ouvre la copie (une importée devient ainsi modifiable). */
  protected duplicate(): void {
    this.service.copy(this.playlistId).subscribe({
      next: (copy) => {
        this.currentPlaylist.refresh();
        void this.router.navigate(['/playlists', copy.id]);
      },
      error: (err: HttpErrorResponse) => this.fail(err, 'Impossible de dupliquer la playlist.'),
    });
  }

  /** Supprime la playlist après confirmation, puis revient à la liste. */
  protected remove(playlist: PlaylistDetail): void {
    if (!confirm(`Supprimer « ${playlist.name} » ? Les morceaux restent dans le catalogue.`)) {
      return;
    }
    this.service.delete(this.playlistId).subscribe({
      next: () => {
        this.currentPlaylist.refresh();
        this.backToList();
      },
      error: (err: HttpErrorResponse) => this.fail(err, 'Impossible de supprimer la playlist.'),
    });
  }

  /** Revient à la liste des playlists. */
  protected backToList(): void {
    void this.router.navigate(['/playlists']);
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

/** Texte de l'enchaînement : « → +0,8 % · Tonalité voisine », « ⚠ tempo +8,0 % », « ⚠ tonalité éloignée (5 crans) »… */
export function describeTransition(t: Transition | null): TransitionView {
  if (t === null) {
    return { kind: 'unknown', text: '? Enchaînement inconnu (morceau non analysé)' };
  }
  const tempo = t.half_double ? '½ / ×2 tempo' : formatBpmChange(t.bpm_change);
  if (t.compatible && t.key_move) {
    return { kind: 'ok', text: `→ ${tempo} · ${KEY_MOVE_LABELS[t.key_move]}` };
  }
  const problems = [];
  if (!t.key_move) {
    const steps = `${t.key_distance} cran${t.key_distance > 1 ? 's' : ''}`;
    problems.push(
      t.same_mode
        ? `tonalité éloignée (${steps})`
        : `tonalité incompatible (${steps} et mineur ↔ majeur)`,
    );
  }
  if (!t.tempo_ok) {
    problems.push(`tempo ${formatBpmChange(t.bpm_change)}`);
  }
  return { kind: 'warn', text: `⚠ ${problems.join(' et ')}` };
}
