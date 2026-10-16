import { ComponentFixture, TestBed } from '@angular/core/testing';
import { CurrentPlaylistService } from '../../core/current-playlist.service';
import { FakeCurrentPlaylistService } from '../../core/current-playlist.service.fake';
import { AddToPlaylistComponent } from './add-to-playlist.component';

describe('AddToPlaylistComponent', () => {
  let playlist: FakeCurrentPlaylistService;

  /** Affiche le bouton pour le morceau t1. */
  async function render(): Promise<ComponentFixture<AddToPlaylistComponent>> {
    playlist = new FakeCurrentPlaylistService();
    TestBed.configureTestingModule({
      imports: [AddToPlaylistComponent],
      providers: [{ provide: CurrentPlaylistService, useValue: playlist }],
    });
    const fixture = TestBed.createComponent(AddToPlaylistComponent);
    fixture.componentRef.setInput('trackId', 't1');
    fixture.detectChanges();
    await fixture.whenStable();
    return fixture;
  }

  /** Le bouton du composant. */
  function button(fixture: ComponentFixture<AddToPlaylistComponent>): HTMLButtonElement {
    return (fixture.nativeElement as HTMLElement).querySelector('button')!;
  }

  it('est désactivé sans playlist en cours, et explique pourquoi', async () => {
    const fixture = await render();
    expect(button(fixture).disabled).toBe(true);
    expect(button(fixture).title).toContain("Choisis d'abord une playlist");
  });

  it('ajoute le morceau puis indique qu’il est ajouté', async () => {
    const fixture = await render();
    playlist.select('current');
    fixture.detectChanges();
    expect(button(fixture).title).toBe('Ajouter à « Set en cours »');

    button(fixture).click();
    fixture.detectChanges();

    expect(playlist.added).toEqual(['t1']);
    expect(button(fixture).textContent).toContain('✓ Ajouté');
    expect(button(fixture).disabled).toBe(true);
  });
});
