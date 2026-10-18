/** Durée lisible d'un set : « 1 h 12 », « 47 min », « 0 min ». */
export function formatDuration(ms: number): string {
  const minutes = Math.round(ms / 60_000);
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return hours > 0 ? `${hours} h ${rest.toString().padStart(2, '0')}` : `${minutes} min`;
}

/** Heure de passage ou durée d'un morceau : « 3:24 », « 1:03:24 ». */
export function formatClock(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = (seconds % 60).toString().padStart(2, '0');
  return h > 0 ? `${h}:${m.toString().padStart(2, '0')}:${s}` : `${m}:${s}`;
}

/** Durée comptée d'un morceau : sa durée entière réduite à la part jouée (comme le serveur, à la ms près). */
export function playedDuration(
  durationMs: number | null | undefined,
  playedPercent: number,
): number {
  return Math.floor(((durationMs ?? 0) * playedPercent) / 100);
}
