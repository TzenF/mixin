import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, input, output, signal } from '@angular/core';
import { apiErrorMessage } from '../../core/api/api-error';
import { CatalogService, CatalogTrack, CorrectionChanges } from '../../core/api/catalog.service';

/** Bornes du BPM acceptées par l'API. */
export const BPM_MIN = 40;
export const BPM_MAX = 250;

/** Bouton « Corriger » : formulaire en ligne pour corriger BPM et tonalité (×2, ÷2, annuler ma correction). */
@Component({
  selector: 'app-track-correction',
  templateUrl: './track-correction.component.html',
  styleUrl: './track-correction.component.scss',
})
export class TrackCorrectionComponent {
  private readonly catalog = inject(CatalogService);

  /** Morceau à corriger, avec ses valeurs affichées. */
  readonly track = input.required<CatalogTrack>();
  /** Émis avec le morceau mis à jour après chaque correction enregistrée. */
  readonly corrected = output<CatalogTrack>();

  protected readonly open = signal(false);
  protected readonly saving = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly bpmMin = BPM_MIN;
  protected readonly bpmMax = BPM_MAX;

  /** Multiplie le BPM saisi (×2 ou ÷2 pour un demi ou double tempo mal détecté). */
  protected scale(bpmInput: HTMLInputElement, factor: number): void {
    const bpm = Number(bpmInput.value);
    if (bpmInput.value.trim() !== '' && Number.isFinite(bpm)) {
      bpmInput.value = String(Math.round(bpm * factor * 10) / 10);
    }
  }

  /** Enregistre les champs modifiés (un champ inchangé n'est pas envoyé). */
  protected save(bpmInput: HTMLInputElement, keyInput: HTMLInputElement): void {
    const track = this.track();
    const changes: CorrectionChanges = {};
    const bpm = bpmInput.value.trim() === '' ? null : Number(bpmInput.value);
    if (bpm !== null && bpm !== track.bpm) {
      if (!Number.isFinite(bpm) || bpm < BPM_MIN || bpm > BPM_MAX) {
        this.error.set(`Le BPM doit être entre ${BPM_MIN} et ${BPM_MAX}.`);
        return;
      }
      changes.bpm = bpm;
    }
    const key = keyInput.value.trim();
    if (key !== '' && key.toUpperCase() !== (track.camelot ?? '').toUpperCase()) {
      changes.key = key;
    }
    if (Object.keys(changes).length === 0) {
      this.open.set(false);
      return;
    }
    this.send(changes);
  }

  /** Annule ma correction d'un champ : la valeur d'Essentia revient. */
  protected cancel(field: 'bpm' | 'key'): void {
    this.send({ [field]: null });
  }

  /** Envoie la correction, puis ferme le formulaire et prévient la page. */
  private send(changes: CorrectionChanges): void {
    this.saving.set(true);
    this.error.set(null);
    this.catalog.correct(this.track().id, changes).subscribe({
      next: (updated) => {
        this.saving.set(false);
        this.open.set(false);
        this.corrected.emit(updated);
      },
      error: (err: HttpErrorResponse) => {
        this.saving.set(false);
        this.error.set(apiErrorMessage(err, 'La correction a échoué.'));
      },
    });
  }
}
