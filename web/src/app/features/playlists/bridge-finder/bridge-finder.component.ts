import { DecimalPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, input, output, signal } from '@angular/core';
import { apiErrorMessage } from '../../../core/api/api-error';
import { Bridge, CatalogService } from '../../../core/api/catalog.service';
import { PlaylistService } from '../../../core/api/playlist.service';
import { describeTransition } from '../../../shared/key-moves';
import { PlayButtonComponent } from '../../../shared/play-button/play-button.component';

type State =
  | { kind: 'closed' }
  | { kind: 'loading' }
  | { kind: 'ready'; bridges: Bridge[] }
  | { kind: 'error'; message: string };

/** « Trouver un pont » : sur un enchaînement refusé A → B, propose des morceaux à insérer entre les deux. */
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
    this.playlists.addTrack(this.playlistId(), bridge.track_id, this.position()).subscribe({
      next: () => {
        this.inserting.set(false);
        this.state.set({ kind: 'closed' });
        this.inserted.emit();
      },
      error: (err: HttpErrorResponse) => {
        this.inserting.set(false);
        this.state.set({
          kind: 'error',
          message: apiErrorMessage(err, "Impossible d'insérer ce morceau."),
        });
      },
    });
  }

  /** Charge les meilleurs ponts. */
  private search(): void {
    this.state.set({ kind: 'loading' });
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
