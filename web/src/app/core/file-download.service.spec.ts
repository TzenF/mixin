import { TestBed } from '@angular/core/testing';
import { FileDownloadService } from './file-download.service';

describe('FileDownloadService', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('fait enregistrer le texte sous le nom donné, puis libère la mémoire', async () => {
    vi.useFakeTimers();
    // jsdom ne fournit pas ces deux fonctions : on les simule.
    const created: Blob[] = [];
    URL.createObjectURL = vi.fn((blob: Blob) => {
      created.push(blob);
      return 'blob:fichier';
    });
    URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      expect(this.download).toBe('Set.txt');
      expect(this.href).toBe('blob:fichier');
    });

    TestBed.inject(FileDownloadService).saveText('Set.txt', 'Losing It\n');

    expect(click).toHaveBeenCalledOnce();
    expect(await created[0].text()).toBe('Losing It\n');
    expect(created[0].type).toBe('text/plain;charset=utf-8');
    expect(URL.revokeObjectURL).not.toHaveBeenCalled();
    vi.runAllTimers();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:fichier');
  });
});
