import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, input, linkedSignal, signal } from '@angular/core';
import { apiErrorMessage } from '../../core/api/api-error';
import { TransitionRating } from '../../core/api/catalog.service';
import { RatingService } from '../../core/api/rating.service';
import { AudioPlayerService } from '../../core/audio-player.service';

/** Notes proposées (1 = à éviter, 5 = parfait). */
const SCALE = [1, 2, 3, 4, 5] as const;

/** Notation d'un enchaînement A → B : 1 à 5, commentaire facultatif ; mis en avant juste après l'écoute. */
@Component({
  selector: 'app-transition-rating',
  templateUrl: './transition-rating.component.html',
  styleUrl: './transition-rating.component.scss',
})
export class TransitionRatingComponent {
  private readonly ratings = inject(RatingService);
  private readonly player = inject(AudioPlayerService);

  readonly fromId = input.required<string>();
  readonly toId = input.required<string>();
  /** Ma note reçue de l'API au chargement de la page. */
  readonly rating = input<TransitionRating | null>(null);

  protected readonly scale = SCALE;
  /** Note affichée : suit `rating`, et change tout de suite au clic. */
  protected readonly current = linkedSignal(() => this.rating());
  protected readonly commenting = signal(false);
  protected readonly error = signal<string | null>(null);

  /** Vrai juste après avoir écouté cet enchaînement en entier. */
  protected readonly justListened = computed(() => {
    const last = this.player.lastFinished();
    return last?.fromId === this.fromId() && last.toId === this.toId();
  });

  /** Donne cette note (en gardant le commentaire déjà saisi). */
  protected rate(value: number): void {
    this.save({ rating: value, comment: this.current()?.comment ?? null });
  }

  /** Enregistre le commentaire avec la note actuelle (3 par défaut s'il n'y en a pas encore). */
  protected saveComment(input: HTMLInputElement): void {
    const comment = input.value.trim() || null;
    this.save({ rating: this.current()?.rating ?? 3, comment });
    this.commenting.set(false);
  }

  /** Efface ma note. */
  protected clear(): void {
    const previous = this.current();
    this.current.set(null);
    this.error.set(null);
    this.ratings.clear(this.fromId(), this.toId()).subscribe({
      error: (err: HttpErrorResponse) => this.undo(previous, err),
    });
  }

  /** Affiche la note tout de suite, l'enregistre, et revient en arrière si l'API refuse. */
  private save(next: TransitionRating): void {
    const previous = this.current();
    this.current.set(next);
    this.error.set(null);
    this.ratings.rate(this.fromId(), this.toId(), next.rating, next.comment).subscribe({
      next: (saved) => this.current.set(saved),
      error: (err: HttpErrorResponse) => this.undo(previous, err),
    });
  }

  /** Revient à la note précédente et explique pourquoi. */
  private undo(previous: TransitionRating | null, err: HttpErrorResponse): void {
    this.current.set(previous);
    this.error.set(apiErrorMessage(err, "La note n'a pas été enregistrée."));
  }
}
