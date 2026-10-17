import { HttpErrorResponse } from '@angular/common/http';
import { Injectable, InjectionToken, inject, signal } from '@angular/core';
import { Observable, catchError, forkJoin, map, of, tap, throwError } from 'rxjs';
import { apiErrorMessage } from './api/api-error';
import { CatalogService } from './api/catalog.service';

/** Fabrique des éléments audio ; remplacée par des faux dans les tests (jsdom ne lit pas d'audio). */
export const AUDIO_FACTORY = new InjectionToken<() => HTMLAudioElement>('AUDIO_FACTORY', {
  providedIn: 'root',
  factory: () => () => new Audio(),
});

/** Déroulé d'un enchaînement : les 10 dernières s de A, fondu croisé de 4 s, puis 12 s de B. */
export const TRANSITION = {
  tailSeconds: 10,
  fadeSeconds: 4,
  nextSeconds: 12,
  tickMs: 100,
} as const;

/** Échec de l'API pour l'URL de ce morceau (pour savoir lequel de A ou B a échoué). */
interface UrlError {
  trackId: string;
  err: HttpErrorResponse;
}

/** Une URL d'extrait est réutilisée jusqu'à 2 min avant son expiration. */
const URL_MARGIN_MS = 2 * 60_000;

/** Ce qui joue : un morceau seul, ou l'enchaînement de A vers B. */
export type Playing =
  { kind: 'track'; trackId: string } | { kind: 'transition'; fromId: string; toId: string };

/** État du lecteur. */
export type PlayerState = 'idle' | 'loading' | 'playing' | 'paused';

/** Échec de lecture d'un morceau ; `final` : inutile de réessayer (pas d'extrait). */
export interface PlayError {
  trackId: string;
  message: string;
  final: boolean;
}

/**
 * Lecteur d'extraits Deezer de toute l'application : un seul son à la fois.
 *
 * Le navigateur lit directement l'URL du CDN de Deezer ; rien ne passe par notre serveur (règle n°5).
 */
@Injectable({ providedIn: 'root' })
export class AudioPlayerService {
  private readonly catalog = inject(CatalogService);
  private readonly createAudio = inject(AUDIO_FACTORY);

  readonly current = signal<Playing | null>(null);
  readonly state = signal<PlayerState>('idle');
  /** Avancement de ce qui joue, de 0 à 1. */
  readonly progress = signal(0);
  /** Dernier échec, ou null. */
  readonly error = signal<PlayError | null>(null);

  private readonly urls = new Map<string, { url: string; validUntil: number }>();
  private audios: HTMLAudioElement[] = [];
  private timer: ReturnType<typeof setInterval> | undefined;
  private session = 0;

  /** Lit le morceau, ou le met en pause / le reprend s'il est déjà en cours. */
  toggle(trackId: string): void {
    const current = this.current();
    if (current?.kind === 'track' && current.trackId === trackId && this.audios[0]) {
      const audio = this.audios[0];
      if (this.state() === 'playing') {
        audio.pause();
        this.state.set('paused');
      } else if (this.state() === 'paused') {
        void this.start(audio);
      }
      return;
    }
    this.playTrack(trackId);
  }

  /** Joue l'enchaînement de A vers B, ou l'arrête s'il est déjà en cours. */
  toggleTransition(fromId: string, toId: string): void {
    const current = this.current();
    if (current?.kind === 'transition' && current.fromId === fromId && current.toId === toId) {
      this.stop();
      return;
    }
    this.playTransition(fromId, toId);
  }

  /** Arrête tout. */
  stop(): void {
    this.session += 1;
    clearInterval(this.timer);
    for (const audio of this.audios) {
      audio.pause();
      audio.removeAttribute('src');
    }
    this.audios = [];
    this.current.set(null);
    this.state.set('idle');
    this.progress.set(0);
  }

  /** Lit un morceau du début à la fin de son extrait. */
  private playTrack(trackId: string): void {
    const session = this.begin({ kind: 'track', trackId });
    this.url(trackId).subscribe({
      next: (url) => {
        if (session !== this.session) {
          return;
        }
        const audio = this.audio(url);
        this.on(audio, 'timeupdate', session, () =>
          this.progress.set(ratio(audio.currentTime, audio.duration)),
        );
        this.on(audio, 'ended', session, () => this.stop());
        // URL expirée pendant l'écoute (le CDN répond 403) : on la redemande une fois, puis on reprend.
        let retried = false;
        this.on(audio, 'error', session, () => {
          if (retried) {
            this.fail(trackId, "L'extrait n'a pas pu être lu.", false);
            return;
          }
          retried = true;
          const position = audio.currentTime;
          this.urls.delete(trackId);
          this.url(trackId).subscribe({
            next: (fresh) => {
              if (session !== this.session) {
                return;
              }
              audio.src = fresh;
              audio.currentTime = position;
              void this.start(audio);
            },
            error: (err: HttpErrorResponse) => this.failFromApi(trackId, err),
          });
        });
        void this.start(audio);
      },
      error: (err: HttpErrorResponse) => this.failFromApi(trackId, err),
    });
  }

