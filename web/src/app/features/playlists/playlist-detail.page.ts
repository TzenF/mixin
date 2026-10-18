import {
  CdkDrag,
  CdkDragDrop,
  CdkDragHandle,
  CdkDropList,
  moveItemInArray,
} from '@angular/cdk/drag-drop';
import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { apiErrorMessage } from '../../core/api/api-error';
import { SPOTIFY_LOGIN_URL } from '../../core/api/auth.service';
import { CatalogTrack } from '../../core/api/catalog.service';
import {
  ExportOutcome,
  PlaylistDetail,
  PlaylistItem,
  PlaylistService,
} from '../../core/api/playlist.service';
import { CurrentPlaylistService } from '../../core/current-playlist.service';
import { FileDownloadService } from '../../core/file-download.service';
import { TrackCorrectionComponent } from '../../shared/track-correction/track-correction.component';
import { PlayButtonComponent } from '../../shared/play-button/play-button.component';
import {
  PlayTransitionButtonComponent,
  TRANSITION_DISCLAIMER,
} from '../../shared/play-transition-button/play-transition-button.component';
import { TransitionRatingComponent } from '../../shared/transition-rating/transition-rating.component';
import { BridgeFinderComponent } from './bridge-finder/bridge-finder.component';
import { FavoriteButtonComponent } from '../../shared/favorite-button/favorite-button.component';
import { describeTransition } from '../../shared/key-moves';
import { PlaylistTextFormat, playlistFileName, playlistText } from '../../shared/playlist-text';

type State =
  | { kind: 'loading' }
  | { kind: 'disconnected' }
  | { kind: 'not_found' }
  | { kind: 'ready'; playlist: PlaylistDetail }
  | { kind: 'error'; message: string };

/** Page « Playlist » : morceaux dans l'ordre et qualité de chaque enchaînement. */
@Component({
  selector: 'app-playlist-detail-page',
  imports: [
    DatePipe,
    DecimalPipe,
    CdkDropList,
    CdkDrag,
    CdkDragHandle,
    FavoriteButtonComponent,
    TrackCorrectionComponent,
    PlayButtonComponent,
    PlayTransitionButtonComponent,
    TransitionRatingComponent,
    BridgeFinderComponent,
  ],
  templateUrl: './playlist-detail.page.html',
  styleUrl: './playlist-detail.page.scss',
})
export class PlaylistDetailPage {
  private readonly service = inject(PlaylistService);
  private readonly router = inject(Router);
  protected readonly currentPlaylist = inject(CurrentPlaylistService);
  private readonly files = inject(FileDownloadService);
  private readonly playlistId = inject(ActivatedRoute).snapshot.paramMap.get('playlistId') ?? '';

  protected readonly loginUrl = SPOTIFY_LOGIN_URL;
  protected readonly disclaimer = TRANSITION_DISCLAIMER;
  protected readonly state = signal<State>({ kind: 'loading' });
  /** Vrai pendant la modification du nom. */
  protected readonly renaming = signal(false);
  /** Vrai pendant l'export vers Spotify. */
  protected readonly exporting = signal(false);
  /** Bilan du dernier export fait depuis cette page, ou null. */
  protected readonly exportOutcome = signal<ExportOutcome | null>(null);
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
      nextTrackId: items[i + 1]?.track.id ?? null,
    }));
  });

  /** Morceaux de la playlist (un pont déjà présent est signalé). */
  protected readonly trackIds = computed(
    () => new Set((this.playlist()?.items ?? []).map((i) => i.track.id)),
  );

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
    this.reload();
  }

  /** Après une correction de BPM ou de tonalité : enchaînements recalculés. */
  protected onCorrected(): void {
    this.reload();
  }

  /** Après l'insertion d'un pont : nouveaux enchaînements, et playlist en cours à jour si c'est elle. */
  protected onBridgeInserted(): void {
    this.reload();
    this.refreshCurrentPlaylist();
  }

  /** Si cette playlist est la playlist en cours, recharge la liste de ses morceaux. */
  private refreshCurrentPlaylist(): void {
    if (this.currentPlaylist.current()?.id === this.playlistId) {
      this.currentPlaylist.select(this.playlistId);
    }
  }

  /** Recharge la playlist sans afficher « Chargement… » (après un déplacement ou un retrait). */
  private reload(): void {
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

  /** Déplace un morceau (glisser-déposer) : affiché tout de suite, enregistré, puis enchaînements recalculés. */
  protected drop(event: CdkDragDrop<PlaylistItem[]>): void {
    const playlist = this.playlist();
    if (playlist === null || event.previousIndex === event.currentIndex) {
      return;
    }
    const items = [...playlist.items];
    moveItemInArray(items, event.previousIndex, event.currentIndex);
    this.state.set({ kind: 'ready', playlist: { ...playlist, items } });
    this.actionError.set(null);
    this.service
      .reorder(
        this.playlistId,
        items.map((i) => i.item_id),
      )
      .subscribe({
        next: () => this.reload(),
        error: (err: HttpErrorResponse) => {
          this.fail(
            err,
            err.status === 422
              ? 'La playlist a changé entre-temps : elle a été rechargée.'
              : "Impossible d'enregistrer le nouvel ordre.",
          );
          this.reload();
        },
      });
  }

  /** Retire un morceau de la playlist. */
  protected removeItem(item: PlaylistItem): void {
    this.actionError.set(null);
    this.service.removeItem(this.playlistId, item.item_id).subscribe({
      next: () => {
        this.reload();
        this.refreshCurrentPlaylist();
      },
      error: (err: HttpErrorResponse) => this.fail(err, 'Impossible de retirer ce morceau.'),
    });
  }

  /** Télécharge la playlist en texte : détaillée (BPM, tonalité, enchaînements) ou simple tracklist. */
  protected downloadText(format: PlaylistTextFormat): void {
    const playlist = this.playlist();
    if (playlist !== null) {
      this.files.saveText(playlistFileName(playlist.name, format), playlistText(playlist, format));
    }
  }

  /** Exporte la playlist vers Spotify, ou met à jour l'export précédent. */
  protected exportToSpotify(): void {
    this.exporting.set(true);
    this.actionError.set(null);
    this.exportOutcome.set(null);
    this.service.exportToSpotify(this.playlistId).subscribe({
      next: (outcome) => {
        this.exporting.set(false);
        this.exportOutcome.set(outcome);
        this.state.update((s) =>
          s.kind === 'ready'
            ? {
                ...s,
                playlist: {
                  ...s.playlist,
                  spotify_export: { url: outcome.url, exported_at: outcome.exported_at },
                },
              }
            : s,
        );
      },
      error: (err: HttpErrorResponse) => {
        this.exporting.set(false);
        // Ici, un 401 vient de Spotify (jeton expiré ou révoqué) : on affiche le message, sans quitter la page.
        this.actionError.set(apiErrorMessage(err, "L'export vers Spotify a échoué."));
      },
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
    } else if (err.status === 422) {
      this.actionError.set(fallback);
    } else {
      this.actionError.set(apiErrorMessage(err, fallback));
    }
  }
}
