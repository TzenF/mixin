import { Injectable } from '@angular/core';

/** Fait enregistrer un fichier par le navigateur (sans passer par le serveur). */
@Injectable({ providedIn: 'root' })
export class FileDownloadService {
  /** Propose d'enregistrer ce texte (UTF-8) sous ce nom de fichier. */
  saveText(fileName: string, content: string): void {
    const url = URL.createObjectURL(new Blob([content], { type: 'text/plain;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = fileName;
    link.click();
    // Libéré après coup : le téléchargement doit avoir démarré avant.
    setTimeout(() => URL.revokeObjectURL(url));
  }
}
