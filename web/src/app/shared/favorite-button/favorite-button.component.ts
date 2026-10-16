import { Component, inject, input, linkedSignal, signal } from '@angular/core';
import { CatalogService } from '../../core/api/catalog.service';

/** Bouton ★ / ☆ : met un morceau dans mes favoris ou l'en retire (catalogue, suggestions, playlists). */
@Component({
  selector: 'app-favorite-button',
  templateUrl: './favorite-button.component.html',
  styleUrl: './favorite-button.component.scss',
})
export class FavoriteButtonComponent {
  private readonly catalog = inject(CatalogService);

  /** Morceau concerné. */
  readonly trackId = input.required<string>();
  /** Valeur reçue de l'API au chargement de la page. */
  readonly favorite = input.required<boolean>();

  /** Valeur affichée : suit `favorite`, et change tout de suite au clic. */
  protected readonly isFavorite = linkedSignal(() => this.favorite());
  protected readonly saving = signal(false);
  protected readonly failed = signal(false);

  /** Inverse l'état ; revient en arrière si l'API refuse. */
  protected toggle(): void {
    const next = !this.isFavorite();
    this.isFavorite.set(next);
    this.saving.set(true);
    this.failed.set(false);
    this.catalog.setFavorite(this.trackId(), next).subscribe({
      next: () => this.saving.set(false),
      error: () => {
        this.isFavorite.set(!next);
        this.saving.set(false);
        this.failed.set(true);
      },
    });
  }
}
