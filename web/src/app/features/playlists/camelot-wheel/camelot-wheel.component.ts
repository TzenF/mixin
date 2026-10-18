import { Component, computed, input, signal } from '@angular/core';
import { PlaylistItem } from '../../../core/api/playlist.service';
import { CAMELOT_KEYS, Ring, ringOf, wheelPoint } from '../../../shared/camelot-geometry';

/** Taille de la roue (px, carré) et rayons des deux anneaux : B (majeur) dehors, A (mineur) dedans. */
const SIZE = 300;
const CENTER = SIZE / 2;
const RADIUS = { B: 108, A: 70 };
/** Point d'une tonalité jouée, et sa zone de survol (24 px de diamètre). */
const NODE_RADIUS = 6;
const HIT_RADIUS = 12;
/** Repère d'une tonalité non jouée (le parcours reste au premier plan). */
const IDLE_RADIUS = 2;
/** Distance des noms au point : dehors pour l'anneau B (comme les numéros), vers le centre pour A. */
const LABEL_OFFSET = { B: 20, A: -24 };
/** Rayon de l'anneau autour du premier et du dernier morceau, et de la pastille ⚠. */
const END_RING_RADIUS = NODE_RADIUS + 4;
const WARNING_RADIUS = 8;
/** Au-delà, le parcours devient une pelote : seules les tonalités jouées restent. */
const MAX_PATH_ITEMS = 100;

/** Une tonalité de la roue, jouée ou non. */
interface WheelKey {
  key: string;
  ring: Ring;
  x: number;
  y: number;
  label: { x: number; y: number };
  /** « début », « fin », « début · fin » ou null. */
  tag: string | null;
  /** Morceaux joués dans cette tonalité (place 1, 2… et titre). */
  tracks: { place: number; title: string }[];
}

/** Un passage entre deux tonalités, dans un sens ou dans l'autre (dessiné une seule fois). */
interface WheelMove {
  id: string;
  /** Tracé SVG : arc le long de l'anneau, ou trait droit d'un anneau à l'autre. */
  path: string;
  middle: { x: number; y: number };
  /** ok : tonalité compatible ; warn : incompatible ; unknown : enchaînement non calculé. */
  kind: 'ok' | 'warn' | 'unknown';
  /** Épaisseur selon le nombre de passages (1 à 3 fois et plus). */
  width: number;
}

/** Point de la roue au numéro `number` et au rayon `r`. */
function at(number: number, r: number): { x: number; y: number } {
  return wheelPoint(number, r, CENTER);
}

/** Position d'une tonalité sur son anneau. */
function position(key: string): { x: number; y: number } {
  return at(Number.parseInt(key, 10), RADIUS[ringOf(key)]);
}

/** Tracé d'un passage : sur un même anneau, un arc (qui suit la roue pour 1 cran, courbé vers le centre au-delà,
 * pour ne pas recouvrir les voisins) ; d'un anneau à l'autre, un trait droit. */
function movePath(from: string, to: string): { path: string; middle: { x: number; y: number } } {
  const a = position(from);
  const b = position(to);
  if (ringOf(from) !== ringOf(to)) {
    return {
      path: `M ${a.x} ${a.y} L ${b.x} ${b.y}`,
      middle: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 },
    };
  }
  const na = Number.parseInt(from, 10);
  let steps = Number.parseInt(to, 10) - na;
  if (steps > 6) steps -= 12;
  if (steps < -6) steps += 12;
  const r = RADIUS[ringOf(from)];
  const control =
    Math.abs(steps) === 1
      ? at(na + steps / 2, r / Math.cos(Math.PI / 12))
      : at(na + steps / 2, r * 0.62);
  // Milieu d'une courbe de Bézier quadratique : (a + 2c + b) / 4.
  const middle = { x: (a.x + 2 * control.x + b.x) / 4, y: (a.y + 2 * control.y + b.y) / 4 };
  return { path: `M ${a.x} ${a.y} Q ${control.x} ${control.y} ${b.x} ${b.y}`, middle };
}

/** Roue de Camelot : tonalités jouées dans la playlist et passages de l'une à l'autre. */
@Component({
  selector: 'app-camelot-wheel',
  templateUrl: './camelot-wheel.component.html',
  styleUrl: './camelot-wheel.component.scss',
})
export class CamelotWheelComponent {
  readonly items = input.required<PlaylistItem[]>();

  protected readonly size = SIZE;
  protected readonly center = CENTER;
  protected readonly radius = RADIUS;
  protected readonly nodeRadius = NODE_RADIUS;
  protected readonly hitRadius = HIT_RADIUS;
  protected readonly idleRadius = IDLE_RADIUS;
  protected readonly endRingRadius = END_RING_RADIUS;
  protected readonly warningRadius = WARNING_RADIUS;
  /** Tonalité survolée ou choisie au clavier, ou null. */
  protected readonly active = signal<string | null>(null);

  /** Tonalités du premier et du dernier morceau qui en ont une. */
  private readonly ends = computed(() => {
    const keys = this.items().flatMap((i) => (i.track.camelot === null ? [] : [i.track.camelot]));
    return { first: keys[0] ?? null, last: keys[keys.length - 1] ?? null };
  });

