import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

/** Composant racine : affiche la page correspondant à l'URL. */
@Component({
  imports: [RouterOutlet],
  selector: 'app-root',
  template: '<router-outlet />',
})
export class App {}
