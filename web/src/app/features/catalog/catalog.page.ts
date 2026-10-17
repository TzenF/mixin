import { DecimalPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, ParamMap, Params, Router } from '@angular/router';
import { Subscription } from 'rxjs';
import { apiErrorMessage } from '../../core/api/api-error';
import { SPOTIFY_LOGIN_URL } from '../../core/api/auth.service';
import {
  AnalysisStatus,
  CatalogPage as Page,
  CatalogQuery,
  CatalogService,
  CatalogSort,
  CatalogTrack,
} from '../../core/api/catalog.service';
import { AddToPlaylistComponent } from '../../shared/add-to-playlist/add-to-playlist.component';
import { TrackCorrectionComponent } from '../../shared/track-correction/track-correction.component';
import { PlayButtonComponent } from '../../shared/play-button/play-button.component';
import { FavoriteButtonComponent } from '../../shared/favorite-button/favorite-button.component';
import { CurrentPlaylistBarComponent } from '../../shared/current-playlist-bar/current-playlist-bar.component';

const PAGE_SIZE = 50;
/** Délai entre la dernière frappe dans la recherche et l'appel à l'API. */
export const SEARCH_DELAY_MS = 300;

const STATUS_LABELS: Record<AnalysisStatus, string> = {
  pending: 'En attente',
  done: 'Analysé',
  no_preview: "Pas d'extrait",
  failed: 'Échec',
};
const STATUSES = Object.keys(STATUS_LABELS) as AnalysisStatus[];
const SORTS: readonly CatalogSort[] = ['title', 'bpm', 'key'];

type State =
  | { kind: 'loading' }
  | { kind: 'disconnected' }
  | { kind: 'ready'; page: Page }
  | { kind: 'error'; message: string };

/** Page « Catalogue » : mes morceaux (ou tous), filtrés et triés, avec BPM et tonalité. */
@Component({
  selector: 'app-catalog-page',
  imports: [
    DecimalPipe,
    AddToPlaylistComponent,
    CurrentPlaylistBarComponent,
    FavoriteButtonComponent,
    TrackCorrectionComponent,
    PlayButtonComponent,
  ],
  templateUrl: './catalog.page.html',
  styleUrl: './catalog.page.scss',
})
export class CatalogPage {
  private readonly catalog = inject(CatalogService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  protected readonly loginUrl = SPOTIFY_LOGIN_URL;
  protected readonly statuses = STATUSES;
  protected readonly statusLabels = STATUS_LABELS;

  /** Filtres, tri et page en cours ; lus dans l'URL au chargement, recopiés dedans à chaque changement. */
  protected readonly query = signal<CatalogQuery>(queryFromUrl(this.route.snapshot.queryParamMap));
  protected readonly state = signal<State>({ kind: 'loading' });
  /** Morceau dont la tonalité est en cours d'inversion, ou null. */
  protected readonly flipping = signal<string | null>(null);
  /** Échec de la dernière correction de tonalité, ou null. */
  protected readonly correctionError = signal<string | null>(null);

  private request: Subscription | undefined;
  private searchTimer: ReturnType<typeof setTimeout> | undefined;

  /** Page affichée, ou null tant qu'elle n'est pas chargée. */
  protected readonly page = computed(() => {
    const s = this.state();
    return s.kind === 'ready' ? s.page : null;
  });

  /** Message d'erreur de chargement, ou null. */
  protected readonly errorMessage = computed(() => {
    const s = this.state();
    return s.kind === 'error' ? s.message : null;
  });

  /** Morceaux affichés (« 1–50 sur 312 »), ou null s'il n'y en a aucun. */
  protected readonly range = computed(() => {
    const page = this.page();
    if (!page || page.items.length === 0) {
      return null;
    }
    const from = this.query().offset + 1;
    return { from, to: from + page.items.length - 1, total: page.total };
  });

  /** Indique s'il existe une page précédente. */
  protected readonly hasPrevious = computed(() => this.query().offset > 0);

  /** Indique s'il existe une page suivante. */
  protected readonly hasNext = computed(() => {
    const page = this.page();
    return page !== null && this.query().offset + PAGE_SIZE < page.total;
  });

  constructor() {
    inject(DestroyRef).onDestroy(() => {
      clearTimeout(this.searchTimer);
      this.request?.unsubscribe();
    });
    this.load();
  }

  /** Charge la page demandée ; une réponse plus ancienne encore en route est abandonnée. */
  protected load(): void {
    this.request?.unsubscribe();
    this.state.set({ kind: 'loading' });
    this.request = this.catalog.tracks(this.query()).subscribe({
      next: (page) => this.state.set({ kind: 'ready', page }),
      error: (err: HttpErrorResponse) =>
        this.state.set(
          err.status === 401
            ? { kind: 'disconnected' }
            : {
                kind: 'error',
                message: apiErrorMessage(err, 'Impossible de charger le catalogue.'),
              },
        ),
    });
  }

  /** N'affiche que mes favoris (ou tout). */
  protected setFavoritesOnly(favoritesOnly: boolean): void {
    this.applyFilters({ favoritesOnly });
  }

  /** Bascule entre mes morceaux et tous les morceaux de la base. */
  protected setShowAll(all: boolean): void {
    this.applyFilters({ scope: all ? 'all' : 'mine' });
  }

  /** Recherche par titre ou artiste, lancée quand la frappe s'arrête. */
  protected search(text: string): void {
    clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => this.applyFilters({ q: text }), SEARCH_DELAY_MS);
  }

  /** Change le BPM minimum (vide = pas de minimum). */
  protected setBpmMin(value: string): void {
    this.applyFilters({ bpmMin: toNumber(value) });
  }

