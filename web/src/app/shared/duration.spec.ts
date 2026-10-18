import { formatClock, formatDuration, playedDuration } from './duration';

describe('durées', () => {
  it('écrit la durée d’un set en heures et minutes', () => {
    expect([formatDuration(0), formatDuration(47 * 60_000), formatDuration(72 * 60_000)]).toEqual([
      '0 min',
      '47 min',
      '1 h 12',
    ]);
    expect(formatDuration(60 * 60_000 + 5 * 60_000)).toBe('1 h 05');
  });

  it('écrit une heure de passage', () => {
    expect([formatClock(0), formatClock(204_000), formatClock(3_804_000)]).toEqual([
      '0:00',
      '3:24',
      '1:03:24',
    ]);
  });

  it('réduit la durée à la part jouée', () => {
    expect([
      playedDuration(240_000, 75),
      playedDuration(null, 75),
      playedDuration(1001, 50),
    ]).toEqual([180_000, 0, 500]);
  });
});