  /** Joue la fin de A, un fondu croisé, puis le début de B (le volume suit la position de A). */
  private playTransition(fromId: string, toId: string): void {
    const session = this.begin({ kind: 'transition', fromId, toId });
    forkJoin([this.taggedUrl(fromId), this.taggedUrl(toId)]).subscribe({
      next: ([urlA, urlB]) => {
        if (session !== this.session) {
          return;
        }
        const a = this.audio(urlA);
        const b = this.audio(urlB);
        b.preload = 'auto'; // préchargé dès maintenant : pas de trou au moment du fondu
        b.volume = 0;
        let startA: number | null = null;
        let bStarted = false;

        this.on(a, 'loadedmetadata', session, () => {
          startA = Math.max(0, a.duration - TRANSITION.tailSeconds);
          a.currentTime = startA;
          void this.start(a);
        });
        this.on(a, 'error', session, () =>
          this.fail(fromId, "L'extrait de A n'a pas pu être lu.", false),
        );
        this.on(b, 'error', session, () =>
          this.fail(toId, "L'extrait de B n'a pas pu être lu.", false),
        );

        // Intervalle plutôt que requestAnimationFrame : il continue (ralenti) quand l'onglet est caché.
        this.timer = setInterval(() => {
          if (startA === null || !Number.isFinite(a.duration)) {
            return;
          }
          const fadeStart = a.duration - TRANSITION.fadeSeconds;
          const t = a.ended ? a.duration : a.currentTime;
          if (t >= fadeStart && !bStarted) {
            bStarted = true;
            b.currentTime = 0;
            void this.start(b);
          }
          const fade = bStarted
            ? Math.min(1, Math.max(0, (t - fadeStart) / TRANSITION.fadeSeconds))
            : 0;
          a.volume = 1 - fade;
          b.volume = fade;
          if (fade >= 1 && !a.paused) {
            a.pause();
          }
          const spanA = a.duration - startA;
          const total = spanA + TRANSITION.nextSeconds - TRANSITION.fadeSeconds;
          const elapsed = bStarted ? spanA - TRANSITION.fadeSeconds + b.currentTime : t - startA;
          this.progress.set(ratio(elapsed, total));
          if (bStarted && b.currentTime >= TRANSITION.nextSeconds) {
            this.stop();
          }
        }, TRANSITION.tickMs);
      },
      error: ({ trackId, err }: UrlError) => this.failFromApi(trackId, err),
    });
  }

  /** Arrête ce qui joue et prépare une nouvelle lecture ; renvoie son numéro (pour ignorer les réponses tardives). */
  private begin(playing: Playing): number {
    this.stop();
    this.current.set(playing);
    this.state.set('loading');
    this.error.set(null);
    return this.session;
  }

  /** URL de l'extrait : réutilisée si elle est encore valable, sinon redemandée à l'API. */
  private url(trackId: string): Observable<string> {
    const cached = this.urls.get(trackId);
    if (cached && cached.validUntil > Date.now()) {
      return of(cached.url);
    }
    return this.catalog.preview(trackId).pipe(
      tap((preview) => {
        if (preview.expires_at !== null) {
          const validUntil = Date.parse(preview.expires_at) - URL_MARGIN_MS;
          this.urls.set(trackId, { url: preview.url, validUntil });
        }
      }),
      map((preview) => preview.url),
    );
  }

  /** Comme url(), mais l'erreur dit de quel morceau il s'agit. */
  private taggedUrl(trackId: string): Observable<string> {
    return this.url(trackId).pipe(
      catchError((err: HttpErrorResponse) => throwError((): UrlError => ({ trackId, err }))),
    );
  }

  /** Écoute un événement de l'élément audio, seulement tant que cette lecture est la lecture en cours. */
  private on(audio: HTMLAudioElement, event: string, session: number, handler: () => void): void {
    audio.addEventListener(event, () => {
      if (session === this.session) {
        handler();
      }
    });
  }

  /** Nouvel élément audio pour cette URL (rattaché à la lecture en cours). */
  private audio(url: string): HTMLAudioElement {
    const audio = this.createAudio();
    audio.preload = 'auto';
    audio.src = url;
    this.audios.push(audio);
    return audio;
  }

  /** Lance la lecture ; un refus du navigateur (lecture automatique bloquée) devient une erreur lisible. */
  private async start(audio: HTMLAudioElement): Promise<void> {
    const session = this.session;
    try {
      await audio.play();
      if (session === this.session) {
        this.state.set('playing');
      }
    } catch {
      if (session === this.session) {
        const current = this.current();
        const trackId = current?.kind === 'track' ? current.trackId : (current?.fromId ?? '');
        this.fail(trackId, 'Le navigateur a refusé la lecture : clique de nouveau.', false);
      }
    }
  }

  /** Échec venant de notre API : 404 = pas d'extrait (définitif), sinon on pourra réessayer. */
  private failFromApi(trackId: string, err: HttpErrorResponse): void {
    this.fail(trackId, apiErrorMessage(err, "Impossible d'obtenir l'extrait."), err.status === 404);
  }

  /** Note l'échec et arrête la lecture. */
  private fail(trackId: string, message: string, final: boolean): void {
    this.stop();
    this.error.set({ trackId, message, final });
  }
}

/** Part de `value` sur `total`, entre 0 et 1 (0 si le total est inconnu). */
function ratio(value: number, total: number): number {
  return Number.isFinite(total) && total > 0 ? Math.min(1, Math.max(0, value / total)) : 0;
}
