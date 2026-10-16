import { ComponentFixture, TestBed } from '@angular/core/testing';
import { CurrentPlaylistService } from '../../core/current-playlist.service';
import { FakeCurrentPlaylistService } from '../../core/current-playlist.service.fake';
import { CurrentPlaylistBarComponent } from './current-playlist-bar.component';

describe('CurrentPlaylistBarComponent', () => {
  let playlist: FakeCurrentPlaylistService;

  /** Affiche la barre. */
  async function render(): Promise<ComponentFixture<CurrentPlaylistBarComponent>> {
    playlist = new FakeCurrentPlaylistService();
    TestBed.configureTestingModule({
      imports: [CurrentPlaylistBarComponent],
      providers: [{ provide: CurrentPlaylistService, useValue: playlist }],
    });
    const fixture = TestBed.createComponent(CurrentPlaylistBarComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    return fixture;
  }

  /** Raccourci : élément portant ce data-testid. */
  function byTestId<T extends HTMLElement>(
    fixture: ComponentFixture<CurrentPlaylistBarComponent>,
    id: string,
  ) {
    return (fixture.nativeElement as HTMLElement).querySelector<T>(`[data-testid="${id}"]`)!;
  }

  it('recharge mes playlists et permet de choisir celle en cours', async () => {
    const fixture = await render();
    expect(playlist.refreshCount).toBe(1);

    const select = byTestId<HTMLSelectElement>(fixture, 'current-playlist');
    expect(select.options.length).toBe(2); // « aucune » + la playlist
    select.value = 'current';
    select.dispatchEvent(new Event('change'));

    expect(playlist.current()?.id).toBe('current');
  });

  it('crée une playlist qui devient la playlist en cours', async () => {
    const fixture = await render();
    byTestId(fixture, 'new-playlist').click();
    fixture.detectChanges();

    byTestId<HTMLInputElement>(fixture, 'new-playlist-name').value = '  Samedi  ';
    byTestId(fixture, 'create-playlist').click();
    fixture.detectChanges();

    expect(playlist.current()?.name).toBe('Samedi');
    expect(
      (fixture.nativeElement as HTMLElement).querySelector('[data-testid="new-playlist-name"]'),
    ).toBeNull();
  });
});