  /** Les 24 tonalités, avec les morceaux joués dans chacune. */
  protected readonly keys = computed((): WheelKey[] => {
    const byKey = new Map<string, { place: number; title: string }[]>();
    this.items().forEach((item, i) => {
      if (item.track.camelot !== null) {
        const list = byKey.get(item.track.camelot) ?? [];
        list.push({ place: i + 1, title: item.track.title });
        byKey.set(item.track.camelot, list);
      }
    });
    const { first, last } = this.ends();
    return CAMELOT_KEYS.map((key) => {
      const ring = ringOf(key);
      const tag =
        key === first && key === last
          ? 'début · fin'
          : key === first
            ? 'début'
            : key === last
              ? 'fin'
              : null;
      return {
        key,
        ring,
        ...position(key),
        label: at(Number.parseInt(key, 10), RADIUS[ring] + LABEL_OFFSET[ring]),
        tag,
        tracks: byKey.get(key) ?? [],
      };
    });
  });

  /** Tonalités jouées, dans l'ordre de la roue (parcourues au clavier). */
  protected readonly played = computed(() => this.keys().filter((k) => k.tracks.length > 0));

  /** Numéros 1 à 12 autour de la roue, sauf quand le nom d'une tonalité B jouée le donne déjà. */
  protected readonly numbers = computed(() => {
    const playedB = new Set(
      this.played()
        .filter((k) => k.ring === 'B')
        .map((k) => k.key),
    );
    return Array.from({ length: 12 }, (_, i) => i + 1)
      .filter((n) => !playedB.has(`${n}B`))
      .map((n) => ({ n, ...at(n, RADIUS.B + LABEL_OFFSET.B) }));
  });

  /** Vrai s'il y a de quoi dessiner (au moins deux morceaux avec une tonalité). */
  protected readonly drawable = computed(
    () => this.items().filter((i) => i.track.camelot !== null).length >= 2,
  );

  /** Passages entre tonalités de morceaux consécutifs, un trait par paire (aucun si la playlist est trop longue). */
  protected readonly moves = computed((): WheelMove[] => {
    const items = this.items();
    if (items.length > MAX_PATH_ITEMS) {
      return [];
    }
    const pairs = new Map<
      string,
      { from: string; to: string; count: number; kind: WheelMove['kind'] }
    >();
    for (let i = 0; i < items.length - 1; i++) {
      const from = items[i].track.camelot;
      const to = items[i + 1].track.camelot;
      if (from === null || to === null || from === to) {
        continue;
      }
      // La compatibilité de tonalité ne dépend pas du sens : 8A → 9A et 9A → 8A sont un même trait.
      const id = [from, to].sort().join('-');
      const t = items[i].transition_to_next;
      const kind = t === null ? 'unknown' : t.key_move === null ? 'warn' : 'ok';
      const pair = pairs.get(id) ?? { from, to, count: 0, kind };
      pair.count++;
      if (pair.kind === 'unknown') {
        pair.kind = kind;
      }
      pairs.set(id, pair);
    }
    return [...pairs.entries()].map(([id, p]) => ({
      id,
      ...movePath(p.from, p.to),
      kind: p.kind,
      width: Math.min(1 + p.count, 4),
    }));
  });

  /** Pastilles ⚠ au milieu des passages de tonalité incompatibles (la couleur n'est jamais le seul signal). */
  protected readonly warnings = computed(() =>
    this.moves()
      .filter((m) => m.kind === 'warn')
      .map((m) => ({ id: m.id, ...m.middle })),
  );

  /** Anneaux autour du premier et du dernier morceau. */
  protected readonly endRings = computed(() => {
    const { first, last } = this.ends();
    return [...new Set([first, last])].flatMap((key) =>
      key === null ? [] : [{ key, ...position(key) }],
    );
  });

  /** Tonalité survolée et ses morceaux. */
  protected readonly tooltip = computed(() => {
    const key = this.active();
    return key === null ? null : (this.keys().find((k) => k.key === key) ?? null);
  });

  /** Résumé lu par les lecteurs d'écran (la liste en dessous donne la tonalité de chaque morceau). */
  protected readonly summary = computed(() => {
    const played = this.played().map((k) => k.key);
    const warn = this.warnings().length;
    const s = (n: number): string => (n > 1 ? 's' : '');
    return (
      `Roue de Camelot : ${played.length} tonalité${s(played.length)} jouée${s(played.length)} ` +
      `(${played.join(', ')}), ${warn} passage${s(warn)} de tonalité incompatible${s(warn)}.`
    );
  });

  /** Flèches : tonalité jouée suivante / précédente (dans l'ordre de la roue). */
  protected onKeydown(event: KeyboardEvent): void {
    const played = this.played();
    if (played.length === 0) {
      return;
    }
    const current = played.findIndex((k) => k.key === this.active());
    const step =
      event.key === 'ArrowRight' || event.key === 'ArrowDown'
        ? 1
        : event.key === 'ArrowLeft' || event.key === 'ArrowUp'
          ? -1
          : 0;
    if (step !== 0) {
      event.preventDefault();
      const next = current === -1 ? 0 : (current + step + played.length) % played.length;
      this.active.set(played[next].key);
    }
  }

  /** Au focus clavier, la première tonalité jouée est montrée. */
  protected onFocus(): void {
    if (this.active() === null) {
      this.active.set(this.played()[0]?.key ?? null);
    }
  }
}
