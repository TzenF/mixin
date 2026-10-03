import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

/** Réponse de GET /health (voir backend/app/api/health.py). */
export interface Health {
  status: 'ok' | 'degraded';
  database: boolean;
  queue: boolean;
}

/** Interroge la route de santé de l'API. */
@Injectable({ providedIn: 'root' })
export class HealthService {
  private readonly http = inject(HttpClient);

  /** Toutes les requêtes passent par /api, redirigé vers le backend par le proxy de dev. */
  check(): Observable<Health> {
    return this.http.get<Health>('/api/health');
  }
}
