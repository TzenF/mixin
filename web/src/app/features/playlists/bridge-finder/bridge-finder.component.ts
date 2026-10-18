import { DecimalPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, input, output, signal } from '@angular/core';
import { apiErrorMessage } from '../../../core/api/api-error';
import { Bridge, CatalogService, SetPath } from '../../../core/api/catalog.service';
import { PlaylistService } from '../../../core/api/playlist.service';
import { describeTransition } from '../../../shared/key-moves';
import { PlayButtonComponent } from '../../../shared/play-button/play-button.component';

type State =
  | { kind: 'closed' }
  | { kind: 'loading' }
  | { kind: 'ready'; bridges: Bridge[] }
  | { kind: 'error'; message: string };

type PathState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ready'; paths: SetPath[] }
  | { kind: 'error'; message: string };

/** « Trouver un pont » : sur un enchaînement refusé A → B, propose un morceau (ou un chemin) à insérer entre les deux. */
@Component({
  selector: 'app-bridge-finder',
  imports: [DecimalPipe, PlayButtonComponent],
  templateUrl: './bridge-finder.component.html',
  styleUrl: './bridge-finder.component.scss',
})
export class BridgeFinderComponent {
  private readonly catalog = inject(CatalogService);
  private readonly playlists = inject(PlaylistService);

  readonly playlistId = input.required<string>();
  readonly fromId = input.required<string>();
  readonly toId = input.required<string>();
  /** Place du morceau B dans la playlist : le pont y est inséré, B descend d'une place. */
  readonly position = input.required<number>();
  /** Morceaux déjà dans la playlist (signalés, pas cachés). */
  readonly playlistTrackIds = input<ReadonlySet<string>>(new Set());
  /** Émis après l'insertion d'un pont : la playlist est à recharger. */
  readonly inserted = output<void>();

  protected readonly state = signal<State>({ kind: 'closed' });
  /** Chemins de plusieurs morceaux, cherchés seulement quand aucun pont n'existe. */
  protected readonly pathState = signal<PathState>({ kind: 'idle' });
  /** Chercher aussi hors de « mes morceaux » (Explorer compris). */
  protected readonly everywhere = signal(false);
  /** Vrai pendant l'insertion. */
  protected readonly inserting = signal(false);

  /** Ponts affichés, avec le texte de leurs deux enchaînements. */
  protected readonly rows = computed(() => {
    const s = this.state();
    return s.kind === 'ready'
      ? s.bridges.map((bridge) => ({
          bridge,
          incoming: describeTransition(bridge.incoming).text,
          outgoing: describeTransition(bridge.outgoing).text,
          inPlaylist: this.playlistTrackIds().has(bridge.track_id),
        }))
      : [];
  });

  /** Chemins affichés : morceaux (signalés s'ils sont déjà dans la playlist) et texte de chaque enchaînement. */
  protected readonly pathRows = computed(() => {
    const s = this.pathState();
    return s.kind === 'ready'
      ? s.paths.map((path) => ({
          path,
          tracks: path.tracks.map((track) => ({
            track,
            inPlaylist: this.playlistTrackIds().has(track.id),
          })),
          steps: path.steps.map((step) => describeTransition(step.transition).text),
        }))
      : [];
  });

  /** Message d'erreur de la recherche de chemin, ou null. */
  protected readonly pathError = computed(() => {
    const s = this.pathState();
    return s.kind === 'error' ? s.message : null;
  });

  /** Message d'erreur, ou null. */
  protected readonly errorMessage = computed(() => {
    const s = this.state();
    return s.kind === 'error' ? s.message : null;
  });

  /** Ouvre la liste des ponts (ou la referme). */
  protected toggle(): void {
    if (this.state().kind === 'closed') {
      this.search();
    } else {
      this.state.set({ kind: 'closed' });
    }
  }

  /** Cherche aussi dans tout le catalogue, ou seulement dans mes morceaux. */
  protected setEverywhere(value: boolean): void {
    this.everywhere.set(value);
    this.search();
  }

  /** Insère le pont entre A et B. */
  protected insert(bridge: Bridge): void {
    this.inserting.set(true);
    this.playlists
      .addTrack(this.playlistId(), bridge.track_id, this.position())
      .subscribe({ next: () => this.done(), error: (err: HttpErrorResponse) => this.failed(err) });
  }

  /** Insère tous les morceaux du chemin entre A et B. */
  protected insertPath(path: SetPath): void {
    this.inserting.set(true);
    this.playlists
      .insertTracks(
        this.playlistId(),
        path.tracks.map((t) => t.id),
        this.position(),
      )
      .subscribe({ next: () => this.done(), error: (err: HttpErrorResponse) => this.failed(err) });
  }

  /** Cherche des chemins de plusieurs morceaux (même portée que les ponts). */
  protected searchPaths(): void {
    this.pathState.set({ kind: 'loading' });
    this.catalog.paths(this.fromId(), this.toId(), this.everywhere() ? 'all' : 'mine').subscribe({
      next: (paths) => this.pathState.set({ kind: 'ready', paths }),
      error: (err: HttpErrorResponse) =>
        this.pathState.set({
          kind: 'error',
          message: apiErrorMessage(err, 'Impossible de chercher un chemin.'),
        }),
    });
  }

  /** Après une insertion réussie : tout se referme et la page recharge la playlist. */
  private done(): void {
    this.inserting.set(false);
    this.state.set({ kind: 'closed' });
    this.pathState.set({ kind: 'idle' });
    this.inserted.emit();
  }

  /** Après un échec d'insertion. */
  private failed(err: HttpErrorResponse): void {
    this.inserting.set(false);
    this.state.set({
      kind: 'error',
      message: apiErrorMessage(err, "Impossible d'insérer ce morceau."),
    });
  }

  /** Charge les meilleurs ponts. */
  private search(): void {
    this.state.set({ kind: 'loading' });
    this.pathState.set({ kind: 'idle' });
    this.catalog.bridges(this.fromId(), this.toId(), this.everywhere() ? 'all' : 'mine').subscribe({
      next: (bridges) => this.state.set({ kind: 'ready', bridges }),
      error: (err: HttpErrorResponse) =>
        this.state.set({
          kind: 'error',
          message: apiErrorMessage(err, 'Impossible de chercher un pont.'),
        }),
    });
  }
}
