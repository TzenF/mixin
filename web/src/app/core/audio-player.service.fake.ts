import { signal } from '@angular/core';
import { PlayError, PlayerState, Playing } from './audio-player.service';

/**
 * Faux AudioPlayerService pour les tests des composants et des pages : aucun son, aucune requête.
 *
 * Usage : `{ provide: AudioPlayerService, useValue: new FakeAudioPlayerService() }`.
 */
export class FakeAudioPlayerService {
  readonly current = signal<Playing | null>(null);
  readonly state = signal<PlayerState>('idle');
  readonly progress = signal(0);
  readonly error = signal<PlayError | null>(null);
  readonly lastFinished = signal<{ fromId: string; toId: string } | null>(null);
  /** Appels reçus, dans l'ordre (« toggle:a », « transition:a>b »). */
  readonly calls: string[] = [];

  /** Note l'appel et fait comme si le morceau jouait. */
  toggle(trackId: string): void {
    this.calls.push(`toggle:${trackId}`);
    this.current.set({ kind: 'track', trackId });
    this.state.set('playing');
  }

  /** Note l'appel et fait comme si l'enchaînement jouait. */
  toggleTransition(fromId: string, toId: string): void {
    this.calls.push(`transition:${fromId}>${toId}`);
    this.current.set({ kind: 'transition', fromId, toId });
    this.state.set('playing');
  }

  /** Arrête tout. */
  stop(): void {
    this.current.set(null);
    this.state.set('idle');
  }
}
