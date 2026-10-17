import { Component, computed, inject, input } from '@angular/core';
import { AudioPlayerService, TRANSITION } from '../../core/audio-player.service';

/** Avertissement affiché partout où l'on écoute un enchaînement. */
export const TRANSITION_DISCLAIMER =
  "Extraits Deezer de 30 s, souvent pris au milieu des morceaux : ce n'est pas la vraie fin de A ni le vrai début de B.";

/** Bouton « Écouter l'enchaînement » : fin de l'extrait de A, fondu croisé, début de l'extrait de B. */
@Component({
  selector: 'app-play-transition-button',
  templateUrl: './play-transition-button.component.html',
  styleUrl: './play-transition-button.component.scss',
})
export class PlayTransitionButtonComponent {
  private readonly player = inject(AudioPlayerService);

  readonly fromId = input.required<string>();
  readonly toId = input.required<string>();

  /** Cet enchaînement est celui qui joue (ou se charge). */
  protected readonly isCurrent = computed(() => {
    const current = this.player.current();
    return (
      current?.kind === 'transition' &&
      current.fromId === this.fromId() &&
      current.toId === this.toId()
    );
  });

  protected readonly loading = computed(
    () => this.isCurrent() && this.player.state() === 'loading',
  );
  protected readonly progress = computed(() => (this.isCurrent() ? this.player.progress() : 0));

  /** Échec concernant A ou B (le dernier essayé), ou null. */
  protected readonly error = computed(() => {
    const error = this.player.error();
    return error && (error.trackId === this.fromId() || error.trackId === this.toId())
      ? error
      : null;
  });

  /** Info-bulle : le déroulé et l'avertissement, ou la raison de l'échec. */
  protected readonly hint = computed(
    () =>
      this.error()?.message ??
      `Fin de A (${TRANSITION.tailSeconds} s), fondu de ${TRANSITION.fadeSeconds} s, début de B. ${TRANSITION_DISCLAIMER}`,
  );

  /** Lance ou arrête l'enchaînement. */
  protected toggle(): void {
    this.player.toggleTransition(this.fromId(), this.toId());
  }
}
