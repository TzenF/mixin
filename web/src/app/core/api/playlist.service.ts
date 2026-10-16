import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { CatalogTrack, KeyMove } from './catalog.service';

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
}

/** Une playlist avec ses morceaux dans l'ordre. */
export interface PlaylistDetail extends PlaylistSummary {
  items: PlaylistItem[];
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
}
