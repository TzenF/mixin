import { KeyMove } from '../core/api/catalog.service';
import { Transition } from '../core/api/playlist.service';

/** Libellé de chaque type d'enchaînement de tonalité (suggestions, playlists). */
export const KEY_MOVE_LABELS: Record<KeyMove, string> = {
  same: 'Même tonalité',
  adjacent: 'Tonalité voisine',
  relative: 'Relative (mineur ↔ majeur)',
  diagonal: 'Diagonale (±1 et mineur ↔ majeur)',
  energy_shift: "Saut de 2 (montée d'énergie)",
};

/** Écart de BPM signé, pour l'affichage : « +1,2 % », « −3,0 % », « 0,0 % ». */
export function formatBpmChange(percent: number): string {
  const sign = percent > 0 ? '+' : percent < 0 ? '−' : '';
  return `${sign}${Math.abs(percent).toFixed(1).replace('.', ',')} %`;
}

/** Enchaînement affiché entre deux morceaux : bon, à vérifier (⚠) ou inconnu (morceau non analysé). */
export interface TransitionView {
  kind: 'ok' | 'warn' | 'unknown';
  text: string;
}

/** Texte de l'enchaînement : « → +0,8 % · Tonalité voisine », « ⚠ tempo +8,0 % », « ⚠ tonalité éloignée (5 crans) »… */
export function describeTransition(t: Transition | null): TransitionView {
  if (t === null) {
    return { kind: 'unknown', text: '? Enchaînement inconnu (morceau non analysé)' };
  }
  const tempo = t.half_double ? '½ / ×2 tempo' : formatBpmChange(t.bpm_change);
  if (t.compatible && t.key_move) {
    return { kind: 'ok', text: `→ ${tempo} · ${KEY_MOVE_LABELS[t.key_move]}` };
  }
  const problems = [];
  if (!t.key_move) {
    const steps = `${t.key_distance} cran${t.key_distance > 1 ? 's' : ''}`;
    problems.push(
      t.same_mode
        ? `tonalité éloignée (${steps})`
        : `tonalité incompatible (${steps} et mineur ↔ majeur)`,
    );
  }
  if (!t.tempo_ok) {
    problems.push(`tempo ${formatBpmChange(t.bpm_change)}`);
  }
  return { kind: 'warn', text: `⚠ ${problems.join(' et ')}` };
}
