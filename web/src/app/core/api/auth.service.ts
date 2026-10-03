import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

/** Adresse de connexion Spotify : à ouvrir en navigation pleine page (redirection OAuth), pas en XHR. */
export const SPOTIFY_LOGIN_URL = '/api/auth/spotify/login';

/** Réponse de GET /auth/me (voir backend/app/api/auth.py). */
export interface Me {
  id: string;
  display_name: string;
  spotify_connected: boolean;
}

/** Session de l'utilisateur : qui est connecté, déconnexion. */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);

  /** Utilisateur connecté ; erreur HTTP 401 si personne ne l'est. */
  me(): Observable<Me> {
    return this.http.get<Me>('/api/auth/me');
  }

  /** Ferme la session courante. */
  logout(): Observable<void> {
    return this.http.post<void>('/api/auth/logout', null);
  }
}
