import { DecimalPipe } from '@angular/common';
import { Component, ElementRef, computed, effect, input, signal, viewChild } from '@angular/core';
import { PlaylistItem } from '../../../core/api/playlist.service';
import { TransitionView, describeTransition } from '../../../shared/key-moves';

/** Hauteur du graphique et marges (px) : place des valeurs d'axe à gauche et des numéros en bas. */
const HEIGHT = 220;
const MARGIN = { top: 20, right: 16, bottom: 28, left: 44 };
/** Rayon des points (8 px de diamètre) ; au-delà de MAX_POINTS morceaux, la ligne suffit. */
const MARKER_RADIUS = 4;
const MAX_POINTS = 100;
/** Au plus ce nombre de numéros sous l'axe (les autres morceaux restent lisibles au survol). */
const MAX_X_LABELS = 12;
/** Largeur tant que le conteneur n'est pas mesuré (et dans les tests, sans ResizeObserver). */
const DEFAULT_WIDTH = 720;

/** Un morceau placé sur la courbe (null : pas de BPM, la courbe s'interrompt). */
interface CurvePoint {
  index: number;
  item: PlaylistItem;
  x: number;
  y: number | null;
}

/** Un segment entre deux morceaux analysés consécutifs, coloré par la qualité de l'enchaînement. */
interface CurveSegment {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  kind: TransitionView['kind'];
}

/** Courbe du BPM morceau par morceau d'une playlist ; chaque segment porte la qualité de l'enchaînement. */
@Component({
  selector: 'app-playlist-curve',
  imports: [DecimalPipe],
  templateUrl: './playlist-curve.component.html',
  styleUrl: './playlist-curve.component.scss',
})
export class PlaylistCurveComponent {
  readonly items = input.required<PlaylistItem[]>();

  protected readonly height = HEIGHT;
  protected readonly margin = MARGIN;
  protected readonly markerRadius = MARKER_RADIUS;
  /** Largeur réelle du conteneur (px) : le texte garde sa taille, même sur téléphone. */
  protected readonly width = signal(DEFAULT_WIDTH);
  /** Morceau survolé ou choisi au clavier, ou null. */
  protected readonly active = signal<number | null>(null);

  /** Zone du graphique, mesurée pour que le SVG ait la largeur réelle (pas de texte rétréci). */
  private readonly plot = viewChild<ElementRef<HTMLElement>>('plot');

  constructor() {
    effect((onCleanup) => {
      const element = this.plot()?.nativeElement;
      if (element === undefined || typeof ResizeObserver === 'undefined') {
        return;
      }
      const observer = new ResizeObserver(([entry]) => {
        if (entry.contentRect.width > 0) {
          this.width.set(entry.contentRect.width);
        }
      });
      observer.observe(element);
      onCleanup(() => observer.disconnect());
    });
  }

  /** BPM des morceaux analysés. */
  private readonly bpms = computed(() =>
    this.items().flatMap((item) => (item.track.bpm === null ? [] : [item.track.bpm])),
  );

  /** Vrai s'il y a de quoi tracer une courbe (au moins deux morceaux analysés). */
  protected readonly drawable = computed(() => this.bpms().length >= 2);

  /** Bornes de l'axe des BPM, arrondies à 5 (au moins 10 BPM d'écart). */
  protected readonly yDomain = computed(() => {
    const bpms = this.bpms();
    let low = Math.floor(Math.min(...bpms) / 5) * 5;
    let high = Math.ceil(Math.max(...bpms) / 5) * 5;
    if (high - low < 10) {
      low -= 5;
      high += 5;
    }
    return { low, high };
  });

  /** Valeurs de l'axe des BPM : un pas de 5, 10 ou 20 pour garder 3 à 6 graduations. */
  protected readonly yTicks = computed(() => {
    const { low, high } = this.yDomain();
    const step = [5, 10, 20, 40].find((s) => (high - low) / s <= 6) ?? 40;
    const ticks: number[] = [];
    for (let v = Math.ceil(low / step) * step; v <= high; v += step) {
      ticks.push(v);
    }
    return ticks.map((value) => ({ value, y: this.yOf(value) }));
  });

  /** Chaque morceau à sa place, avec sa hauteur (null sans BPM). */
  protected readonly points = computed((): CurvePoint[] => {
    const items = this.items();
    const plotWidth = this.width() - MARGIN.left - MARGIN.right;
    const step = items.length > 1 ? plotWidth / (items.length - 1) : 0;
    return items.map((item, index) => ({
      index,
      item,
      x: MARGIN.left + index * step,
      y: item.track.bpm === null ? null : this.yOf(item.track.bpm),
    }));
  });

