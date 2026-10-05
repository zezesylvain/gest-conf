import { TestBed } from '@angular/core/testing';
import { MeEdition } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';

import { CHAIR_EDITION, provideGestionTesting } from '../../../testing/gestion-testing';
import { EditionApi } from '../../core/edition-api';
import { exportUrl, SubmissionsApi } from '../../core/submissions-api';
import { SubmissionsPage } from './submissions-page';
import { row } from './testing';

/** CO : lecture seule des soumissions, ni export ni dérogation (F10). */
const OC: MeEdition = {
  ...CHAIR_EDITION,
  roles: [{ role: 'OC_MEMBER', oc_function: 'finance' }],
  capabilities: ['edition.read', 'submissions.read'],
};

describe('SubmissionsPage (gestion)', () => {
  let api: Record<string, ReturnType<typeof vi.fn>>;

  async function render(edition: MeEdition = CHAIR_EDITION) {
    api = {
      list: vi.fn().mockResolvedValue({
        count: 2,
        next: null,
        previous: null,
        results: [
          row({ extension_until: '2026-10-20T10:00:00Z' }),
          row({ id: 8, reference: null, status: 'draft', title: '' }),
        ],
      }),
    };
    TestBed.configureTestingModule({
      providers: [
        ...provideGestionTesting([edition]),
        { provide: SubmissionsApi, useValue: api },
        {
          provide: EditionApi,
          useValue: {
            edition: vi.fn().mockResolvedValue({ timezone: 'Africa/Abidjan' }),
            tracks: vi.fn().mockResolvedValue([{ id: 1, code: 'ia', name_fr: 'IA' }]),
            submissionTypes: vi.fn().mockResolvedValue([{ id: 1, code: 'oral', label_fr: 'Oral' }]),
          },
        },
      ],
    });
    await useTestLanguage('fr');
    const fixture = TestBed.createComponent(SubmissionsPage);
    fixture.componentRef.setInput('editionId', '3');
    await fixture.whenStable();
    fixture.detectChanges();
    return { fixture, root: fixture.nativeElement as HTMLElement };
  }

  it('liste : référence ou « Brouillon », auteurs, état traduit, dérogation en cours', async () => {
    const { root } = await render();
    const rows = Array.from(root.querySelectorAll('tbody tr')).map((tr) => tr.textContent ?? '');
    expect(rows[0]).toContain('GC27-0001');
    expect(rows[0]).toContain('Awa Koné ; Mariam Traoré');
    expect(rows[0]).toContain('Soumise');
    expect(rows[0]).toContain('dérogation jusqu');
    expect(rows[1]).toContain('Brouillon');
    expect(rows[1]).toContain('(sans titre)');
    expect(root.textContent).toContain('2 soumission(s)');
    expect(api['list']).toHaveBeenCalledWith(3, { ordering: 'reference', page: 1, page_size: 25 });
  });

  it('filtres : recherche et états transmis au serveur ; lien d’export aux mêmes filtres', async () => {
    const { fixture, root } = await render();
    const page = fixture.componentInstance as unknown as {
      form: { patchValue(v: object): void };
      search(): Promise<void>;
    };
    page.form.patchValue({ q: ' Koné ', status: ['submitted', 'screening'], track: 'ia' });
    await page.search();
    fixture.detectChanges();
    expect(api['list']).toHaveBeenLastCalledWith(3, {
      ordering: 'reference',
      q: 'Koné',
      status: ['submitted', 'screening'],
      track: 'ia',
      page: 1,
      page_size: 25,
    });
    const link = root.querySelector<HTMLAnchorElement>('a[download]')!;
    expect(link.getAttribute('href')).toBe(
      '/api/v1/manage/editions/3/submissions/export?ordering=reference&q=Kon%C3%A9&status=submitted&status=screening&track=ia',
    );
  });

  it('CO : pas de lien d’export (submissions.export)', async () => {
    const { root } = await render(OC);
    expect(root.querySelector('a[download]')).toBeNull();
    expect(root.querySelectorAll('tbody tr')).toHaveLength(2);
  });
});

describe('exportUrl', () => {
  it('ignore pagination et valeurs vides', () => {
    expect(exportUrl(3, { page: 2, page_size: 25, q: '' })).toBe(
      '/api/v1/manage/editions/3/submissions/export',
    );
  });
});