  /** Change le BPM maximum (vide = pas de maximum). */
  protected setBpmMax(value: string): void {
    this.applyFilters({ bpmMax: toNumber(value) });
  }

  /** Change la tonalité filtrée (8A, Am…) ; l'API refuse une tonalité inconnue. */
  protected setKey(value: string): void {
    this.applyFilters({ key: value });
  }

  /** Change le statut d'analyse filtré (vide = tous). */
  protected setStatus(value: string): void {
    this.applyFilters({ status: isStatus(value) ? value : '' });
  }

  /** Change l'ordre du catalogue. */
  protected setSort(value: string): void {
    this.applyFilters({ sort: isSort(value) ? value : 'title' });
  }

  /** Affiche la page précédente. */
  protected previous(): void {
    this.goTo(Math.max(this.query().offset - PAGE_SIZE, 0));
  }

  /** Affiche la page suivante. */
  protected next(): void {
    this.goTo(this.query().offset + PAGE_SIZE);
  }

  /** Inverse majeur/mineur de la tonalité du morceau (correction perso), puis met sa ligne à jour. */
  protected flipMode(track: CatalogTrack): void {
    this.flipping.set(track.id);
    this.correctionError.set(null);
    this.catalog.flipMode(track.id).subscribe({
      next: ({ camelot, key_source }) => {
        this.flipping.set(null);
        this.updateTrack(track.id, { camelot, key_source, key_confidence: 1 });
      },
      error: (err: HttpErrorResponse) => {
        this.flipping.set(null);
        if (err.status === 401) {
          this.state.set({ kind: 'disconnected' });
        } else {
          this.correctionError.set(apiErrorMessage(err, 'La correction a échoué.'));
        }
      },
    });
  }

  /** Ouvre les suggestions d'enchaînement après ce morceau (en gardant « tous les morceaux » si coché). */
  protected openSuggestions(track: CatalogTrack): void {
    const scope = this.query().scope === 'all' ? 'all' : null;
    void this.router.navigate(['/suggestions', track.id], { queryParams: { scope } });
  }

  /** Valeur d'un champ de formulaire à partir de son événement. */
  protected valueOf(event: Event): string {
    return (event.target as HTMLInputElement | HTMLSelectElement).value;
  }

  /** État d'une case à cocher à partir de son événement. */
  protected checkedOf(event: Event): boolean {
    return (event.target as HTMLInputElement).checked;
  }

  /** Reprend les valeurs d'un morceau qui vient d'être corrigé. */
  protected onCorrected(updated: CatalogTrack): void {
    this.updateTrack(updated.id, updated);
  }

  /** Met à jour un morceau de la page affichée, sans la recharger. */
  private updateTrack(trackId: string, change: Partial<CatalogTrack>): void {
    this.state.update((s) =>
      s.kind === 'ready'
        ? {
            ...s,
            page: {
              ...s.page,
              items: s.page.items.map((t) => (t.id === trackId ? { ...t, ...change } : t)),
            },
          }
        : s,
    );
  }

  /** Applique un changement de filtre : retour à la première page. */
  private applyFilters(change: Partial<CatalogQuery>): void {
    this.query.update((q) => ({ ...q, ...change, offset: 0 }));
    this.refresh();
  }

  /** Va à la page qui commence à `offset`. */
  private goTo(offset: number): void {
    this.query.update((q) => ({ ...q, offset }));
    this.refresh();
  }

  /** Recopie la requête dans l'URL (sans ajouter d'entrée à l'historique) et recharge. */
  private refresh(): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: queryToUrl(this.query()),
      replaceUrl: true,
    });
    this.load();
  }
}

/** Requête lue dans l'URL ; une valeur absente ou invalide prend sa valeur par défaut. */
function queryFromUrl(params: ParamMap): CatalogQuery {
  const status = params.get('status') ?? '';
  const sort = params.get('sort') ?? '';
  const page = Math.max(Math.floor(toNumber(params.get('page') ?? '') ?? 1), 1);
  return {
    scope: params.get('scope') === 'all' ? 'all' : 'mine',
    q: params.get('q') ?? '',
    bpmMin: toNumber(params.get('bpm_min') ?? ''),
    bpmMax: toNumber(params.get('bpm_max') ?? ''),
    key: params.get('key') ?? '',
    status: isStatus(status) ? status : '',
    sort: isSort(sort) ? sort : 'title',
    favoritesOnly: params.get('favorites') === '1',
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  };
}

/** Paramètres d'URL de la requête ; les valeurs par défaut sont omises (null = retiré de l'URL). */
function queryToUrl(query: CatalogQuery): Params {
  const page = Math.floor(query.offset / PAGE_SIZE) + 1;
  return {
    scope: query.scope === 'all' ? 'all' : null,
    q: query.q.trim() || null,
    bpm_min: query.bpmMin,
    bpm_max: query.bpmMax,
    key: query.key.trim() || null,
    status: query.status || null,
    sort: query.sort === 'title' ? null : query.sort,
    favorites: query.favoritesOnly ? 1 : null,
    page: page > 1 ? page : null,
  };
}

/** Nombre saisi, ou null si le champ est vide ou illisible. */
function toNumber(value: string): number | null {
  const n = Number(value);
  return value.trim() === '' || !Number.isFinite(n) ? null : n;
}

/** Indique si la valeur est un statut d'analyse connu. */
function isStatus(value: string): value is AnalysisStatus {
  return (STATUSES as string[]).includes(value);
}

/** Indique si la valeur est un ordre de tri connu. */
function isSort(value: string): value is CatalogSort {
  return (SORTS as readonly string[]).includes(value);
}
