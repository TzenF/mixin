import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { apiErrorMessage } from '../../core/api/api-error';
import { SPOTIFY_LOGIN_URL } from '../../core/api/auth.service';
import { CatalogService, LibraryMap } from '../../core/api/catalog.service';
import { BpmHistogramComponent } from './bpm-histogram/bpm-histogram.component';
import { KeyHeatmapComponent } from './key-heatmap/key-heatmap.component';

type State =
  | { kind: 'loading' }
  | { kind: 'disconnected' }
  | { kind: 'ready'; map: LibraryMap }
  | { kind: 'error'; message: string };

/** Page « Ma bibliothèque » : mes morceaux par tonalité et par BPM, et où il m'en manque. */
@Component({
  selector: 'app-library-page',
  imports: [KeyHeatmapComponent, BpmHistogramComponent],
  templateUrl: './library.page.html',
  styleUrl: './library.page.scss',
})
export class LibraryPage {
  private readonly catalog = inject(CatalogService);

  protected readonly loginUrl = SPOTIFY_LOGIN_URL;
  protected readonly state = signal<State>({ kind: 'loading' });

  /** Carte chargée, ou null. */
  protected readonly map = computed(() => {
    const s = this.state();
    return s.kind === 'ready' ? s.map : null;
  });

  /** Message d'erreur de chargement, ou null. */
  protected readonly errorMessage = computed(() => {
    const s = this.state();
    return s.kind === 'error' ? s.message : null;
  });

  constructor() {
    this.load();
  }

  /** Charge la carte ; 401 = pas connectée. */
  protected load(): void {
    this.state.set({ kind: 'loading' });
    this.catalog.libraryMap().subscribe({
      next: (map) => this.state.set({ kind: 'ready', map }),
      error: (err: HttpErrorResponse) =>
        this.state.set(
          err.status === 401
            ? { kind: 'disconnected' }
            : {
                kind: 'error',
                message: apiErrorMessage(err, 'Impossible de charger ta bibliothèque.'),
              },
        ),
    });
  }
}
