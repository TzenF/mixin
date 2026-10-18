import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

/** Une source de l'Explorer (top ou playlist éditoriale Deezer), partagée par tous. */
export interface ExploreSource {
  id: string;
  title: string;
  curator: string | null;
  track_count: number;
  /** Morceaux déjà analysés (BPM, tonalité). */
  analysed_count: number;
  /** Morceaux encore en attente d'analyse (un morceau sans extrait Deezer n'y est plus). */
  pending_count: number;
  last_synced_at: string | null;
  last_error: string | null;
  /** Vrai si c'est moi qui l'ai ajoutée (les sources par défaut ne se retirent pas). */
  removable: boolean;
}

/** Sources de l'Explorer ; leurs morceaux passent par le catalogue (`CatalogService.tracks` avec `source`). */
@Injectable({ providedIn: 'root' })
export class ExploreService {
  private readonly http = inject(HttpClient);

  /** Toutes les sources, avec l'avancement de la synchronisation et de l'analyse. */
  sources(): Observable<ExploreSource[]> {
    return this.http.get<ExploreSource[]>('/api/explore/sources');
  }

  /** Ajoute la playlist Deezer de ce lien (site, lien court de l'app ou identifiant) ; renvoie la source. */
  add(link: string): Observable<ExploreSource> {
    return this.http.post<ExploreSource>('/api/explore/sources', { link });
  }

  /** Retire une source que j'ai ajoutée (ses morceaux restent dans le catalogue). */
  remove(sourceId: string): Observable<void> {
    return this.http.delete<void>(`/api/explore/sources/${encodeURIComponent(sourceId)}`);
  }

  /** Met à jour la source depuis Deezer (par le worker). */
  refresh(sourceId: string): Observable<{ queued: boolean }> {
    return this.http.post<{ queued: boolean }>(
      `/api/explore/sources/${encodeURIComponent(sourceId)}/refresh`,
      null,
    );
  }
}
