import { PlaylistDetail, PlaylistItem } from '../core/api/playlist.service';
import { describeTransition } from './key-moves';

/** « detailed » : pour préparer un set (BPM, tonalité, enchaînements) ; « tracklist » : à partager. */
export type PlaylistTextFormat = 'detailed' | 'tracklist';

/** Texte de la playlist, prêt à enregistrer dans un fichier .txt. */
export function playlistText(
  playlist: PlaylistDetail,
  format: PlaylistTextFormat,
  today: Date = new Date(),
): string {
  const items = playlist.items;
  const width = Math.max(2, String(items.length).length);
  const lines = [playlist.name];

  if (format === 'detailed') {
    const transitions = items.slice(0, -1).map((i) => describeTransition(i.transition_to_next));
    const warn = transitions.filter((t) => t.kind === 'warn').length;
    lines.push(
      `${plural(items.length, 'titre')} · ${plural(warn, 'enchaînement')} ⚠ · exportée le ${frenchDate(today)}`,
    );
  }
  lines.push('');

  items.forEach((item, i) => {
    const number = String(i + 1).padStart(width, '0');
    lines.push(
      `${number}. ${trackLabel(item)}${format === 'detailed' ? ` · ${values(item)}` : ''}`,
    );
    if (format === 'detailed' && i < items.length - 1) {
      lines.push(`${' '.repeat(width + 2)}${describeTransition(item.transition_to_next).text}`);
    }
  });
  return lines.join('\n') + '\n';
}

/** Nom du fichier : nom de la playlist sans caractères interdits par Windows ou macOS. */
export function playlistFileName(name: string, format: PlaylistTextFormat): string {
  const safe = name.replace(/[\\/:*?"<>|\u0000-\u001f]/g, '-').trim() || 'playlist';
  return format === 'detailed' ? `${safe}.txt` : `${safe} (tracklist).txt`;
}

/** « Artiste 1, Artiste 2 – Titre » (ou le titre seul s'il n'y a pas d'artiste). */
function trackLabel(item: PlaylistItem): string {
  const artists = item.track.artists.join(', ');
  return artists ? `${artists} – ${item.track.title}` : item.track.title;
}

/** « 124.0 BPM · 6A », avec « ? » pour une valeur inconnue. */
function values(item: PlaylistItem): string {
  const bpm = item.track.bpm === null ? '? BPM' : `${item.track.bpm.toFixed(1)} BPM`;
  return `${bpm} · ${item.track.camelot ?? '?'}`;
}

/** « 1 titre », « 3 titres ». */
function plural(count: number, word: string): string {
  return `${count} ${word}${count > 1 ? 's' : ''}`;
}

/** Date au format JJ/MM/AAAA. */
function frenchDate(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()}`;
}
