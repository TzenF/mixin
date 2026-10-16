import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

/** Où en est l'analyse audio d'un morceau. */
export type AnalysisStatus = 'pending' | 'done' | 'no_preview' | 'failed';

/** Ordre du catalogue. */
export type CatalogSort = 'title' | 'bpm' | 'key';

/** Un morceau du catalogue (voir backend/app/api/tracks.py) ; bpm et camelot à null sans analyse. */
export interface CatalogTrack {
  id: string;
  title: string;
  artists: string[];
  bpm: number | null;
  camelot: string | null;
  bpm_source: string | null;
  key_source: string | null;
  key_confidence: number | null;
  analysis_status: AnalysisStatus;
}

/** Une page du catalogue ; total = nombre de morceaux qui passent les filtres. */
export interface CatalogPage {
  total: number;
  items: CatalogTrack[];
}

/** Tonalité affichée après une correction perso. */
export interface KeyCorrected {
  camelot: string;
  key_source: 'manual';
}

/** Filtres, tri et page demandés ; une chaîne vide ou null = pas de filtre. */
export interface CatalogQuery {
  scope: 'mine' | 'all';
  q: string;
  bpmMin: number | null;
  bpmMax: number | null;
  key: string;
  status: AnalysisStatus | '';
  sort: CatalogSort;
  limit: number;
  offset: number;
}

/** Catalogue des morceaux : les miens (playlists importées) ou tous. */
@Injectable({ providedIn: 'root' })
export class CatalogService {
  private readonly http = inject(HttpClient);

  /** Une page du catalogue ; erreur 401 si personne n'est connecté. */
  tracks(query: CatalogQuery): Observable<CatalogPage> {
    let params = new HttpParams()
      .set('scope', query.scope)
      .set('sort', query.sort)
      .set('limit', query.limit)
      .set('offset', query.offset);
    const optional: Record<string, string | number | null> = {
      q: query.q.trim(),
      bpm_min: query.bpmMin,
      bpm_max: query.bpmMax,
      key: query.key.trim(),
      status: query.status,
    };
    for (const [name, value] of Object.entries(optional)) {
      if (value !== null && value !== '') {
        params = params.set(name, value);
      }
    }
    return this.http.get<CatalogPage>('/api/tracks', { params });
  }

  /** Inverse majeur/mineur de la tonalité affichée (8A -> 11B), pour moi seulement ; 409 sans tonalité. */
  flipMode(trackId: string): Observable<KeyCorrected> {
    return this.http.post<KeyCorrected>(
      `/api/tracks/${encodeURIComponent(trackId)}/key/flip-mode`,
      null,
    );
  }
}
