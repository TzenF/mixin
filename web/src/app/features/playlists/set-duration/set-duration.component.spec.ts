import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { CatalogTrack } from '../../../core/api/catalog.service';
import { PlaylistDetail } from '../../../core/api/playlist.service';
import { SetDurationComponent } from './set-duration.component';

/** Morceau de test de 4 min. */
function track(id: string, title: string): CatalogTrack {
  return {
    id,
    title,
    artists: [],
    bpm: 124,
    camelot: '6A',
    bpm_source: null,
    key_source: null,
    key_confidence: null,
    analysis_status: 'done',
    favorite: false,
    mine: true,
    duration_ms: 240_000,
  };
}

/** Playlist de 5 morceaux de 4 min (20 min) avec ces réglages. */
function playlist(slot: number | null, percent = 100): PlaylistDetail {
  return {
    id: 'set',
    name: 'Set',
    source_provider: null,
    track_count: 5,
    updated_at: '2026-10-18T10:00:00Z',
    slot_minutes: slot,
    played_percent: percent,
    spotify_export: null,
    items: ['A', 'B', 'C', 'D', 'E'].map((t, i) => ({
      item_id: i + 1,
      position: i,
      track: track(t.toLowerCase(), t),
      transition_to_next: null,
      my_rating: null,
    })),
  };
}

describe('SetDurationComponent', () => {
  let http: HttpTestingController;

  /** Affiche le panneau pour cette playlist. */
  async function render(p: PlaylistDetail): Promise<ComponentFixture<SetDurationComponent>> {
    TestBed.configureTestingModule({
      imports: [SetDurationComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(SetDurationComponent);
    fixture.componentRef.setInput('playlist', p);
    fixture.detectChanges();
    await fixture.whenStable();
    return fixture;
  }

  afterEach(() => http.verify());

  /** Raccourci : élément portant ce data-testid. */
  function byTestId<T extends HTMLElement = HTMLElement>(
    fixture: ComponentFixture<SetDurationComponent>,
    id: string,
  ): T | null {
    return (fixture.nativeElement as HTMLElement).querySelector<T>(`[data-testid="${id}"]`);
  }

  it('affiche la durée, et ce qu’il reste dans le créneau', async () => {
    const fixture = await render(playlist(30, 75));

    expect(byTestId(fixture, 'set-total')?.textContent).toContain('15 min'); // 20 min à 75 %
    expect(byTestId(fixture, 'set-fits')?.textContent).toContain('il reste 15 min');
    expect(byTestId(fixture, 'propose-cut')).toBeNull();
  });

  it('enregistre le créneau et la part jouée', async () => {
    const fixture = await render(playlist(null));
    const changed = vi.fn();
    fixture.componentInstance.changed.subscribe(changed);
    byTestId<HTMLInputElement>(fixture, 'slot-input')!.value = '12';
    byTestId<HTMLInputElement>(fixture, 'percent-input')!.value = '80';
    byTestId(fixture, 'save-settings')!.click();

    const req = http.expectOne('/api/playlists/set');
    expect([req.request.method, req.request.body]).toEqual([
      'PATCH',
      { slot_minutes: 12, played_percent: 80 },
    ]);
    req.flush({});
    expect(changed).toHaveBeenCalledTimes(1);
  });

  it('refuse une part jouée hors de 50 à 100 %', async () => {
    const fixture = await render(playlist(null));
    byTestId<HTMLInputElement>(fixture, 'percent-input')!.value = '30';
    byTestId(fixture, 'save-settings')!.click();
    fixture.detectChanges();

    expect(byTestId(fixture, 'settings-error')?.textContent).toContain('50 à 100 %');
  });

  it('si ça dépasse, propose quoi retirer puis l’applique', async () => {
    const fixture = await render(playlist(12));
    const changed = vi.fn();
    fixture.componentInstance.changed.subscribe(changed);
    expect(byTestId(fixture, 'set-over')?.textContent).toContain('8 min de trop');

    byTestId(fixture, 'propose-cut')!.click();
    http.expectOne('/api/playlists/set/cut-proposal').flush({
      remove_item_ids: [3, 5],
      total_ms: 1_200_000,
      total_after_ms: 720_000,
      slot_ms: 720_000,
      refused_before: 1,
      refused_after: 0,
    });
    fixture.detectChanges();
    const items = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('[data-testid="cut-item"]'),
    ).map((li) => li.textContent?.trim());
    expect(items).toEqual(['3. C', '5. E']);
    expect(byTestId(fixture, 'cut-proposal')?.textContent).toContain('(−8 min) → 12 min');

    byTestId(fixture, 'apply-cut')!.click();
    const req = http.expectOne('/api/playlists/set/items/remove');
    expect(req.request.body).toEqual({ item_ids: [3, 5] });
    req.flush(null);
    expect(changed).toHaveBeenCalledTimes(1);
  });
});
