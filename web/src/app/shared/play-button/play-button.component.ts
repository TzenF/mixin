import { Component, computed, inject, input } from '@angular/core';
import { AudioPlayerService } from '../../core/audio-player.service';

/** Bouton ▶ / ⏸ : écoute l'extrait Deezer d'un morceau (un seul son à la fois dans toute l'application). */
@Component({
  selector: 'app-play-button',
  templateUrl: './play-button.component.html',
  styleUrl: './play-button.component.scss',
})
export class PlayButtonComponent {
  private readonly player = inject(AudioPlayerService);

  readonly trackId = input.required<string>();
  /** Vrai si l'analyse n'a trouvé aucun extrait : bouton désactivé d'avance, sans appel. */
  readonly noPreview = input(false);

  /** Ce morceau est celui qui joue (ou se charge, ou est en pause). */
  protected readonly isCurrent = computed(() => {
    const current = this.player.current();
    return current?.kind === 'track' && current.trackId === this.trackId();
  });

  protected readonly playing = computed(
    () => this.isCurrent() && this.player.state() === 'playing',
  );
  protected readonly loading = computed(
    () => this.isCurrent() && this.player.state() === 'loading',
  );
  protected readonly progress = computed(() => (this.isCurrent() ? this.player.progress() : 0));

  /** Échec de lecture de ce morceau, ou null. */
  protected readonly error = computed(() => {
    const error = this.player.error();
    return error?.trackId === this.trackId() ? error : null;
  });

  /** Désactivé s'il n'y a pas d'extrait (connu d'avance, ou appris de l'API). */
  protected readonly disabled = computed(() => this.noPreview() || this.error()?.final === true);

  /** Info-bulle : l'action, ou la raison de l'échec. */
  protected readonly hint = computed(() => {
    if (this.noPreview()) {
      return "Pas d'extrait Deezer pour ce morceau";
    }
    const error = this.error();
    if (error) {
      return error.message;
    }
    return this.playing() ? "Mettre l'extrait en pause" : "Écouter l'extrait (30 s, Deezer)";
  });

  /** Lit, met en pause ou reprend l'extrait. */
  protected toggle(): void {
    this.player.toggle(this.trackId());
  }
}
