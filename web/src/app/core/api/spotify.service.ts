import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

/** Une playlist Spotify de l'utilisateur (voir backend/app/api/spotify.py). */
export interface SpotifyPlaylist {
  id: string;
  name: string;
  track_count: number;
  imported: boolean;
}

/** Bilan d'un import : total = nouveaux + déjà connus + ignorés. */
export interface ImportOutcome {
  import_job_id: string;
  playlist_id: string;
  name: string;
  created: boolean;
  total: number;
  new: number;
  known: number;
  skipped: number;
  queued: number;
}

/** Playlists Spotify de l'utilisateur connecté : liste et import dans notre base. */
@Injectable({ providedIn: 'root' })
export class SpotifyService {
  private readonly http = inject(HttpClient);

  /** Playlists dont l'utilisateur est propriétaire ; erreur 401 s'il n'est pas connecté. */
  playlists(): Observable<SpotifyPlaylist[]> {
    return this.http.get<SpotifyPlaylist[]>('/api/spotify/playlists');
  }

  /** Importe (ou réimporte) une playlist et renvoie le bilan. */
  importPlaylist(playlistId: string): Observable<ImportOutcome> {
    return this.http.post<ImportOutcome>(
      `/api/spotify/playlists/${encodeURIComponent(playlistId)}/import`,
      null,
    );
  }
}
