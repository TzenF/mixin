import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { apiErrorMessage } from '../../core/api/api-error';
import { CurrentPlaylistService } from '../../core/current-playlist.service';

/** Barre « Playlist en cours » : choisir la playlist que remplissent les boutons « + Ajouter », ou en créer une. */
@Component({
  selector: 'app-current-playlist-bar',
  templateUrl: './current-playlist-bar.component.html',
  styleUrl: './current-playlist-bar.component.scss',
})
export class CurrentPlaylistBarComponent {
  protected readonly playlist = inject(CurrentPlaylistService);

  /** Vrai pendant la saisie du nom d'une nouvelle playlist. */
  protected readonly creating = signal(false);
  protected readonly error = signal<string | null>(null);

  constructor() {
    this.playlist.refresh();
  }

  /** Change la playlist en cours (valeur vide : aucune). */
  protected choose(event: Event): void {
    const value = (event.target as HTMLSelectElement).value;
    this.playlist.select(value === '' ? null : value);
  }

  /** Crée une playlist avec ce nom et en fait la playlist en cours. */
  protected create(nameInput: HTMLInputElement): void {
    const name = nameInput.value.trim();
    if (name === '') {
      return;
    }
    this.error.set(null);
    this.playlist.create(name).subscribe({
      next: () => this.creating.set(false),
      error: (err: HttpErrorResponse) =>
        this.error.set(apiErrorMessage(err, 'Impossible de créer la playlist.')),
    });
  }
}
