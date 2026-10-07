import { Type } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { Budget, BudgetLine, GcApiError, MeEdition, Task, TaskDetail } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';
import { of } from 'rxjs';

import { CHAIR_EDITION, provideGestionTesting } from '../../../testing/gestion-testing';
import { OrganisationApi } from '../../core/organisation-api';
import { ActivityPage } from './activity-page';
import { BudgetPage } from './budget-page';
import { TaskDetailPage } from './task-detail-page';
import { TasksPage } from './tasks-page';

/** CO « finances » : tâches, budget en lecture et en écriture (plan L8, N2). */
const FINANCE: MeEdition = {
  ...CHAIR_EDITION,
  roles: [{ role: 'OC_MEMBER', oc_function: 'finance' }],
  capabilities: ['edition.read', 'tasks.read', 'tasks.write', 'budget.read', 'budget.write'],
};

/** Chair : tâches, budget en lecture seule. */
const READER: MeEdition = {
  ...CHAIR_EDITION,
  capabilities: ['edition.read', 'tasks.read', 'budget.read'],
};

function task(overrides: Partial<Task> = {}): Task {
  return {
    id: 5,
    title: 'Réserver le traiteur',
    description: '',
    status: 'todo',
    priority: 'high',
    label: 'repas',
    assignee: { id: 9, name: 'Awa Koné' },
    created_by: { id: 1, name: 'Koffi Yao' },
    due_date: '2027-05-01',
    overdue: true,
    position: 0,
    revision: 3,
    comment_count: 1,
    attachment_count: 0,
    archived_at: null,
    done_at: null,
    created_at: '2027-04-01T08:00:00Z',
    updated_at: '2027-04-01T08:00:00Z',
    ...overrides,
  };
}

function detail(overrides: Partial<TaskDetail> = {}): TaskDetail {
  return {
    ...task(),
    comments: [
      {
        id: 1,
        author: { id: 1, name: 'Koffi Yao' },
        body: 'Devis reçu',
        created_at: '2027-04-02T08:00:00Z',
      },
    ],
    attachments: [
      {
        id: 2,
        name: 'devis.pdf',
        kind: 'pdf',
        size: 2048,
        uploaded_by: { id: 1, name: 'Koffi Yao' },
        created_at: '2027-04-02T08:00:00Z',
      },
    ],
    ...overrides,
  };
}

function line(overrides: Partial<BudgetLine> = {}): BudgetLine {
  return {
    id: 7,
    kind: 'expense',
    category: 'catering',
    label: 'Traiteur',
    planned: '1000.00',
    actual: '1200.00',
    variance: '200.00',
    note: '',
    source: 'manual',
    computed: false,
    position: 0,
    proof: null,
    ...overrides,
  };
}

function budget(overrides: Partial<Budget> = {}): Budget {
  return {
    currency: 'XOF',
    expense: { planned: '1000.00', actual: '1200.00' },
    income: { planned: '5000.00', actual: '3000.00' },
    balance_planned: '4000.00',
    balance_actual: '1800.00',
    by_category: [],
    lines: [
      line(),
      line({
        id: 8,
        kind: 'income',
        category: 'registrations',
        label: 'Inscriptions',
        source: 'registrations',
        computed: true,
        planned: '5000.00',
        actual: '3000.00',
        variance: '-2000.00',
      }),
    ],
    ...overrides,
  };
}

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

let api: Record<string, ReturnType<typeof vi.fn>>;

