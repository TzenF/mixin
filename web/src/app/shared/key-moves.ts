import { KeyMove } from '../core/api/catalog.service';

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
