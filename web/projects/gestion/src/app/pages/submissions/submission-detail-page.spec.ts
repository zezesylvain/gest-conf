import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { MeEdition } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';
import { of } from 'rxjs';

import { CHAIR_EDITION, provideGestionTesting } from '../../../testing/gestion-testing';
import { EditionApi } from '../../core/edition-api';
import { SubmissionsApi } from '../../core/submissions-api';
import { SubmissionDetailPage } from './submission-detail-page';
import { detail } from './testing';

const OC: MeEdition = {
  ...CHAIR_EDITION,
  roles: [{ role: 'OC_MEMBER', oc_function: 'finance' }],
  capabilities: ['edition.read', 'submissions.read'],
};

describe('SubmissionDetailPage', () => {
  let api: Record<string, ReturnType<typeof vi.fn>>;

  async function render(edition: MeEdition = CHAIR_EDITION, value = detail()) {
    api = {
      get: vi.fn().mockResolvedValue(value),
      grantExtension: vi.fn().mockResolvedValue(
        detail({
          extensions: [
            {
              id: 5,
              until: '2026-10-20T10:00:00Z',
              reason: 'Panne',
              granted_by_name: 'Présidente',
              granted_at: '2026-10-05T10:00:00Z',
              revoked_at: null,
              is_active: true,
            },
          ],
        }),
      ),
      revokeExtension: vi.fn().mockResolvedValue(detail()),
    };
    TestBed.configureTestingModule({
      providers: [
        ...provideGestionTesting([edition]),
        { provide: SubmissionsApi, useValue: api },
        {
          provide: EditionApi,
          useValue: { edition: vi.fn().mockResolvedValue({ timezone: 'Africa/Abidjan' }) },
        },
        { provide: MatDialog, useValue: { open: () => ({ afterClosed: () => of(true) }) } },
      ],
    });
    await useTestLanguage('fr');
    const fixture = TestBed.createComponent(SubmissionDetailPage);
    fixture.componentRef.setInput('editionId', '3');
    fixture.componentRef.setInput('submissionId', '7');
    await fixture.whenStable();
    fixture.detectChanges();
    return { fixture, root: fixture.nativeElement as HTMLElement };
  }

  it('auteurs avec adresse, versions du PDF par l’endpoint authentifié, historique', async () => {
    const { root } = await render();
    expect(api['get']).toHaveBeenCalledWith(3, 7);
    expect(root.querySelector('h1')!.textContent).toContain('GC27-0001');
    expect(root.querySelector('a[href="mailto:awa@univ.ci"]')).not.toBeNull();
    const files = Array.from(root.querySelectorAll<HTMLAnchorElement>('a[download]'));
    expect(files.map((a) => a.getAttribute('href'))).toEqual([
      '/api/v1/manage/editions/3/submissions/7/files/12/content',
      '/api/v1/manage/editions/3/submissions/7/files/11/content',
    ]);
    expect(root.textContent).toContain('version courante');
    expect(root.textContent).toContain('Awa Koné');
    expect(root.textContent).toContain('Aucune dérogation.');
  });

  it('RG-02 : dérogation accordée (échéance à l’heure de l’édition, motif)', async () => {
    const { fixture, root } = await render();
    const page = fixture.componentInstance as unknown as {
      extensionForm: { setValue(v: object): void };
      grant(): Promise<void>;
    };
    page.extensionForm.setValue({ until_local: '2026-10-20T10:00', reason: ' Panne ' });
    await page.grant();
    fixture.detectChanges();
    expect(api['grantExtension']).toHaveBeenCalledWith(3, 7, {
      until_local: '2026-10-20T10:00',
      reason: 'Panne',
    });
    expect(root.textContent).toContain('Dérogation accordée');
    expect(root.textContent).toContain('en cours');
  });

  it('RG-02 : motif obligatoire, aucun appel sinon', async () => {
    const { fixture } = await render();
    const page = fixture.componentInstance as unknown as {
      extensionForm: { setValue(v: object): void };
      grant(): Promise<void>;
    };
    page.extensionForm.setValue({ until_local: '2026-10-20T10:00', reason: '' });
    await page.grant();
    expect(api['grantExtension']).not.toHaveBeenCalled();
  });

  it('révocation après confirmation', async () => {
    const extension = {
      id: 5,
      until: '2026-10-20T10:00:00Z',
      reason: 'Panne',
      granted_by_name: 'Présidente',
      granted_at: '2026-10-05T10:00:00Z',
      revoked_at: null,
      is_active: true,
    };
    const { fixture, root } = await render(CHAIR_EDITION, detail({ extensions: [extension] }));
    Array.from(root.querySelectorAll('button'))
      .find((button) => button.textContent!.includes('Révoquer'))!
      .click();
    await fixture.whenStable();
    expect(api['revokeExtension']).toHaveBeenCalledWith(3, 7, 5);
  });

  it('CO ou soumission en recevabilité : pas de formulaire de dérogation', async () => {
    let { root } = await render(OC);
    expect(root.querySelector('input[type=datetime-local]')).toBeNull();
    TestBed.resetTestingModule();
    ({ root } = await render(CHAIR_EDITION, detail({ status: 'screening', can_extend: false })));
    expect(root.querySelector('input[type=datetime-local]')).toBeNull();
  });
});
