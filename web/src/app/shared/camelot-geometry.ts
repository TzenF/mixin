/** Géométrie de la roue de Camelot, partagée par les roues (parcours d'une playlist, carte de la bibliothèque). */

/** Anneau d'une tonalité : B (majeur) dehors, A (mineur) dedans. */
export type Ring = 'A' | 'B';

/** Les 24 tonalités dans l'ordre de la roue : 1A, 1B, 2A… 12B. */
export const CAMELOT_KEYS: readonly string[] = Array.from({ length: 12 }, (_, i) => [
  `${i + 1}A`,
  `${i + 1}B`,
]).flat();

/** Anneau d'une tonalité Camelot (« 8B » → B). */
export function ringOf(key: string): Ring {
  return key.endsWith('B') ? 'B' : 'A';
}

/** Point de la roue au numéro `number` (le 1 en haut, sens des aiguilles d'une montre), au rayon `r`. */
export function wheelPoint(number: number, r: number, center: number): { x: number; y: number } {
  const angle = ((number - 1) * 30 - 90) * (Math.PI / 180);
  return { x: center + r * Math.cos(angle), y: center + r * Math.sin(angle) };
}
