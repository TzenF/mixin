import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import { TransitionRating } from './catalog.service';

/** Mes notes des enchaînements A → B (elles ne changent pas le score pour l'instant). */
@Injectable({ providedIn: 'root' })
export class RatingService {
  private readonly http = inject(HttpClient);

  /** Note l'enchaînement de A vers B (remplace ma note précédente). */
  rate(
    fromId: string,
    toId: string,
    rating: number,
    comment: string | null,
  ): Observable<TransitionRating> {
    return this.http.put<TransitionRating>(this.url(fromId, toId), { rating, comment });
  }

  /** Efface ma note de l'enchaînement de A vers B. */
  clear(fromId: string, toId: string): Observable<void> {
    return this.http.delete<void>(this.url(fromId, toId));
  }

  /** Nombre d'enchaînements que j'ai notés. */
  count(): Observable<number> {
    return this.http
      .get<{ count: number }>('/api/transitions/ratings/count')
      .pipe(map((body) => body.count));
  }

  /** Adresse de la note de l'enchaînement A → B. */
  private url(fromId: string, toId: string): string {
    return `/api/transitions/${encodeURIComponent(fromId)}/${encodeURIComponent(toId)}/rating`;
  }
}
