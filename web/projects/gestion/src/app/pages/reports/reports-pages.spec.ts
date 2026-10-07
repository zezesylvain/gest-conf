import { Type } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Edition, GcApiError, MeEdition } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';

import { CHAIR_EDITION, provideGestionTesting } from '../../../testing/gestion-testing';
import { EditionApi } from '../../core/edition-api';
import { LogisticsApi } from '../../core/logistics-api';
import { OrganisationApi } from '../../core/organisation-api';
import { ReportsApi } from '../../core/reports-api';
import { SponsorsApi } from '../../core/sponsors-api';
import { DashboardPage } from '../dashboard/dashboard-page';
import { ReportsPage, withBars } from './reports-page';

/** CO « logistique » et « finances » réunis : les indicateurs de l'organisation (plan L8). */
const ORGANISER: MeEdition = {
  ...CHAIR_EDITION,
  roles: [{ role: 'OC_MEMBER', oc_function: 'logistics' }],
  capabilities: [
    'edition.read',
    'tasks.read',
    'budget.read',
    'sponsors.read',
    'logistics.read',
    'volunteers.plan',
  ],
};

function text(root: HTMLElement): string {
  return (root.textContent ?? '').replace(/[\u00a0\u202f]/g, ' ').replace(/\s+/g, ' ');
}

function button(root: HTMLElement, label: string): HTMLButtonElement {
  const found = Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find((item) =>
    item.textContent!.includes(label),
  );
  if (!found) throw new Error(`Bouton « ${label} » absent`);
  return found;
}

async function render<T>(component: Type<T>, providers: unknown[]) {
  TestBed.configureTestingModule({
    providers: [...provideGestionTesting([ORGANISER]), ...(providers as never[])],
  });
  await useTestLanguage('fr');
  const fixture = TestBed.createComponent(component);
  fixture.componentRef.setInput('editionId', '3');
  await fixture.whenStable();
  fixture.detectChanges();
  const settle = async () => {
    await fixture.whenStable();
    fixture.detectChanges();
  };
  return { root: fixture.nativeElement as HTMLElement, settle };
}

describe('Rapports (plan L8, N13)', () => {
  it('barres sur la première colonne numérique, jamais sur une seule ligne', () => {
    const table = {
      key: 'by_track',
      title: 'Par thématique',
      columns: ['Thématique', 'Envoyées', 'Taux (%)'],
      rows: [
        ['IA', '12', '50.0'],
        ['Santé', '6', null],
      ],
    };
    expect(withBars(table)).toEqual(expect.objectContaining({ barColumn: 1, max: 12 }));
    expect(withBars({ ...table, rows: [['IA', '12', '50.0']] }).barColumn).toBeNull();
    expect(
      withBars({
        ...table,
        rows: [
          ['IA', 'n/a', '1'],
          ['Santé', '2', '3'],
        ],
      }).barColumn,
    ).toBe(2);
  });

  it('sections ouvertes, tableaux et barres doublées des nombres, changement et export', async () => {
    const api = {
      sections: vi.fn().mockResolvedValue([
        { code: 'submissions', label: 'Soumissions' },
        { code: 'budget', label: 'Budget' },
      ]),
      section: vi.fn().mockImplementation((_edition: number, code: string) =>
        Promise.resolve({
          code,
          label: code === 'budget' ? 'Budget' : 'Soumissions',
          tables: [
            {
              key: 'by_status',
              title: code === 'budget' ? 'Par poste' : 'Par statut',
              columns: ['Statut', 'Nombre'],
              rows: [
                ['Envoyée', '8'],
                ['Acceptée', '4'],
              ],
            },
          ],
        }),
      ),
      exportSection: vi.fn().mockResolvedValue(new Blob(['%PDF'])),
    };
    const { root, settle } = await render(ReportsPage, [{ provide: ReportsApi, useValue: api }]);
    expect(api.section).toHaveBeenCalledWith(3, 'submissions');
    expect(text(root)).toContain('Par statut');
    expect(
      Array.from(root.querySelectorAll('tbody tr')).map((row) => text(row as HTMLElement)),
    ).toEqual(['Envoyée8', 'Acceptée4']);
    const bars = Array.from(root.querySelectorAll<HTMLElement>('.bar'));
    expect(bars.map((bar) => bar.style.width)).toEqual(['100%', '50%']);
    expect(bars.every((bar) => bar.getAttribute('aria-hidden') === 'true')).toBe(true);
    button(root, 'Budget').click();
    await settle();
    expect(api.section).toHaveBeenLastCalledWith(3, 'budget');
    expect(text(root)).toContain('Par poste');
    expect(root.querySelector('button[aria-pressed="true"]')!.textContent!.trim()).toBe('Budget');
    button(root, 'Exporter (PDF)').click();
    await settle();
    expect(api.exportSection).toHaveBeenCalledWith(3, 'budget', 'pdf');
  });

  it('aucune section ouverte : message', async () => {
    const api = {
      sections: vi.fn().mockResolvedValue([]),
      section: vi.fn(),
      exportSection: vi.fn(),
    };
    const { root } = await render(ReportsPage, [{ provide: ReportsApi, useValue: api }]);
    expect(text(root)).toContain("Aucune section de rapport n'est ouverte à votre rôle.");
    expect(api.section).not.toHaveBeenCalled();
  });

  it('section refusée par le serveur : message traduit', async () => {
    const api = {
      sections: vi.fn().mockResolvedValue([{ code: 'finance', label: 'Recettes' }]),
      section: vi.fn().mockRejectedValue(new GcApiError(403, 'permission_denied', 'Refusé')),
      exportSection: vi.fn(),
    };
    const { root } = await render(ReportsPage, [{ provide: ReportsApi, useValue: api }]);
    expect(root.querySelector('gc-error-summary')!.textContent!.trim()).not.toBe('');
  });
});

