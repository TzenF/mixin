import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, input, output, signal } from '@angular/core';
import { apiErrorMessage } from '../../../core/api/api-error';
import { CutProposal, PlaylistDetail, PlaylistService } from '../../../core/api/playlist.service';
import { formatDuration, playedDuration } from '../../../shared/duration';

type CutState =
  | { kind: 'closed' }
  | { kind: 'loading' }
  | { kind: 'ready'; proposal: CutProposal }
  | { kind: 'error'; message: string };

/** Durée du set, créneau et part jouée ; si ça dépasse, « Proposer quoi retirer » puis « Appliquer ». */
@Component({
  selector: 'app-set-duration',
  templateUrl: './set-duration.component.html',
  styleUrl: './set-duration.component.scss',
})
export class SetDurationComponent {
  private readonly playlists = inject(PlaylistService);

  readonly playlist = input.required<PlaylistDetail>();
  /** Émis quand le créneau, la part jouée ou les morceaux ont changé : la page recharge la playlist. */
  readonly changed = output<void>();

  protected readonly format = formatDuration;
  protected readonly cut = signal<CutState>({ kind: 'closed' });
  /** Vrai pendant un enregistrement (réglages ou retrait). */
  protected readonly saving = signal(false);
  /** Échec du dernier enregistrement, ou null. */
  protected readonly saveError = signal<string | null>(null);

  /** Durée comptée du set (morceaux réduits à la part jouée). */
  protected readonly total = computed(() => {
    const p = this.playlist();
    return p.items.reduce(
      (sum, i) => sum + playedDuration(i.track.duration_ms, p.played_percent),
      0,
    );
  });

  /** Comparaison avec le créneau (de trop, ou ce qu'il reste), ou null sans créneau. */
  protected readonly slotStatus = computed(() => {
    const slot = this.playlist().slot_minutes;
    if (slot === null) {
      return null;
    }
    const diff = this.total() - slot * 60_000;
    return { over: diff > 0, diff: Math.abs(diff), slotMs: slot * 60_000 };
  });

  /** Titres des morceaux proposés au retrait, avec leur place. */
  protected readonly toRemove = computed(() => {
    const s = this.cut();
    if (s.kind !== 'ready') {
      return [];
    }
    const ids = new Set(s.proposal.remove_item_ids);
    return this.playlist()
      .items.filter((i) => ids.has(i.item_id))
      .map((i) => ({ place: i.position + 1, title: i.track.title }));
  });

  /** Proposition affichée, ou null. */
  protected readonly proposal = computed(() => {
    const s = this.cut();
    return s.kind === 'ready' ? s.proposal : null;
  });

  /** Message d'erreur de la proposition, ou null. */
  protected readonly cutError = computed(() => {
    const s = this.cut();
    return s.kind === 'error' ? s.message : null;
  });

  /** Enregistre le créneau (vide = aucun) et la part jouée. */
  protected save(slotInput: HTMLInputElement, percentInput: HTMLInputElement): void {
    const slot = slotInput.value.trim() === '' ? null : Number(slotInput.value);
    const percent = Number(percentInput.value);
    const slotOk = slot === null || (Number.isInteger(slot) && slot >= 1 && slot <= 1440);
    if (!slotOk || !(percent >= 50 && percent <= 100)) {
      this.saveError.set('Créneau : 1 à 1440 min (vide = aucun). Part jouée : 50 à 100 %.');
      return;
    }
    this.saving.set(true);
    this.saveError.set(null);
    this.cut.set({ kind: 'closed' });
    this.playlists
      .updateSettings(this.playlist().id, {
        slot_minutes: slot,
        played_percent: Math.round(percent),
      })
      .subscribe({
        next: () => {
          this.saving.set(false);
          this.changed.emit();
        },
        error: (err: HttpErrorResponse) => {
          this.saving.set(false);
          this.saveError.set(apiErrorMessage(err, "Impossible d'enregistrer le créneau."));
        },
      });
  }

  /** Demande quels morceaux retirer (ou referme la proposition). */
  protected toggleCut(): void {
    if (this.cut().kind !== 'closed') {
      this.cut.set({ kind: 'closed' });
      return;
    }
    this.cut.set({ kind: 'loading' });
    this.playlists.proposeCut(this.playlist().id).subscribe({
      next: (proposal) => this.cut.set({ kind: 'ready', proposal }),
      error: (err: HttpErrorResponse) =>
        this.cut.set({
          kind: 'error',
          message: apiErrorMessage(err, 'Impossible de proposer une coupe.'),
        }),
    });
  }

  /** Retire les morceaux proposés (tout ou rien). */
  protected apply(proposal: CutProposal): void {
    this.saving.set(true);
    this.playlists.removeItems(this.playlist().id, proposal.remove_item_ids).subscribe({
      next: () => {
        this.saving.set(false);
        this.cut.set({ kind: 'closed' });
        this.changed.emit();
      },
      error: (err: HttpErrorResponse) => {
        this.saving.set(false);
        this.cut.set({
          kind: 'error',
          message:
            err.status === 404
              ? 'La playlist a changé depuis la proposition : relance-la.'
              : apiErrorMessage(err, 'Impossible de retirer ces morceaux.'),
        });
      },
    });
  }
}
