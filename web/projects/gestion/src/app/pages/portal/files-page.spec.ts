import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { MeEdition, PublicFile } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';
import { of } from 'rxjs';

import { CHAIR_EDITION, provideGestionTesting } from '../../../testing/gestion-testing';
import { PortalApi, PortalFilesApi } from '../../core/portal-api';
import { FilesPage } from './files-page';

const WRITER: MeEdition = {
  ...CHAIR_EDITION,
  capabilities: [...CHAIR_EDITION.capabilities, 'portal.write'],
};

function file(id: number, kind: 'document' | 'image', uses: string[] = []): PublicFile {
  return {
    id,
    uuid: `00000000-0000-0000-0000-00000000000${id}`,
    kind,
    original_name: kind === 'image' ? 'affiche.png' : 'appel.pdf',
    url: `/api/v1/public/files/x/${id}`,
    preview_url: `/api/v1/manage/editions/3/portal/files/${id}/content`,
    title_fr: `F${id}`,
    extension: kind === 'image' ? 'png' : 'pdf',
    content_type: kind === 'image' ? 'image/png' : 'application/pdf',
    size: 2048,
    width: kind === 'image' ? 800 : null,
    height: kind === 'image' ? 400 : null,
    position: id,
    published: true,
    uses,
    created_at: '2026-10-05T10:00:00Z',
  };
}

describe('FilesPage', () => {
  let files: Record<string, ReturnType<typeof vi.fn>>;

  async function render() {
    files = {
      files: vi.fn().mockResolvedValue([file(1, 'document'), file(2, 'image', ['section a'])]),
      poster: vi.fn().mockResolvedValue({ file: null, poster: null }),
      upload: vi.fn().mockResolvedValue(file(3, 'document')),
      setPoster: vi.fn().mockResolvedValue({ file: 2, poster: null }),
      update: vi.fn().mockResolvedValue(file(1, 'document')),
      remove: vi.fn(),
    };
    TestBed.configureTestingModule({
      providers: [
        ...provideGestionTesting([WRITER]),
        { provide: PortalFilesApi, useValue: files },
        {
          provide: PortalApi,
          useValue: {
            status: vi.fn().mockResolvedValue({
              last_published_at: null,
              release: '',
              pending_changes: 0,
              pending_since: null,
            }),
          },
        },
        { provide: MatDialog, useValue: { open: () => ({ afterClosed: () => of(true) }) } },
      ],
    });
    await useTestLanguage('fr');
    const fixture = TestBed.createComponent(FilesPage);
    fixture.componentRef.setInput('editionId', '3');
    await fixture.whenStable();
    fixture.detectChanges();
    return { fixture, root: fixture.nativeElement as HTMLElement };
  }

  it('documents et images séparés ; usages affichés ; taille lisible', async () => {
    const { root } = await render();
    const text = root.textContent ?? '';
    expect(text).toContain('section a');
    expect(text).toContain('2 Ko');
    expect(root.querySelectorAll('img.thumb')).toHaveLength(1);
  });

  it('envoi : fichier et nature transmis au serveur', async () => {
    const { fixture, root } = await render();
    const input = root.querySelector<HTMLInputElement>('input[type=file]')!;
    const pdf = new File(['%PDF-1.7'], 'appel.pdf', { type: 'application/pdf' });
    Object.defineProperty(input, 'files', { value: [pdf] });
    input.dispatchEvent(new Event('change'));
    const send = Array.from(root.querySelectorAll('button')).find((b) =>
      b.textContent!.includes('Envoyer'),
    )!;
    send.click();
    await fixture.whenStable();
    expect(files['upload']).toHaveBeenCalledWith(3, pdf, 'document', '', '');
  });

  it('sans fichier choisi : message, aucun envoi', async () => {
    const { fixture, root } = await render();
    Array.from(root.querySelectorAll('button'))
      .find((b) => b.textContent!.includes('Envoyer'))!
      .click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(files['upload']).not.toHaveBeenCalled();
    expect(root.textContent).toContain('Choisissez d’abord un fichier'.replace('’', "'"));
  });

  it('affiche : enregistrée par le serveur', async () => {
    const { fixture } = await render();
    await (
      fixture.componentInstance as unknown as { savePoster: (v: number | null) => Promise<void> }
    ).savePoster(2);
    expect(files['setPoster']).toHaveBeenCalledWith(3, 2);
  });
});
