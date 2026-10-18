import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { CatalogTrack, KeyMove, TransitionRating } from './catalog.service';

/** Bilan d'un ordre : enchaînements refusés et score moyen (morceaux analysés seulement). */
export interface OrderQuality {
  refused: number;
  mean_score: number;
}

/** Ordre proposé pour une playlist (voir backend/app/api/playlists.py), à appliquer avec `reorder`. */
export interface OrderProposal {
  item_ids: number[];
  before: OrderQuality;
  after: OrderQuality;
  /** Morceaux non analysés, placés en fin. */
  unanalysed: number;
  /** Enchaînement entre morceaux analysés consécutifs de l'ordre proposé ; transition null = refusé. */
  steps: { transition: Transition | null; score: number | null }[];
}

/** Une playlist ; source_provider null = créée ici, sinon importée (lecture seule). */
export interface PlaylistSummary {
  id: string;
  name: string;
  source_provider: string | null;
  track_count: number;
  updated_at: string;
}

/** Enchaînement vers le morceau suivant (voir la fonction SQL transition). */
export interface Transition {
  /** null : tonalité incompatible, voir key_distance. */
  key_move: KeyMove | null;
  /** Crans sur la roue Camelot (0 à 6). */
  key_distance: number;
  half_double: boolean;
  bpm_diff: number;
  /** Écart signé en % du tempo direct (+1,2 = on accélère). */
  bpm_change: number;
  /** Écart de BPM dans la tolérance (sinon, c'est le tempo qui pose problème). */
  tempo_ok: boolean;
  /** Même lettre Camelot (mineur → mineur ou majeur → majeur). */
  same_mode: boolean;
  compatible: boolean;
}

/** Un morceau de la playlist ; transition_to_next null = dernier morceau, ou l'un des deux non analysé. */
export interface PlaylistItem {
  item_id: number;
  position: number;
  track: CatalogTrack;
  transition_to_next: Transition | null;
  /** Ma note de ce morceau vers le suivant, ou null. */
  my_rating: TransitionRating | null;
}

/** Dernier export d'une playlist vers Spotify. */
export interface SpotifyExport {
  url: string;
  exported_at: string;
}

/** Une playlist avec ses morceaux dans l'ordre ; spotify_export null = jamais exportée. */
export interface PlaylistDetail extends PlaylistSummary {
  items: PlaylistItem[];
  spotify_export: SpotifyExport | null;
}

/** Bilan d'un export : created = nouvelle playlist chez Spotify (sinon : mise à jour de la précédente). */
export interface ExportOutcome {
  url: string;
  created: boolean;
  exported: number;
  /** Morceaux absents de Spotify (sans identifiant Spotify). */
  skipped: number;
  exported_at: string;
}

/** Élément ajouté à une playlist. */
export interface AddedItem {
  item_id: number;
  position: number;
}

/** Playlists de l'utilisateur connecté. */
@Injectable({ providedIn: 'root' })
export class PlaylistService {
  private readonly http = inject(HttpClient);

  /** Mes playlists, les plus récemment modifiées d'abord ; 401 si personne n'est connecté. */
  list(): Observable<PlaylistSummary[]> {
    return this.http.get<PlaylistSummary[]>('/api/playlists');
  }

  /** Une de mes playlists avec ses morceaux et leurs enchaînements ; 404 si elle n'est pas à moi. */
  get(playlistId: string): Observable<PlaylistDetail> {
    return this.http.get<PlaylistDetail>(`/api/playlists/${encodeURIComponent(playlistId)}`);
  }

  /** Crée une playlist vide. */
  create(name: string): Observable<PlaylistSummary> {
    return this.http.post<PlaylistSummary>('/api/playlists', { name });
  }

  /** Renomme une de mes playlists ; 409 si elle est importée. */
  rename(playlistId: string, name: string): Observable<PlaylistSummary> {
    return this.http.patch<PlaylistSummary>(`/api/playlists/${encodeURIComponent(playlistId)}`, {
      name,
    });
  }

  /** Supprime une de mes playlists (les morceaux restent dans le catalogue). */
  delete(playlistId: string): Observable<void> {
    return this.http.delete<void>(`/api/playlists/${encodeURIComponent(playlistId)}`);
  }

  /** Ajoute un morceau en fin de playlist, ou à `position` (0 = en tête) ; 409 si elle est importée. */
  addTrack(playlistId: string, trackId: string, position?: number): Observable<AddedItem> {
    return this.http.post<AddedItem>(`/api/playlists/${encodeURIComponent(playlistId)}/items`, {
      track_id: trackId,
      ...(position === undefined ? {} : { position }),
    });
  }

  /** Insère plusieurs morceaux d'un coup (tout ou rien), dans l'ordre, à partir de `position`. */
  insertTracks(playlistId: string, trackIds: string[], position: number): Observable<AddedItem[]> {
    return this.http.post<AddedItem[]>(
      `/api/playlists/${encodeURIComponent(playlistId)}/items/batch`,
      { track_ids: trackIds, position },
    );
  }

  /** Duplique une de mes playlists (même importée) en une playlist modifiable « X (copie) ». */
  copy(playlistId: string): Observable<PlaylistSummary> {
    return this.http.post<PlaylistSummary>(
      `/api/playlists/${encodeURIComponent(playlistId)}/copy`,
      null,
    );
  }

  /** Change l'ordre des morceaux (tous les item_id, dans le nouvel ordre) ; 422 si la playlist a changé. */
  reorder(playlistId: string, itemIds: number[]): Observable<void> {
    return this.http.put<void>(`/api/playlists/${encodeURIComponent(playlistId)}/order`, {
      item_ids: itemIds,
    });
  }

  /** Ordre proposé (ouverture comprise) et bilan avant / après ; rien n'est modifié. */
  proposeOrder(playlistId: string): Observable<OrderProposal> {
    return this.http.get<OrderProposal>(
      `/api/playlists/${encodeURIComponent(playlistId)}/order/proposal`,
    );
  }

  /** Retire un morceau de la playlist (les suivants remontent d'une place). */
  removeItem(playlistId: string, itemId: number): Observable<void> {
    return this.http.delete<void>(
      `/api/playlists/${encodeURIComponent(playlistId)}/items/${itemId}`,
    );
  }

  /** Exporte la playlist vers Spotify (privée) ou met à jour l'export précédent ; 409 si elle est importée. */
  exportToSpotify(playlistId: string): Observable<ExportOutcome> {
    return this.http.post<ExportOutcome>(
      `/api/playlists/${encodeURIComponent(playlistId)}/export/spotify`,
      null,
    );
  }
}
