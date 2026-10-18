import { Component, computed, input } from '@angular/core';
import { RouterLink } from '@angular/router';

/** Largeur d'une tranche (BPM), comme le serveur ; une graduation sous l'axe tous les AXIS_STEP BPM. */
const BIN = 2;
const AXIS_STEP = 10;
/** Une plage vide n'est signalée que dans la zone où les DJ jouent vraiment (les extrêmes sont souvent ½ / ×2). */
const GAP_RANGE = { from: 90, to: 160 };

/** Une tranche de l'histogramme : de `from` à moins de `from + 2` BPM. */
interface Bin {
  from: number;
  count: number;
  /** Hauteur de la barre en % du maximum. */
  height: number;
  /** Paramètres du catalogue qui montrent tous les morceaux de cette tranche. */
  query: Record<string, string | number>;
}

/** Histogramme des BPM de mes morceaux : chaque tranche (et chaque trou) ouvre le catalogue filtré dessus. */
@Component({
  selector: 'app-bpm-histogram',
  imports: [RouterLink],
  templateUrl: './bpm-histogram.component.html',
  styleUrl: './bpm-histogram.component.scss',
})
export class BpmHistogramComponent {
  /** Morceaux par tranche de 2 BPM (« 124 » → nombre). */
  readonly counts = input.required<Record<string, number>>();

  /** Toutes les tranches de la plus basse à la plus haute, vides comprises. */
  protected readonly bins = computed((): Bin[] => {
    const entries = Object.entries(this.counts()).map(([bin, n]) => [Number(bin), n] as const);
    if (entries.length === 0) {
      return [];
    }
    const low = Math.min(...entries.map(([b]) => b));
    const high = Math.max(...entries.map(([b]) => b));
    const max = Math.max(...entries.map(([, n]) => n));
    const bins: Bin[] = [];
    for (let from = low; from <= high; from += BIN) {
      const count = this.counts()[String(from)] ?? 0;
      bins.push({ from, count, height: (count / max) * 100, query: rangeQuery(from, from + BIN) });
    }
    return bins;
  });

  /** Graduations sous l'axe (multiples de 10). */
  protected readonly ticks = computed(() =>
    this.bins()
      .filter((b) => b.from % AXIS_STEP === 0)
      .map((b) => b.from),
  );

  /** Plages de BPM sans aucun morceau entre 90 et 160 (tranches vides consécutives regroupées). */
  protected readonly gaps = computed(() => {
    const gaps: { from: number; to: number; query: Record<string, string | number> }[] = [];
    for (const bin of this.bins()) {
      if (bin.count > 0 || bin.from < GAP_RANGE.from || bin.from >= GAP_RANGE.to) {
        continue;
      }
      const last = gaps[gaps.length - 1];
      if (last !== undefined && last.to === bin.from) {
        last.to = bin.from + BIN;
        last.query = rangeQuery(last.from, last.to);
      } else {
        gaps.push({
          from: bin.from,
          to: bin.from + BIN,
          query: rangeQuery(bin.from, bin.from + BIN),
        });
      }
    }
    return gaps;
  });
}

/** Paramètres du catalogue (tous les morceaux, Explorer compris) pour les BPM de `from` à moins de `to`. */
function rangeQuery(from: number, to: number): Record<string, string | number> {
  return { scope: 'all', bpm_min: from, bpm_max: to - 0.01 };
}
