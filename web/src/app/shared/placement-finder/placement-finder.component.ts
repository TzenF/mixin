import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, input, output, signal } from '@angular/core';
import { apiErrorMessage } from '../../core/api/api-error';
import { CatalogService, Placement } from '../../core/api/catalog.service';
import { Transition } from '../../core/api/playlist.service';
import { CurrentPlaylistService } from '../../core/current-playlist.service';
import { describeTransition } from '../key-moves';

type State =
  | { kind: 'loading' }
  | { kind: 'ready'; placements: Placement[] }
  | { kind: 'error'; message: string };

/** Un côté de la place, affiché : ✓ s'il passe, ⚠ s'il est refusé. */
interface Side {
  ok: boolean;
  text: string;
}

/** Un côté de la place, ou null s'il n'y a pas de voisin (ouverture, fin). */
function side(label: string, neighbour: unknown, transition: Transition | null): Side | null {
  if (neighbour === null) {
    return null;
  }
  return transition === null
    ? { ok: false, text: `⚠ ${label} : refusé` }
    : { ok: true, text: `✓ ${label} : ${describeTransition(transition).text.replace(/^→ /, '')}` };
}

/** « Où le placer ? » : les places de la playlist en cours où ce morceau s'insère, et « Insérer ici ». */
@Component({
  selector: 'app-placement-finder',
  templateUrl: './placement-finder.component.html',
  styleUrl: './placement-finder.component.scss',
})
export class PlacementFinderComponent implements OnInit {
  private readonly catalog = inject(CatalogService);
  private readonly currentPlaylist = inject(CurrentPlaylistService);

  readonly trackId = input.required<string>();
  /** Émis après l'insertion : la liste est à recharger (les liens avec la playlist ont changé). */
  readonly inserted = output<void>();

  protected readonly state = signal<State>({ kind: 'loading' });
  /** Vrai pendant l'insertion. */
  protected readonly inserting = signal(false);

  /** Places affichées : où, et l'état de chaque côté. */
  protected readonly rows = computed(() => {
    const s = this.state();
    if (s.kind !== 'ready') {
      return [];
    }
    return s.placements.map((p) => ({
      placement: p,
      where:
        p.before === null && p.after !== null
          ? `En ouverture, avant ${p.after.place}. ${p.after.title}`
          : p.after === null && p.before !== null
            ? `En fin, après ${p.before.place}. ${p.before.title}`
            : `Entre ${p.before?.place}. ${p.before?.title} et ${p.after?.place}. ${p.after?.title}`,
      sides: [side('avant', p.before, p.incoming), side('après', p.after, p.outgoing)].filter(
        (s): s is Side => s !== null,
      ),
    }));
  });

  /** Message d'erreur, ou null. */
  protected readonly errorMessage = computed(() => {
    const s = this.state();
    return s.kind === 'error' ? s.message : null;
  });

  /** Cherche les places dans la playlist en cours. */
  ngOnInit(): void {
    const current = this.currentPlaylist.current();
    if (current === null) {
      this.state.set({ kind: 'error', message: 'Choisis une playlist en cours.' });
      return;
    }
    this.catalog.placements(this.trackId(), current.id).subscribe({
      next: (placements) => this.state.set({ kind: 'ready', placements }),
      error: (err: HttpErrorResponse) =>
        this.state.set({
          kind: 'error',
          message: apiErrorMessage(err, 'Impossible de chercher où le placer.'),
        }),
    });
  }

  /** Insère le morceau à cette place dans la playlist en cours. */
  protected insert(placement: Placement): void {
    this.inserting.set(true);
    this.currentPlaylist.add(this.trackId(), placement.position).subscribe({
      next: () => {
        this.inserting.set(false);
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
}
