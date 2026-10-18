import { computed, signal } from '@angular/core';
import { Observable, of } from 'rxjs';
import { AddedItem, PlaylistSummary } from './api/playlist.service';

/** Playlist modifiable d'exemple pour les tests. */
export const FAKE_PLAYLIST: PlaylistSummary = {
  id: 'current',
  name: 'Set en cours',
  source_provider: null,
  track_count: 0,
  updated_at: '2026-10-16T14:00:00Z',
  slot_minutes: null,
  played_percent: 100,
};

/**
 * Faux CurrentPlaylistService pour les tests des pages : aucune requête HTTP.
 *
 * Usage : `{ provide: CurrentPlaylistService, useValue: new FakeCurrentPlaylistService() }`.
 */
export class FakeCurrentPlaylistService {
  readonly editable = signal<PlaylistSummary[] | null>([FAKE_PLAYLIST]);
  readonly trackIds = signal<ReadonlySet<string>>(new Set());
  private readonly selectedId = signal<string | null>(null);
  /** Morceaux ajoutés, dans l'ordre (à vérifier dans les tests). */
  readonly added: string[] = [];
  /** Position demandée pour chaque ajout (undefined : en fin). */
  readonly positions: (number | undefined)[] = [];
  /** Nombre d'appels à refresh(). */
  refreshCount = 0;

  /** La playlist en cours, comme le vrai service. */
  readonly current = computed(
    () => this.editable()?.find((p) => p.id === this.selectedId()) ?? null,
  );

  /** Compte les rechargements demandés. */
  refresh(): void {
    this.refreshCount += 1;
  }

  /** Change la playlist en cours. */
  select(playlistId: string | null): void {
    this.selectedId.set(playlistId);
  }

  /** Crée une playlist (sans requête) et la choisit. */
  create(name: string): Observable<PlaylistSummary> {
    const created = { ...FAKE_PLAYLIST, id: `new-${name}`, name };
    this.editable.update((list) => [created, ...(list ?? [])]);
    this.select(created.id);
    return of(created);
  }

  /** Ajoute un morceau (sans requête), en fin ou à `position`. */
  add(trackId: string, position?: number): Observable<AddedItem> {
    this.added.push(trackId);
    this.positions.push(position);
    this.trackIds.update((ids) => new Set(ids).add(trackId));
    return of({ item_id: this.added.length, position: this.added.length - 1 });
  }
}