function mockApi(): Record<string, ReturnType<typeof vi.fn>> {
  return {
    tasks: vi
      .fn()
      .mockResolvedValue([
        task(),
        task({ id: 6, title: 'Imprimer', status: 'done', overdue: false }),
      ]),
    members: vi.fn().mockResolvedValue([{ id: 9, name: 'Awa Koné' }]),
    task: vi.fn().mockResolvedValue(detail()),
    createTask: vi.fn().mockResolvedValue(detail({ id: 10, title: 'Nouvelle' })),
    updateTask: vi.fn().mockResolvedValue(detail({ revision: 4 })),
    archiveTask: vi.fn().mockResolvedValue(detail({ archived_at: '2027-04-03T08:00:00Z' })),
    restoreTask: vi.fn().mockResolvedValue(detail()),
    comment: vi.fn().mockResolvedValue(detail()),
    uploadAttachment: vi.fn().mockResolvedValue(detail()),
    downloadAttachment: vi.fn().mockResolvedValue(new Blob(['%PDF'])),
    removeAttachment: vi.fn().mockResolvedValue(detail({ attachments: [] })),
    budget: vi.fn().mockResolvedValue(budget()),
    createLine: vi.fn().mockResolvedValue(budget()),
    updateLine: vi.fn().mockResolvedValue(budget()),
    deleteLine: vi.fn().mockResolvedValue(budget()),
    uploadProof: vi.fn().mockResolvedValue(budget()),
    downloadProof: vi.fn(),
    removeProof: vi.fn().mockResolvedValue(budget()),
    exportBudget: vi.fn().mockResolvedValue(new Blob(['a;b'])),
    activity: vi.fn().mockResolvedValue([
      {
        at: '2027-04-02T08:00:00Z',
        action: 'task.created',
        actor: 'Koffi Yao',
        object_type: 'logistics.task',
        object_id: '5',
      },
      {
        at: '2027-04-02T07:00:00Z',
        action: 'portal.published',
        actor: '',
        object_type: '',
        object_id: '',
      },
    ]),
  };
}

async function setup<T>(
  component: Type<T>,
  edition: MeEdition,
  inputs: Record<string, string> = {},
  prepare: (mocks: typeof api) => void = () => undefined,
) {
  api = mockApi();
  prepare(api);
  TestBed.configureTestingModule({
    providers: [
      ...provideGestionTesting([edition]),
      { provide: OrganisationApi, useValue: api },
      {
        provide: MatDialog,
        useValue: { open: () => ({ afterClosed: () => of({ confirmed: true }) }) },
      },
    ],
  });
  await useTestLanguage('fr');
  const fixture = TestBed.createComponent(component);
  fixture.componentRef.setInput('editionId', '3');
  for (const [name, value] of Object.entries(inputs)) {
    fixture.componentRef.setInput(name, value);
  }
  await fixture.whenStable();
  fixture.detectChanges();
  const settle = async () => {
    await fixture.whenStable();
    fixture.detectChanges();
  };
  return { fixture, root: fixture.nativeElement as HTMLElement, settle };
}

describe('Tâches du CO (plan L8, N3)', () => {
  it('trois colonnes, retard signalé, déplacement au clavier avec la révision lue', async () => {
    const { root, settle } = await setup(TasksPage, FINANCE);
    const columns = Array.from(root.querySelectorAll('section.column h2')).map((item) =>
      text(item as HTMLElement).trim(),
    );
    expect(columns).toEqual(['À faire (1)', 'En cours (0)', 'Terminées (1)']);
    expect(text(root)).toContain('en retard');
    const select = root.querySelector<HTMLSelectElement>(
      'select[aria-label="Déplacer la tâche « Réserver le traiteur » vers une autre colonne"]',
    )!;
    select.value = 'doing';
    select.dispatchEvent(new Event('change'));
    await settle();
    expect(api['updateTask']).toHaveBeenCalledWith(3, 5, 3, { status: 'doing' });
    expect(text(root)).toContain('déplacée vers « En cours »');
  });

  it('création d’une tâche ; tâche modifiée entre-temps : message et rechargement', async () => {
    const { fixture, root, settle } = await setup(TasksPage, FINANCE, {}, (mocks) => {
      mocks['updateTask'].mockRejectedValue(new GcApiError(412, 'stale_revision', 'Modifié'));
    });
    const component = fixture.componentInstance as unknown as {
      form: { setValue(value: unknown): void };
    };
    component.form.setValue({
      title: ' Nouvelle ',
      assignee: 9,
      due_date: '2027-05-10',
      priority: 'normal',
      label: '',
    });
    button(root, 'Créer la tâche').click();
    await settle();
    expect(api['createTask']).toHaveBeenCalledWith(3, {
      title: 'Nouvelle',
      assignee: 9,
      due_date: '2027-05-10',
      priority: 'normal',
      label: '',
    });
    const select = root.querySelector<HTMLSelectElement>('select')!;
    select.value = 'done';
    select.dispatchEvent(new Event('change'));
    await settle();
    expect(text(root)).toContain('modifiée entre-temps');
    expect(api['tasks'].mock.calls.length).toBeGreaterThanOrEqual(3);
  });

  it('lecture seule (sans tasks.write) : ni formulaire ni déplacement', async () => {
    const { root } = await setup(TasksPage, READER);
    expect(text(root)).not.toContain('Nouvelle tâche');
    expect(root.querySelector('select')).toBeNull();
  });

  it('fiche : enregistrement avec la révision, commentaire, pièce jointe téléchargée', async () => {
    const { root, settle } = await setup(TaskDetailPage, FINANCE, { taskId: '5' });
    expect(text(root)).toContain('Devis reçu');
    button(root, 'Enregistrer').click();
    await settle();
    expect(api['updateTask']).toHaveBeenCalledWith(
      3,
      5,
      3,
      expect.objectContaining({
        title: 'Réserver le traiteur',
        assignee: 9,
        due_date: '2027-05-01',
      }),
    );
    expect(text(root)).toContain('Tâche enregistrée.');
    button(root, 'devis.pdf').click();
    await settle();
    expect(api['downloadAttachment']).toHaveBeenCalledWith(3, 5, 2);
  });

  it('fiche archivée : champs figés, restauration proposée', async () => {
    const { root, settle } = await setup(TaskDetailPage, FINANCE, { taskId: '5' }, (mocks) => {
      mocks['task'].mockResolvedValue(detail({ archived_at: '2027-04-03T08:00:00Z' }));
    });
    expect(text(root)).toContain('Tâche archivée le');
    expect(root.querySelector<HTMLInputElement>('input[formcontrolname="title"]')!.disabled).toBe(
      true,
    );
    button(root, 'Restaurer').click();
    await settle();
    expect(api['restoreTask']).toHaveBeenCalledWith(3, 5, 3);
  });
});

