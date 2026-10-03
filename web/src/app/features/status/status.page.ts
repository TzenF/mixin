import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Health, HealthService } from '../../core/api/health.service';

type State =
  | { kind: 'loading' }
  | { kind: 'ready'; health: Health }
  | { kind: 'error'; message: string };

/** Page d'accueil provisoire : affiche l'état de la base et de la file de tâches. */
@Component({
  selector: 'app-status-page',
  imports: [RouterLink],
  templateUrl: './status.page.html',
  styleUrl: './status.page.scss',
})
export class StatusPage {
  private readonly healthService = inject(HealthService);
  protected readonly state = signal<State>({ kind: 'loading' });

  /** État des services, ou null tant qu'il n'est pas connu. */
  protected readonly health = computed(() => {
    const s = this.state();
    return s.kind === 'ready' ? s.health : null;
  });

  /** Message d'erreur, ou null s'il n'y en a pas. */
  protected readonly errorMessage = computed(() => {
    const s = this.state();
    return s.kind === 'error' ? s.message : null;
  });

  constructor() {
    this.refresh();
  }

  /** Interroge l'API et met à jour l'affichage. */
  protected refresh(): void {
    this.state.set({ kind: 'loading' });
    this.healthService.check().subscribe({
      next: (health) => this.state.set({ kind: 'ready', health }),
      error: (err: HttpErrorResponse) =>
        // 503 = l'API répond mais un service est en panne : on affiche quand même le détail
        err.status === 503 && err.error
          ? this.state.set({ kind: 'ready', health: err.error as Health })
          : this.state.set({ kind: 'error', message: "L'API ne répond pas." }),
    });
  }
}
