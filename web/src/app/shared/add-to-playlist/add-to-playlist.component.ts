import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, input, signal } from '@angular/core';
import { apiErrorMessage } from '../../core/api/api-error';
import { CurrentPlaylistService } from '../../core/current-playlist.service';

/** Bouton « + Ajouter » : ajoute un morceau à la playlist en cours (catalogue, suggestions). */
@Component({
  selector: 'app-add-to-playlist',
  templateUrl: './add-to-playlist.component.html',
  styleUrl: './add-to-playlist.component.scss',
})
export class AddToPlaylistComponent {
  private readonly playlist = inject(CurrentPlaylistService);

  /** Morceau à ajouter. */
  readonly trackId = input.required<string>();

  protected readonly adding = signal(false);
  protected readonly error = signal<string | null>(null);

  /** Vrai si le morceau est déjà dans la playlist en cours. */
  protected readonly added = computed(() => this.playlist.trackIds().has(this.trackId()));

  /** Info-bulle : dans quelle playlist le morceau ira, ou pourquoi le bouton est désactivé. */
  protected readonly hint = computed(() => {
    const current = this.playlist.current();
    if (current === null) {
      return "Choisis d'abord une playlist en cours";
    }
    return this.added() ? `Déjà dans « ${current.name} »` : `Ajouter à « ${current.name} »`;
  });

  /** Vrai si le bouton est utilisable. */
  protected readonly enabled = computed(
    () => this.playlist.current() !== null && !this.added() && !this.adding(),
  );

  /** Ajoute le morceau à la playlist en cours. */
  protected add(): void {
    this.adding.set(true);
    this.error.set(null);
    this.playlist.add(this.trackId()).subscribe({
      next: () => this.adding.set(false),
      error: (err: unknown) => {
        this.adding.set(false);
        this.error.set(
          err instanceof HttpErrorResponse
            ? apiErrorMessage(err, "L'ajout a échoué.")
            : "L'ajout a échoué.",
        );
      },
    });
  }
}
