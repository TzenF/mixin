import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { apiErrorMessage } from '../../core/api/api-error';
import { SPOTIFY_LOGIN_URL } from '../../core/api/auth.service';
import { ExploreService, ExploreSource } from '../../core/api/explore.service';
import { CurrentPlaylistBarComponent } from '../../shared/current-playlist-bar/current-playlist-bar.component';
import { TrackBrowserComponent } from '../../shared/track-browser/track-browser.component';

/** Tant que des morceaux attendent leur analyse, les compteurs sont relus à cet intervalle. */
export const PROGRESS_POLL_MS = 15_000;

type State =
  | { kind: 'loading' }
  | { kind: 'disconnected' }
  | { kind: 'ready'; sources: ExploreSource[] }
  | { kind: 'error'; message: string };

/** Page « Explorer » : découvrir de nouveaux morceaux dans les tops et playlists éditoriales Deezer. */
@Component({
  selector: 'app-explore-page',
  imports: [DatePipe, CurrentPlaylistBarComponent, TrackBrowserComponent],
  templateUrl: './explore.page.html',
  styleUrl: './explore.page.scss',
})
export class ExplorePage {
  private readonly explore = inject(ExploreService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  protected readonly loginUrl = SPOTIFY_LOGIN_URL;
  protected readonly state = signal<State>({ kind: 'loading' });
  /** Source choisie (dans l'URL : ?source=…), ou la première. */
  private readonly chosen = signal<string | null>(this.route.snapshot.queryParamMap.get('source'));
  /** Message après « Actualiser », ou null. */
  protected readonly notice = signal<string | null>(null);
  private poll: ReturnType<typeof setInterval> | undefined;

  /** Sources affichées, ou null tant qu'elles ne sont pas chargées. */
  protected readonly sources = computed(() => {
    const s = this.state();
    return s.kind === 'ready' ? s.sources : null;
  });

  /** La source affichée : celle de l'URL si elle existe, sinon la première. */
  protected readonly selected = computed(() => {
    const sources = this.sources() ?? [];
    return sources.find((s) => s.id === this.chosen()) ?? sources[0] ?? null;
  });

  /** Clé du navigateur de morceaux : il est recréé (filtres remis à zéro) quand on change de source. */
  protected readonly browserKeys = computed(() => {
    const selected = this.selected();
    return selected ? [selected.id] : [];
  });

  /** Message d'erreur de chargement, ou null. */
  protected readonly errorMessage = computed(() => {
    const s = this.state();
    return s.kind === 'error' ? s.message : null;
  });

  constructor() {
    inject(DestroyRef).onDestroy(() => clearInterval(this.poll));
    this.load();
  }

  /** Charge les sources ; relit les compteurs tant que des analyses sont en cours. */
  protected load(): void {
    this.explore.sources().subscribe({
      next: (sources) => {
        this.state.set({ kind: 'ready', sources });
        this.watchProgress(sources);
      },
      error: (err: HttpErrorResponse) => {
        clearInterval(this.poll);
        this.state.set(
          err.status === 401
            ? { kind: 'disconnected' }
            : { kind: 'error', message: apiErrorMessage(err, "Impossible de charger l'Explorer.") },
        );
      },
    });
  }

  /** Affiche une autre source (ses filtres repartent de zéro). */
  protected choose(source: ExploreSource): void {
    this.chosen.set(source.id);
    this.notice.set(null);
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { source: source.id },
      replaceUrl: true,
    });
  }

  /** Demande la mise à jour de la source depuis Deezer. */
  protected refresh(source: ExploreSource): void {
    this.explore.refresh(source.id).subscribe({
      next: ({ queued }) => {
        this.notice.set(
          queued
            ? 'Mise à jour demandée : elle arrive dans quelques secondes.'
            : 'Mise à jour déjà en cours.',
        );
        this.watchProgress(this.sources() ?? [], true);
      },
      error: (err: HttpErrorResponse) =>
        this.notice.set(apiErrorMessage(err, 'Mise à jour impossible.')),
    });
  }

  /** Relit les compteurs régulièrement tant qu'il reste des morceaux à analyser (ou si on vient d'actualiser). */
  private watchProgress(sources: ExploreSource[], force = false): void {
    // Sur les morceaux encore en attente, pas sur les analysés : un morceau sans extrait ne le sera jamais.
    const busy = force || sources.some((s) => s.pending_count > 0 || s.last_synced_at === null);
    clearInterval(this.poll);
    if (busy) {
      this.poll = setInterval(() => this.load(), PROGRESS_POLL_MS);
    }
  }
}