describe('Budget (plan L8, N4)', () => {
  it('synthèse, ligne calculée non supprimable, export CSV', async () => {
    const { root, settle } = await setup(BudgetPage, FINANCE);
    expect(text(root)).toContain('Solde réalisé');
    expect(text(root)).toContain('calculé');
    expect(root.querySelector('[aria-label="Supprimer la ligne « Inscriptions »"]')).toBeNull();
    expect(root.querySelector('[aria-label="Supprimer la ligne « Traiteur »"]')).not.toBeNull();
    button(root, 'Exporter (CSV)').click();
    await settle();
    expect(api['exportBudget']).toHaveBeenCalledWith(3, 'csv');
  });

  it('ajout d’une ligne ; modification d’une ligne calculée limitée au libellé, prévu, note', async () => {
    const { fixture, root, settle } = await setup(BudgetPage, FINANCE);
    const component = fixture.componentInstance as unknown as {
      form: { patchValue(value: unknown): void };
    };
    component.form.patchValue({ label: 'Salle', planned: '500' });
    button(root, 'Ajouter la ligne').click();
    await settle();
    expect(api['createLine']).toHaveBeenCalledWith(
      3,
      expect.objectContaining({
        kind: 'expense',
        category: 'venue',
        label: 'Salle',
        planned: '500',
        actual: null,
      }),
    );
    (
      root.querySelector('[aria-label="Modifier la ligne « Inscriptions »"]') as HTMLButtonElement
    ).click();
    await settle();
    expect(text(root)).toContain('Ligne calculée');
    button(root, 'Enregistrer').click();
    await settle();
    expect(api['updateLine']).toHaveBeenCalledWith(3, 8, {
      label: 'Inscriptions',
      planned: '5000.00',
      note: '',
    });
  });

  it('lecture seule : ni formulaire ni actions', async () => {
    const { root } = await setup(BudgetPage, READER);
    expect(text(root)).not.toContain('Nouvelle ligne');
    expect(text(root)).not.toContain('Actions');
  });
});

describe('Fil d’activité (plan L8, N14)', () => {
  it('actions traduites, lien vers la tâche, système sans nom', async () => {
    const { root } = await setup(ActivityPage, READER);
    expect(text(root)).toContain('Tâche créée');
    expect(text(root)).toContain('Portail publié');
    expect(text(root)).toContain('Système');
    expect(root.querySelector('a[href="/editions/3/organisation/taches/5"]')).not.toBeNull();
  });
});
