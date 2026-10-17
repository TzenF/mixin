import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { AUDIO_FACTORY, AudioPlayerService, TRANSITION } from './audio-player.service';

/** Faux élément audio : on règle à la main sa durée, sa position et ses événements. */
class FakeAudio {
  src = '';
  preload = '';
  volume = 1;
  currentTime = 0;
  duration = Number.NaN;
  paused = true;
  ended = false;
  refusePlay = false;
  private readonly listeners = new Map<string, (() => void)[]>();

  /** Enregistre un écouteur. */
  addEventListener(event: string, listener: () => void): void {
    this.listeners.set(event, [...(this.listeners.get(event) ?? []), listener]);
  }

  /** Comme le vrai : retirer src vide la source. */
  removeAttribute(name: string): void {
    if (name === 'src') {
      this.src = '';
    }
  }

  /** Démarre la lecture, ou la refuse comme un navigateur qui bloque la lecture automatique. */
  play(): Promise<void> {
    if (this.refusePlay) {
      return Promise.reject(new Error('NotAllowedError'));
    }
    this.paused = false;
    return Promise.resolve();
  }

  /** Met en pause. */
  pause(): void {
    this.paused = true;
  }

  /** Déclenche un événement. */
  emit(event: string): void {
    for (const listener of this.listeners.get(event) ?? []) {
      listener();
    }
  }
}

/** Réponse de l'API pour un extrait qui expire dans 15 min. */
function preview(url: string): { url: string; expires_at: string } {
  return { url, expires_at: new Date(Date.now() + 15 * 60_000).toISOString() };
}