describe('Tableau de bord : organisation (plan L8, N16)', () => {
  it('mes tâches et retards, soldes, partenariats, venues, places à pourvoir', async () => {
    const edition = {
      id: 3,
      code: 'GC27',
      title_fr: 'GEST-CONF 2027',
      title_en: 'GEST-CONF 2027',
      status: 'draft',
      timezone: 'Africa/Abidjan',
    } as unknown as Edition;
    const { root, settle } = await render(DashboardPage, [
      {
        provide: EditionApi,
        useValue: {
          edition: vi.fn().mockResolvedValue(edition),
          keyDates: vi.fn().mockResolvedValue([]),
          tracks: vi.fn().mockResolvedValue([]),
          submissionTypes: vi.fn().mockResolvedValue([]),
        },
      },
      {
        provide: OrganisationApi,
        useValue: {
          tasks: vi.fn().mockResolvedValue([
            { status: 'todo', overdue: true },
            { status: 'doing', overdue: false },
            { status: 'done', overdue: false },
          ]),
          budget: vi.fn().mockResolvedValue({
            currency: 'XOF',
            balance_planned: '4000.00',
            balance_actual: '-500.00',
          }),
        },
      },
      {
        provide: SponsorsApi,
        useValue: {
          sponsors: vi.fn().mockResolvedValue({
            totals: { currency: 'XOF', agreed: '5000000.00', received: '1000000.00' },
            sponsors: [],
          }),
        },
      },
      {
        provide: LogisticsApi,
        useValue: {
          visits: vi.fn().mockResolvedValue([
            { status: 'to_arrange', missing_equipment: ['wifi'] },
            { status: 'booked', missing_equipment: [] },
          ]),
          shifts: vi.fn().mockResolvedValue({
            shifts: [{ missing: 2 }, { missing: 1 }],
            volunteers: [],
          }),
        },
      },
    ]);
    // Les indicateurs se chargent l'un après l'autre : attendre le dernier.
    await settle();
    await settle();
    expect(text(root)).toContain('2 tâche(s) à faire ou en cours pour moi');
    expect(text(root)).toContain('dont 1 en retard');
    expect(text(root)).toContain('Solde prévu');
    expect(text(root)).toContain('1 000 000');
    expect(text(root)).toContain("1 venue(s) d'intervenant à organiser");
    expect(text(root)).toContain('1 avec un équipement manquant en salle');
    expect(text(root)).toContain('3 place(s) de bénévole à pourvoir');
    expect(root.querySelector('a[href="/editions/3/logistique/benevoles"]')).not.toBeNull();
  });
});
