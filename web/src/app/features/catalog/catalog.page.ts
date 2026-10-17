import { Component } from '@angular/core';
import { CurrentPlaylistBarComponent } from '../../shared/current-playlist-bar/current-playlist-bar.component';
import { TrackBrowserComponent } from '../../shared/track-browser/track-browser.component';

export { SEARCH_DELAY_MS } from '../../shared/track-browser/track-browser.component';

/** Page « Catalogue » : mes morceaux (ou tous), filtrés et triés, avec BPM et tonalité. */
@Component({
  selector: 'app-catalog-page',
  imports: [CurrentPlaylistBarComponent, TrackBrowserComponent],
  templateUrl: './catalog.page.html',
  styleUrl: './catalog.page.scss',
})
export class CatalogPage {}
