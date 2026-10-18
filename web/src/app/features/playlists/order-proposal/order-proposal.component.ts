import { DecimalPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, input, output, signal } from '@angular/core';
import { apiErrorMessage } from '../../../core/api/api-error';
import {
  OrderProposal,
  PlaylistDetail,
  PlaylistItem,
  PlaylistService,
} from '../../../core/api/playlist.service';
import { TransitionView, describeTransition } from '../../../shared/key-moves';

type State =
  | { kind: 'closed' }
  | { kind: 'loading' }
  | { kind: 'ready'; proposal: OrderProposal }
  | { kind: 'error'; message: string };

/** Un morceau de l'ordre proposé, et l'enchaînement vers le suivant (null après le dernier analysé). */
interface ProposedRow {
  item: PlaylistItem;
  next: TransitionView | null;
}

/** Enchaînement refusé dans l'ordre proposé (pas de détail : seuls les compatibles sont calculés). */
const REFUSED: TransitionView = { kind: 'warn', text: '⚠ enchaînement refusé' };

/** « Proposer un ordre » : l'ordre qui enchaîne le mieux (ouverture comprise), en aperçu avant d'appliquer. */
@Component({
  selector: 'app-order-proposal',
  imports: [DecimalPipe],
  templateUrl: './order-proposal.component.html',
  styleUrl: './order-proposal.component.scss',
})
export class OrderProposalComponent {
  private readonly playlists = inject(PlaylistService);

  readonly playlist = input.required<PlaylistDetail>();
  /** Émis après « Appliquer » : la playlist est à recharger. */
  readonly applied = output<void>();

  protected readonly state = signal<State>({ kind: 'closed' });
  /** Vrai pendant l'enregistrement du nouvel ordre. */
  protected readonly applying = signal(false);

  /** Proposition affichée, ou null. */
  protected readonly proposal = computed(() => {
    const s = this.state();
    return s.kind === 'ready' ? s.proposal : null;
  });

  /** Morceaux dans l'ordre proposé, avec l'enchaînement vers le suivant (null après le dernier analysé). */
  protected readonly rows = computed((): ProposedRow[] => {
    const proposal = this.proposal();
    if (proposal === null) {
      return [];
    }
    const byId = new Map(this.playlist().items.map((item) => [item.item_id, item]));
    const rows: ProposedRow[] = [];
    proposal.item_ids.forEach((id, i) => {
      const item = byId.get(id);
      const step = proposal.steps[i];
      if (item !== undefined) {
        const next =
          step === undefined
            ? null
            : step.transition === null
              ? REFUSED
              : describeTransition(step.transition);
        rows.push({ item, next });
      }
    });
    return rows;
  });

  /** Vrai si l'ordre proposé est l'ordre actuel. */
  protected readonly unchanged = computed(() => {
    const proposal = this.proposal();
    const current = this.playlist().items.map((i) => i.item_id);
    return proposal !== null && proposal.item_ids.every((id, i) => id === current[i]);
  });

  /** Message d'erreur, ou null. */
  protected readonly errorMessage = computed(() => {
    const s = this.state();
    return s.kind === 'error' ? s.message : null;
  });

  /** Calcule une proposition (ou referme l'aperçu). */
  protected toggle(): void {
    if (this.state().kind !== 'closed') {
      this.state.set({ kind: 'closed' });
      return;
    }
    this.state.set({ kind: 'loading' });
    this.playlists.proposeOrder(this.playlist().id).subscribe({
      next: (proposal) => this.state.set({ kind: 'ready', proposal }),
      error: (err: HttpErrorResponse) =>
        this.state.set({
          kind: 'error',
          message: apiErrorMessage(err, 'Impossible de proposer un ordre.'),
        }),
    });
  }

  /** Enregistre l'ordre proposé ; 422 = la playlist a changé depuis la proposition. */
  protected apply(proposal: OrderProposal): void {
    this.applying.set(true);
    this.playlists.reorder(this.playlist().id, proposal.item_ids).subscribe({
      next: () => {
        this.applying.set(false);
        this.state.set({ kind: 'closed' });
        this.applied.emit();
      },
      error: (err: HttpErrorResponse) => {
        this.applying.set(false);
        this.state.set({
          kind: 'error',
          message:
            err.status === 422
              ? 'La playlist a changé depuis la proposition : relance-la.'
              : apiErrorMessage(err, "Impossible d'appliquer cet ordre."),
        });
      },
    });
  }
}