  /** Points dessinés (au-delà de MAX_POINTS morceaux, la ligne seule reste lisible). */
  protected readonly markers = computed(() =>
    this.points().length > MAX_POINTS ? [] : this.points().filter((p) => p.y !== null),
  );

  /** Segments entre morceaux analysés consécutifs ; un morceau non analysé interrompt la courbe. */
  protected readonly segments = computed((): CurveSegment[] => {
    const points = this.points();
    const segments: CurveSegment[] = [];
    for (let i = 0; i < points.length - 1; i++) {
      const a = points[i];
      const b = points[i + 1];
      if (a.y !== null && b.y !== null) {
        const kind = describeTransition(a.item.transition_to_next).kind;
        segments.push({ x1: a.x, y1: a.y, x2: b.x, y2: b.y, kind });
      }
    }
    return segments;
  });

  /** Repères ⚠ au milieu des enchaînements refusés (la couleur n'est jamais le seul signal). */
  protected readonly warnings = computed(() =>
    this.segments()
      .filter((s) => s.kind === 'warn')
      .map((s) => ({ x: (s.x1 + s.x2) / 2, y: (s.y1 + s.y2) / 2 })),
  );

  /** Numéros sous l'axe : 1, puis un sur k pour en garder au plus MAX_X_LABELS, et le dernier. */
  protected readonly xLabels = computed(() => {
    const points = this.points();
    const every = Math.ceil(points.length / MAX_X_LABELS);
    return points.filter((p) => p.index % every === 0 || p.index === points.length - 1);
  });

  /** Étiquettes directes : seulement le BPM le plus bas et le plus haut. */
  protected readonly extremes = computed(() => {
    const analysed = this.points().filter((p) => p.y !== null);
    if (analysed.length < 2) {
      return [];
    }
    const bpm = (p: CurvePoint): number => p.item.track.bpm ?? 0;
    const lowest = analysed.reduce((a, b) => (bpm(b) < bpm(a) ? b : a));
    const highest = analysed.reduce((a, b) => (bpm(b) > bpm(a) ? b : a));
    return bpm(lowest) === bpm(highest)
      ? [{ point: highest, above: true }]
      : [
          { point: lowest, above: false },
          { point: highest, above: true },
        ];
  });

  /** Morceau survolé, avec le texte de l'enchaînement vers le suivant. */
  protected readonly tooltip = computed(() => {
    const index = this.active();
    const point = index === null ? undefined : this.points()[index];
    if (point === undefined) {
      return null;
    }
    const isLast = point.index === this.points().length - 1;
    return {
      point,
      next: isLast ? null : describeTransition(point.item.transition_to_next).text,
      /** L'infobulle passe à gauche de la ligne dans la moitié droite du graphique. */
      flip: point.x > this.width() / 2,
    };
  });

  /** Résumé lu par les lecteurs d'écran (la liste en dessous donne chaque valeur). */
  protected readonly summary = computed(() => {
    const bpms = this.bpms();
    const warn = this.segments().filter((s) => s.kind === 'warn').length;
    return (
      `Courbe des BPM de ${Math.min(...bpms).toFixed(0)} à ${Math.max(...bpms).toFixed(0)}, ` +
      `${warn} enchaînement${warn > 1 ? 's' : ''} à vérifier.`
    );
  });

  /** Suit le pointeur : le morceau le plus proche horizontalement devient actif. */
  protected onPointerMove(event: PointerEvent): void {
    const svg = event.currentTarget as SVGElement;
    const x = event.clientX - svg.getBoundingClientRect().left;
    const points = this.points();
    if (points.length === 0) {
      return;
    }
    const nearest = points.reduce((a, b) => (Math.abs(b.x - x) < Math.abs(a.x - x) ? b : a));
    this.active.set(nearest.index);
  }

  /** Flèches gauche / droite : morceau précédent / suivant ; Début / Fin : premier / dernier. */
  protected onKeydown(event: KeyboardEvent): void {
    const last = this.points().length - 1;
    const current = this.active() ?? 0;
    const next =
      event.key === 'ArrowRight'
        ? Math.min(current + 1, last)
        : event.key === 'ArrowLeft'
          ? Math.max(current - 1, 0)
          : event.key === 'Home'
            ? 0
            : event.key === 'End'
              ? last
              : null;
    if (next !== null) {
      event.preventDefault();
      this.active.set(next);
    }
  }

  /** Au focus clavier, le premier morceau est montré. */
  protected onFocus(): void {
    if (this.active() === null) {
      this.active.set(0);
    }
  }

  /** Hauteur (px) d'un BPM sur l'axe. */
  private yOf(bpm: number): number {
    const { low, high } = this.yDomain();
    const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
    return MARGIN.top + ((high - bpm) / (high - low)) * plotHeight;
  }
}
