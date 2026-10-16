import { DecimalPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router } from '@angular/router';
import { Subscription, forkJoin } from 'rxjs';
import { apiErrorMessage } from '../../core/api/api-error';
import { SPOTIFY_LOGIN_URL } from '../../core/api/auth.service';
import {
  CatalogService,
  CatalogTrack,
  KeyMove,
  Suggestion,
  SuggestionOptions,
} from '../../core/api/catalog.service';

/** Écarts de BPM proposés (fractions) ; 0.06 = ±6 %, la valeur par défaut de l'API. */
export const TOLERANCES = [0.02, 0.04, 0.06, 0.08, 0.1, 0.12] as const;
const DEFAULT_TOLERANCE = 0.06;

const MOVE_LABELS: Record<KeyMove, string> = {
  same: 'Même tonalité',
  adjacent: 'Tonalité voisine',
  relative: 'Relative (mineur ↔ majeur)',
  energy_shift: "Saut de 2 (montée d'énergie)",
};

type State =
  | { kind: 'loading' }
  | { kind: 'disconnected' }
  | { kind: 'not_found' }
  | { kind: 'ready'; seed: CatalogTrack; suggestions: Suggestion[] }
  | { kind: 'error'; message: string };

/** Page « Suggestions » : les morceaux qui s'enchaînent bien après un morceau ; un clic enchaîne. */
@Component({
  selector: 'app-suggestions-page',
  imports: [DecimalPipe],
  templateUrl: './suggestions.page.html',
  styleUrl: './suggestions.page.scss',
})
export class SuggestionsPage {
  private readonly catalog = inject(CatalogService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  protected readonly loginUrl = SPOTIFY_LOGIN_URL;
  protected readonly tolerances = TOLERANCES;
  protected readonly moveLabels = MOVE_LABELS;

  /** Morceau de départ (dans l'URL : /suggestions/:trackId). */
  private trackId = '';
  /** Réglages ; lus dans l'URL au chargement, recopiés dedans à chaque changement. */
  protected readonly options = signal<SuggestionOptions>(optionsFromUrl(this.route));
  protected readonly state = signal<State>({ kind: 'loading' });
  /** Vrai pendant l'inversion de la tonalité du morceau de départ. */
  protected readonly flipping = signal(false);

  private request: Subscription | undefined;

  /** Morceau de départ, ou null tant qu'il n'est pas chargé. */
  protected readonly seed = computed(() => {
    const s = this.state();
    return s.kind === 'ready' ? s.seed : null;
  });

  /** Suggestions, ou null tant qu'elles ne sont pas chargées. */
  protected readonly suggestions = computed(() => {
    const s = this.state();
    return s.kind === 'ready' ? s.suggestions : null;
  });

  /** Message d'erreur de chargement, ou null. */
  protected readonly errorMessage = computed(() => {
    const s = this.state();
    return s.kind === 'error' ? s.message : null;
  });

  constructor() {
    inject(DestroyRef).onDestroy(() => this.request?.unsubscribe());
    // Le composant est réutilisé quand on enchaîne vers un autre morceau : on suit l'identifiant de l'URL.
    this.route.paramMap.pipe(takeUntilDestroyed()).subscribe((params) => {
      this.trackId = params.get('trackId') ?? '';
      this.load();
    });
  }

  /** Charge le morceau de départ et ses suggestions ; une réponse devenue inutile est abandonnée. */
  protected load(): void {
    this.request?.unsubscribe();
    this.state.set({ kind: 'loading' });
    this.request = forkJoin({
      seed: this.catalog.track(this.trackId),
      suggestions: this.catalog.suggestions(this.trackId, this.options()),
    }).subscribe({
      next: ({ seed, suggestions }) => this.state.set({ kind: 'ready', seed, suggestions }),
      error: (err: HttpErrorResponse) => this.state.set(stateForError(err)),
    });
  }

  /** Bascule entre mes morceaux et tous les morceaux de la base. */
  protected setShowAll(all: boolean): void {
    this.changeOptions({ scope: all ? 'all' : 'mine' });
  }

  /** Change l'écart de BPM accepté. */
  protected setTolerance(value: string): void {
    const tolerance = Number(value);
    this.changeOptions({
      bpmTolerance: isTolerance(tolerance) ? tolerance : DEFAULT_TOLERANCE,
    });
  }

  /** Enchaîne : le morceau choisi devient le nouveau point de départ (le retour arrière remonte la chaîne). */
  protected chain(suggestion: Suggestion): void {
    void this.router.navigate(['/suggestions', suggestion.track_id], {
      queryParamsHandling: 'preserve',
    });
  }

  /** Inverse majeur/mineur de la tonalité du morceau de départ, puis recalcule les suggestions. */
  protected flipSeedMode(): void {
    this.flipping.set(true);
    this.catalog.flipMode(this.trackId).subscribe({
      next: () => {
        this.flipping.set(false);
        this.load();
      },
      error: (err: HttpErrorResponse) => {
        this.flipping.set(false);
        this.state.set(stateForError(err));
      },
    });
  }

  /** Revient au catalogue. */
  protected backToCatalog(): void {
    void this.router.navigate(['/catalog']);
  }

  /** Pourcentage affiché pour un écart de BPM (0.06 -> 6). */
  protected percent(tolerance: number): number {
    return Math.round(tolerance * 100);
  }

  /** État d'une case à cocher à partir de son événement. */
  protected checkedOf(event: Event): boolean {
    return (event.target as HTMLInputElement).checked;
  }

  /** Valeur d'une liste déroulante à partir de son événement. */
  protected valueOf(event: Event): string {
    return (event.target as HTMLSelectElement).value;
  }

  /** Applique un changement de réglage : recopié dans l'URL, puis rechargement. */
  private changeOptions(change: Partial<SuggestionOptions>): void {
    this.options.update((o) => ({ ...o, ...change }));
    const { scope, bpmTolerance } = this.options();
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: {
        scope: scope === 'all' ? 'all' : null,
        tolerance: bpmTolerance === DEFAULT_TOLERANCE ? null : bpmTolerance,
      },
      replaceUrl: true,
    });
    this.load();
  }
}

/** Réglages lus dans l'URL ; une valeur absente ou invalide prend sa valeur par défaut. */
function optionsFromUrl(route: ActivatedRoute): SuggestionOptions {
  const params = route.snapshot.queryParamMap;
  const tolerance = Number(params.get('tolerance'));
  return {
    scope: params.get('scope') === 'all' ? 'all' : 'mine',
    bpmTolerance: isTolerance(tolerance) ? tolerance : DEFAULT_TOLERANCE,
  };
}

/** Indique si la valeur fait partie des écarts proposés. */
function isTolerance(value: number): boolean {
  return (TOLERANCES as readonly number[]).includes(value);
}

/** État à afficher pour une erreur d'API : 401 = pas connecté, 404 = morceau inconnu. */
function stateForError(err: HttpErrorResponse): State {
  if (err.status === 401) {
    return { kind: 'disconnected' };
  }
  if (err.status === 404) {
    return { kind: 'not_found' };
  }
  return { kind: 'error', message: apiErrorMessage(err, 'Impossible de charger les suggestions.') };
}
