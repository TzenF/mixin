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
  favorite: boolean;
}

/** Une page du catalogue ; total = nombre de morceaux qui passent les filtres. */
export interface CatalogPage {
  total: number;
  items: CatalogTrack[];
}

/** Type d'enchaînement de tonalité (roue Camelot). */
export type KeyMove = 'same' | 'adjacent' | 'relative' | 'diagonal' | 'energy_shift';

/** Ma note d'un enchaînement A → B (1 à 5) et mon commentaire éventuel. */
export interface TransitionRating {
  rating: number;
  comment: string | null;
}

/** Un morceau qui s'enchaîne bien après le morceau de départ (voir backend/app/api/tracks.py). */
export interface Suggestion {
  track_id: string;
  title: string;
  artists: string[];
  bpm: number;
  camelot: string;
  key_move: KeyMove;
  /** Vrai si l'enchaînement passe par un demi- ou double tempo. */
  half_double: boolean;
  bpm_diff_pct: number;
  score: number;
  favorite: boolean;
  /** Ma note de l'enchaînement départ → ce morceau, ou null. */
  my_rating: TransitionRating | null;
}

/** Réglages des suggestions. */
export interface SuggestionOptions {
  scope: 'mine' | 'all';
  /** Écart de BPM accepté, en fraction (0.06 = ±6 %). */
  bpmTolerance: number;
  /** Seulement mes favoris. */
  favoritesOnly: boolean;
}

/** Correction à envoyer : un champ absent reste tel quel ; à null, ma correction de ce champ est annulée. */
export interface CorrectionChanges {
  bpm?: number | null;
  key?: string | null;
}

/** URL d'un extrait Deezer, à lire tout de suite ; expires_at null = expiration inconnue. */
export interface Preview {
  url: string;
  expires_at: string | null;
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
  /** Seulement mes favoris. */
  favoritesOnly: boolean;
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
    if (query.favoritesOnly) {
      params = params.set('favorites', true);
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

  /** Un morceau et ses valeurs affichées ; 404 s'il n'existe pas. */
  track(trackId: string): Observable<CatalogTrack> {
    return this.http.get<CatalogTrack>(`/api/tracks/${encodeURIComponent(trackId)}`);
  }

  /** Morceaux qui s'enchaînent bien après ce morceau, du meilleur au moins bon. */
  suggestions(trackId: string, options: SuggestionOptions): Observable<Suggestion[]> {
    let params = new HttpParams()
      .set('scope', options.scope)
      .set('bpm_tolerance', options.bpmTolerance);
    if (options.favoritesOnly) {
      params = params.set('favorites', true);
    }
    return this.http.get<Suggestion[]>(`/api/tracks/${encodeURIComponent(trackId)}/suggestions`, {
      params,
    });
  }

  /** Met le morceau dans mes favoris, ou l'en retire. */
  setFavorite(trackId: string, favorite: boolean): Observable<void> {
    const url = `/api/tracks/${encodeURIComponent(trackId)}/favorite`;
    return favorite ? this.http.put<void>(url, null) : this.http.delete<void>(url);
  }

  /** Corrige le BPM et/ou la tonalité (pour moi seulement) ; renvoie le morceau mis à jour. */
  correct(trackId: string, changes: CorrectionChanges): Observable<CatalogTrack> {
    return this.http.patch<CatalogTrack>(
      `/api/tracks/${encodeURIComponent(trackId)}/correction`,
      changes,
    );
  }

  /** URL neuve de l'extrait (valable ~15 min) ; 404 avec `reason` s'il n'y en a pas, 503 si Deezer flanche. */
  preview(trackId: string): Observable<Preview> {
    return this.http.get<Preview>(`/api/tracks/${encodeURIComponent(trackId)}/preview`);
  }
}
