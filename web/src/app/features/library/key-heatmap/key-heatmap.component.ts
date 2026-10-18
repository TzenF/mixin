import { Component, computed, inject, input, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { CAMELOT_KEYS, ringOf, wheelPoint } from '../../../shared/camelot-geometry';

/** Taille de la roue (px, carré), rayons des anneaux et d'une tonalité (24 px et plus : bonne cible). */
const SIZE = 300;
const CENTER = SIZE / 2;
const RADIUS = { B: 112, A: 72 };
const NODE_RADIUS = 17;
/** Paliers de couleur (--color-seq-1 à 5) ; les paliers 1 et 2 sont clairs : texte marine, sinon blanc. */
const STEPS = 5;
const LIGHT_STEPS = 2;
/** Tonalités les moins fournies listées sous la roue. */
const POOREST = 4;

/** Une tonalité de la carte : sa place, son nombre de morceaux et son palier de couleur (0 = aucun). */
interface HeatKey {
  key: string;
  x: number;
  y: number;
  count: number;
  step: number;
}

/** Roue de Camelot en carte de chaleur : combien de mes morceaux dans chaque tonalité ; un clic cherche les autres. */
@Component({
  selector: 'app-key-heatmap',
  imports: [RouterLink],
  templateUrl: './key-heatmap.component.html',
  styleUrl: './key-heatmap.component.scss',
})
export class KeyHeatmapComponent {
  private readonly router = inject(Router);

  /** Morceaux par tonalité (« 8A » → nombre) ; une tonalité absente = aucun morceau. */
  readonly counts = input.required<Record<string, number>>();

  protected readonly size = SIZE;
  protected readonly center = CENTER;
  protected readonly radius = RADIUS;
  protected readonly nodeRadius = NODE_RADIUS;
  /** Tonalité survolée ou choisie au clavier, ou null. */
  protected readonly active = signal<string | null>(null);

  /** Le plus grand nombre de morceaux dans une tonalité (au moins 1). */
  private readonly max = computed(() => Math.max(1, ...Object.values(this.counts())));

  /** Les 24 tonalités avec leur palier : proportionnel au maximum, arrondi au palier supérieur. */
  protected readonly keys = computed((): HeatKey[] =>
    CAMELOT_KEYS.map((key) => {
      const count = this.counts()[key] ?? 0;
      return {
        key,
        ...wheelPoint(Number.parseInt(key, 10), RADIUS[ringOf(key)], CENTER),
        count,
        step: count === 0 ? 0 : Math.ceil((count / this.max()) * STEPS),
      };
    }),
  );

  /** Les tonalités où j'ai le moins de morceaux (les vides d'abord). */
  protected readonly poorest = computed(() =>
    [...this.keys()]
      .sort((a, b) => a.count - b.count || a.key.localeCompare(b.key))
      .slice(0, POOREST),
  );

  /** Légende : la plage de nombres de chaque palier. */
  protected readonly legend = computed(() =>
    Array.from({ length: STEPS }, (_, i) => ({
      step: i + 1,
      from: Math.floor((i / STEPS) * this.max()) + 1,
      to: Math.floor(((i + 1) / STEPS) * this.max()),
    })).filter((l) => l.from <= l.to),
  );

  /** Tonalité survolée, pour l'infobulle. */
  protected readonly tooltip = computed(
    () => this.keys().find((k) => k.key === this.active()) ?? null,
  );

  /** Vrai si le nom de la tonalité doit être écrit en marine (palier clair ou case vide). */
  protected darkText(k: HeatKey): boolean {
    return k.step <= LIGHT_STEPS;
  }

  /** Ouvre le catalogue (tous les morceaux, Explorer compris) filtré sur cette tonalité. */
  protected search(key: string): void {
    void this.router.navigate(['/catalog'], { queryParams: { scope: 'all', key } });
  }

  /** Clavier : flèches = tonalité suivante / précédente, Entrée = chercher. */
  protected onKeydown(event: KeyboardEvent): void {
    const index = CAMELOT_KEYS.indexOf(this.active() ?? '');
    if (event.key === 'Enter' && this.active() !== null) {
      this.search(this.active() as string);
      return;
    }
    const step =
      event.key === 'ArrowRight' || event.key === 'ArrowDown'
        ? 1
        : event.key === 'ArrowLeft' || event.key === 'ArrowUp'
          ? -1
          : 0;
    if (step !== 0) {
      event.preventDefault();
      const next = index === -1 ? 0 : (index + step + CAMELOT_KEYS.length) % CAMELOT_KEYS.length;
      this.active.set(CAMELOT_KEYS[next]);
    }
  }
}