describe('AudioPlayerService', () => {
  let http: HttpTestingController;
  let audios: FakeAudio[];
  let player: AudioPlayerService;

  beforeEach(() => {
    audios = [];
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        {
          provide: AUDIO_FACTORY,
          useValue: () => {
            const audio = new FakeAudio();
            audios.push(audio);
            return audio as unknown as HTMLAudioElement;
          },
        },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    player = TestBed.inject(AudioPlayerService);
  });

  afterEach(() => {
    player.stop();
    vi.useRealTimers();
    http.verify();
  });

  /** Répond à la demande d'URL de ce morceau. */
  function answer(trackId: string, url = `https://cdn/${trackId}.mp3`): void {
    http.expectOne(`/api/tracks/${trackId}/preview`).flush(preview(url));
  }

  /** Laisse les promesses (play) se résoudre. */
  const flush = () => Promise.resolve();

  it('lit un morceau, le met en pause, le reprend', async () => {
    player.toggle('a');
    expect(player.state()).toBe('loading');
    answer('a');
    await flush();
    expect(audios[0].src).toBe('https://cdn/a.mp3');
    expect(player.state()).toBe('playing');

    player.toggle('a');
    expect([audios[0].paused, player.state()]).toEqual([true, 'paused']);
    player.toggle('a');
    await flush();
    expect(player.state()).toBe('playing');
    expect(audios.length).toBe(1); // pas de nouvel élément, pas de nouvel appel
  });

  it('ne joue qu’un son à la fois', async () => {
    player.toggle('a');
    answer('a');
    await flush();
    player.toggle('b');
    answer('b');
    await flush();

    expect(audios[0].paused).toBe(true);
    expect(audios[0].src).toBe('');
    expect(player.current()).toEqual({ kind: 'track', trackId: 'b' });
  });

  it('réutilise une URL encore valable, et redemande une URL bientôt expirée', async () => {
    player.toggle('a');
    answer('a');
    player.toggle('b');
    http
      .expectOne('/api/tracks/b/preview')
      .flush({ url: 'https://cdn/b.mp3', expires_at: new Date(Date.now() + 60_000).toISOString() });
    await flush();

    player.toggle('a'); // encore valable : pas d'appel
    http.expectNone('/api/tracks/a/preview');
    player.toggle('b'); // expire dans moins de 2 min : redemandée
    answer('b');
  });

  it('redemande une fois une URL expirée pendant l’écoute, puis abandonne', async () => {
    player.toggle('a');
    answer('a');
    await flush();
    audios[0].currentTime = 12;

    audios[0].emit('error'); // le CDN répond 403
    answer('a', 'https://cdn/a-neuf.mp3');
    await flush();
    expect([audios[0].src, audios[0].currentTime]).toEqual(['https://cdn/a-neuf.mp3', 12]);
    expect(player.state()).toBe('playing');

    audios[0].emit('error');
    expect(player.error()).toEqual({
      trackId: 'a',
      message: "L'extrait n'a pas pu être lu.",
      final: false,
    });
    expect(player.current()).toBeNull();
  });

  it('signale l’absence d’extrait (définitive) et Deezer indisponible (réessayable)', () => {
    player.toggle('a');
    http
      .expectOne('/api/tracks/a/preview')
      .flush(
        { detail: "Pas d'extrait : Deezer n'en propose pas", reason: 'no_preview' },
        { status: 404, statusText: '' },
      );
    expect(player.error()).toEqual({
      trackId: 'a',
      message: "Pas d'extrait : Deezer n'en propose pas",
      final: true,
    });

    player.toggle('b');
    http
      .expectOne('/api/tracks/b/preview')
      .flush({ detail: 'Deezer est indisponible' }, { status: 503, statusText: '' });
    expect(player.error()?.final).toBe(false);
  });

  it('transforme un refus de lecture du navigateur en message', async () => {
    player.toggle('a');
    const req = http.expectOne('/api/tracks/a/preview');
    req.flush(preview('https://cdn/a.mp3'));
    audios[0].refusePlay = true;
    audios[0].emit('error'); // force un nouvel essai de lecture
    answer('a');
    await flush();
    await flush();
    expect(player.error()?.message).toContain('refusé la lecture');
  });

  it('ignore les événements tardifs d’un extrait arrêté', async () => {
    player.toggle('a');
    answer('a');
    await flush();
    player.stop();

    audios[0].emit('error');
    audios[0].emit('ended');
    expect(player.error()).toBeNull();
  });

  describe('enchaînement', () => {
    /** Lance l'enchaînement a -> b, A dure `duration` secondes. */
    async function startTransition(duration = 30): Promise<[FakeAudio, FakeAudio]> {
      vi.useFakeTimers();
      player.toggleTransition('a', 'b');
      answer('a');
      answer('b');
      const [a, b] = audios;
      a.duration = duration;
      a.emit('loadedmetadata');
      await flush();
      return [a, b];
    }

    /** Place A à `t` secondes puis laisse passer un intervalle. */
    function at(a: FakeAudio, t: number): void {
      a.currentTime = t;
      vi.advanceTimersByTime(TRANSITION.tickMs);
    }

    it('joue les 10 dernières s de A, fond B pendant 4 s, puis 12 s de B', async () => {
      const [a, b] = await startTransition();
      expect(a.currentTime).toBe(20);
      expect(b.preload).toBe('auto'); // préchargé tout de suite
      expect(b.volume).toBe(0);

      at(a, 25.9);
      expect(b.paused).toBe(true);
      at(a, 26);
      expect([b.paused, b.currentTime]).toEqual([false, 0]);
      at(a, 28); // milieu du fondu : volumes croisés
      expect([a.volume, b.volume]).toEqual([0.5, 0.5]);
      at(a, 30);
      expect([a.volume, b.volume, a.paused]).toEqual([0, 1, true]);

      b.currentTime = TRANSITION.nextSeconds;
      vi.advanceTimersByTime(TRANSITION.tickMs);
      expect(player.current()).toBeNull(); // B s'arrête
      expect(player.lastFinished()).toEqual({ fromId: 'a', toId: 'b' }); // invite à le noter
    });

    it('s’adapte à un extrait plus court que 30 s', async () => {
      const [a] = await startTransition(20);
      expect(a.currentTime).toBe(10);
    });

    it('un second clic arrête l’enchaînement', async () => {
      const [a, b] = await startTransition();
      player.toggleTransition('a', 'b');
      expect([a.paused, b.paused, player.current()]).toEqual([true, true, null]);
    });

    it('dit lequel des deux morceaux n’a pas d’extrait', () => {
      player.toggleTransition('a', 'b');
      answer('a');
      http
        .expectOne('/api/tracks/b/preview')
        .flush({ detail: "Pas d'extrait" }, { status: 404, statusText: '' });
      expect(player.error()).toEqual({ trackId: 'b', message: "Pas d'extrait", final: true });
    });
  });
});
