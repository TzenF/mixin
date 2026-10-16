import { HttpErrorResponse } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Observable, tap, throwError } from 'rxjs';
import { AddedItem, PlaylistService, PlaylistSummary } from './api/playlist.service';

/** Clé du navigateur où l'on retient la playlist en cours entre deux visites. */
export const CURRENT_PLAYLIST_KEY = 'currentPlaylistId';

/**
 * La playlist « en cours » : celle que remplissent les boutons « + Ajouter » (catalogue, suggestions).
 *
 * Seules mes playlists créées ici peuvent l'être (une importée est en lecture seule).
 */
@Injectable({ providedIn: 'root' })
export class CurrentPlaylistService {
  private readonly playlists = inject(PlaylistService);

  private readonly selectedId = signal<string | null>(readStoredId());
  /** Mes playlists modifiables, ou null tant qu'elles ne sont pas chargées. */
  readonly editable = signal<PlaylistSummary[] | null>(null);
  /** Morceaux déjà dans la playlist en cours (pour afficher « ✓ Ajouté »). */
  readonly trackIds = signal<ReadonlySet<string>>(new Set());

  /** La playlist en cours, ou null s'il n'y en a pas (ou pas encore chargée). */
  readonly current = computed(() => {
    const id = this.selectedId();
    return this.editable()?.find((p) => p.id === id) ?? null;
  });

  /** Recharge mes playlists modifiables ; oublie la playlist en cours si elle n'existe plus. */
  refresh(): void {
    this.playlists.list().subscribe({
      next: (all) => {
        const editable = all.filter((p) => p.source_provider === null);
        this.editable.set(editable);
        const id = this.selectedId();
        if (id !== null && !editable.some((p) => p.id === id)) {
          this.select(null);
        } else if (id !== null && this.trackIds().size === 0) {
          this.loadTrackIds(id);
        }
      },
      // 401 ou panne : on garde le choix en mémoire, la liste reste vide
      error: () => this.editable.set([]),
    });
  }

  /** Choisit la playlist en cours (null : aucune), et la retient dans le navigateur. */
  select(playlistId: string | null): void {
    this.selectedId.set(playlistId);
    writeStoredId(playlistId);
    this.trackIds.set(new Set());
    if (playlistId !== null) {
      this.loadTrackIds(playlistId);
    }
  }

  /** Crée une playlist et en fait la playlist en cours. */
  create(name: string): Observable<PlaylistSummary> {
    return this.playlists.create(name).pipe(
      tap((created) => {
        this.editable.update((list) => [created, ...(list ?? [])]);
        this.select(created.id);
      }),
    );
  }

  /** Ajoute un morceau à la playlist en cours. */
  add(trackId: string): Observable<AddedItem> {
    const current = this.current();
    if (current === null) {
      return throwError(() => new Error('Aucune playlist en cours'));
    }
    return this.playlists.addTrack(current.id, trackId).pipe(
      tap(() => {
        this.trackIds.update((ids) => new Set(ids).add(trackId));
        this.editable.update(
          (list) =>
            list?.map((p) =>
              p.id === current.id ? { ...p, track_count: p.track_count + 1 } : p,
            ) ?? null,
        );
      }),
    );
  }

  /** Charge les morceaux de la playlist en cours. */
  private loadTrackIds(playlistId: string): void {
    this.playlists.get(playlistId).subscribe({
      next: (playlist) => {
        if (this.selectedId() === playlistId) {
          this.trackIds.set(new Set(playlist.items.map((i) => i.track.id)));
        }
      },
      error: (err: HttpErrorResponse) => {
        if (err.status === 404 && this.selectedId() === playlistId) {
          this.select(null);
        }
      },
    });
  }
}

/** Identifiant retenu dans le navigateur, ou null (stockage vide, bloqué ou indisponible). */
function readStoredId(): string | null {
  try {
    return localStorage.getItem(CURRENT_PLAYLIST_KEY);
  } catch {
    return null;
  }
}

/** Retient l'identifiant dans le navigateur (sans effet si le stockage est indisponible). */
function writeStoredId(playlistId: string | null): void {
  try {
    if (playlistId === null) {
      localStorage.removeItem(CURRENT_PLAYLIST_KEY);
    } else {
      localStorage.setItem(CURRENT_PLAYLIST_KEY, playlistId);
    }
  } catch {
    // Navigation privée ou stockage bloqué : le choix ne durera que le temps de la page.
  }
}
