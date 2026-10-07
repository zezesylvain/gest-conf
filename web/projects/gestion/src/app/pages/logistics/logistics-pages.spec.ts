import { Type } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { GcApiError, ManageVisit, Meal, MeEdition, Shift } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';
import { of } from 'rxjs';

import { CHAIR_EDITION, provideGestionTesting } from '../../../testing/gestion-testing';
import { LogisticsApi } from '../../core/logistics-api';
import { RegistrationsApi } from '../../core/registrations-api';
import { CateringPage } from './catering-page';
import { MyShiftsPage } from './my-shifts-page';
import { ShiftsPage } from './shifts-page';
import { SpeakersPage } from './speakers-page';
import { VisitDetailPage } from './visit-detail-page';

/** CO « logistique » : lecture, écriture, planning des bénévoles (plan L8, N2). */
const LOGISTICS: MeEdition = {
  ...CHAIR_EDITION,
  roles: [{ role: 'OC_MEMBER', oc_function: 'logistics' }],
  capabilities: ['edition.read', 'logistics.read', 'logistics.write', 'volunteers.plan'],
};

/** Chair : logistique en lecture seule. */
const READER: MeEdition = {
  ...CHAIR_EDITION,
  capabilities: ['edition.read', 'logistics.read'],
};

/** Bénévole : son planning seulement. */
const VOLUNTEER: MeEdition = {
  ...CHAIR_EDITION,
  roles: [{ role: 'VOLUNTEER', oc_function: '' }],
  capabilities: ['checkin.scan', 'shifts.own'],
};

function visit(overrides: Partial<ManageVisit> = {}): ManageVisit {
  return {
    speaker: { id: 12, name: 'Aminata Diallo' },
    institution: 'Université de Dakar',
    technical_needs: ['projector', 'interpretation'],
    technical_note: '',
    arrival_local: '2027-06-01T09:30',
    arrival_means: 'plane',
    arrival_reference: 'AF 702',
    departure_local: null,
    departure_means: '',
    departure_reference: '',
    accommodation_needed: true,
    transfer_needed: false,
    speaker_note: 'Arrivée tardive possible',
    hotel: '',
    check_in: null,
    check_out: null,
    status: 'to_arrange',
    internal_note: 'Devis hôtel demandé',
    missing_equipment: ['interpretation'],
    updated_at: null,
    ...overrides,
  };
}

function meal(overrides: Partial<Meal> = {}): Meal {
  return {
    id: 4,
    day: '2027-06-01',
    kind: 'lunch',
    label_fr: 'Buffet',
    label_en: 'Buffet',
    include_registered: true,
    option_code: '',
    include_speakers: true,
    include_committees: false,
    include_volunteers: true,
    margin_percent: 10,
    position: 0,
    estimate: { count: 120, margin: 12, total: 132, by_diet: { vegetarian: 8 }, allergies: 2 },
    ...overrides,
  };
}

function shift(overrides: Partial<Shift> = {}): Shift {
  return {
    id: 6,
    title_fr: 'Accueil du matin',
    title_en: 'Morning reception',
    place: 'Hall',
    starts_at: '2027-06-01T07:00:00Z',
    ends_at: '2027-06-01T10:00:00Z',
    starts_local: '2027-06-01T07:00',
    ends_local: '2027-06-01T10:00',
    needed: 3,
    missing: 2,
    instructions: 'Badge visible',
    volunteers: [{ id: 21, name: 'Koffi Yao' }],
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

const BOARD = {
  shifts: [shift()],
  volunteers: [
    { id: 21, name: 'Koffi Yao' },
    { id: 22, name: 'Awa Koné' },
  ],
};

let api: Record<string, ReturnType<typeof vi.fn>>;
let registrations: Record<string, ReturnType<typeof vi.fn>>;

function mockApi(): Record<string, ReturnType<typeof vi.fn>> {
  return {
    visits: vi.fn().mockResolvedValue([
      visit(),
      visit({
        speaker: { id: 13, name: 'Jean Kouassi' },
        missing_equipment: [],
        technical_needs: [],
        accommodation_needed: false,
        hotel: 'Hôtel du Plateau',
      }),
    ]),
    visit: vi.fn().mockResolvedValue(visit()),
    updateVisit: vi.fn().mockResolvedValue(visit({ status: 'booked', hotel: 'Hôtel du Plateau' })),
    dietary: vi.fn().mockResolvedValue({
      declarations: 9,
      by_diet: { vegetarian: 8, no_pork: 1 },
      allergies: 2,
    }),
    exportDietary: vi.fn().mockResolvedValue(new Blob(['a;b'])),
    meals: vi.fn().mockResolvedValue([meal()]),
    createMeal: vi.fn().mockResolvedValue([meal(), meal({ id: 5, kind: 'dinner' })]),
    updateMeal: vi.fn().mockResolvedValue([meal({ margin_percent: 15 })]),
    deleteMeal: vi.fn().mockResolvedValue([]),
    exportMeals: vi.fn().mockResolvedValue(new Blob(['%PDF'])),
    shifts: vi.fn().mockResolvedValue(BOARD),
    createShift: vi.fn().mockResolvedValue(BOARD),
    updateShift: vi.fn().mockResolvedValue(BOARD),
    deleteShift: vi.fn().mockResolvedValue({ ...BOARD, shifts: [] }),
    assign: vi.fn().mockResolvedValue(BOARD),
    unassign: vi.fn().mockResolvedValue(BOARD),
    myShifts: vi.fn().mockResolvedValue([shift()]),
    myCalendar: vi.fn().mockResolvedValue(new Blob(['BEGIN:VCALENDAR'])),
  };
}

async function setup<T>(
  component: Type<T>,
  edition: MeEdition,
  inputs: Record<string, string> = {},
  prepare: (mocks: typeof api) => void = () => undefined,
) {
  api = mockApi();
  registrations = {
    options: vi
      .fn()
      .mockResolvedValue([
        { id: 1, code: 'GALA', label_fr: 'Dîner de gala', label_en: 'Gala dinner' },
      ]),
  };
  prepare(api);
  TestBed.configureTestingModule({
    providers: [
      ...provideGestionTesting([edition]),
      { provide: LogisticsApi, useValue: api },
      { provide: RegistrationsApi, useValue: registrations },
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

describe('Intervenants invités (plan L8, N6)', () => {
  it('liste : prise en charge, heure du lieu, équipement manquant signalé, lien vers la fiche', async () => {
    const { root } = await setup(SpeakersPage, READER);
    expect(text(root)).toContain('Aminata Diallo');
    expect(text(root)).toContain('À organiser');
    expect(text(root)).toContain('09:30');
    expect(text(root)).toContain('Avion AF 702');
    expect(text(root)).toContain('Demandé, à réserver');
    expect(text(root)).toContain('Manque en salle : Interprétation');
    expect(text(root)).toContain('Hôtel du Plateau');
    expect(root.querySelector('a[href="/editions/3/logistique/intervenants/12"]')).not.toBeNull();
  });

  it('fiche : part du comité enregistrée, besoins cochés, heures nulles quand vides', async () => {
    const { fixture, root, settle } = await setup(VisitDetailPage, LOGISTICS, { userId: '12' });
    expect(text(root)).toContain('Une salle où passe cet intervenant');
    expect(
      root.querySelector<HTMLTextAreaElement>('textarea[formcontrolname="internal_note"]')!.value,
    ).toBe('Devis hôtel demandé');
    const component = fixture.componentInstance as unknown as {
      form: { patchValue(value: unknown): void };
    };
    component.form.patchValue({ hotel: 'Hôtel du Plateau', status: 'booked' });
    button(root, 'Enregistrer').click();
    await settle();
    expect(api['visit']).toHaveBeenCalledWith(3, 12);
    expect(api['updateVisit']).toHaveBeenCalledWith(
      3,
      12,
      expect.objectContaining({
        hotel: 'Hôtel du Plateau',
        status: 'booked',
        technical_needs: ['projector', 'interpretation'],
        arrival_local: '2027-06-01T09:30',
        departure_local: null,
        check_in: null,
      }),
    );
    expect(text(root)).toContain('Fiche de venue enregistrée.');
  });

  it('fiche en lecture seule (sans logistics.write) : champs figés, pas de bouton', async () => {
    const { root } = await setup(VisitDetailPage, READER, { userId: '12' });
    expect(root.querySelector<HTMLInputElement>('input[formcontrolname="hotel"]')!.disabled).toBe(
      true,
    );
    expect(text(root)).not.toContain('Enregistrer');
  });
});

describe('Restauration (plan L8, N7, N8, RG-23)', () => {
  it('repas estimés sans nom, régimes agrégés, commande PDF, liste nominative à part', async () => {
    const { root, settle } = await setup(CateringPage, LOGISTICS);
    expect(text(root)).toContain('Déjeuner — Buffet');
    expect(text(root)).toContain('Inscrits, Intervenants invités, Bénévoles');
    expect(text(root)).toContain('132');
    expect(text(root)).toContain('Végétarien : 8');
    expect(text(root)).toContain('Allergies : 2');
    expect(text(root)).toContain('9 déclaration(s)');
    button(root, 'Commande au traiteur (PDF)').click();
    await settle();
    expect(api['exportMeals']).toHaveBeenCalledWith(3, 'pdf');
    button(root, 'Liste nominative (CSV)').click();
    await settle();
    expect(api['exportDietary']).toHaveBeenCalledWith(3, 'csv');
  });

  it('ajout d’un repas réservé à une option, marge numérique ; suppression confirmée', async () => {
    const { fixture, root, settle } = await setup(CateringPage, LOGISTICS);
    const component = fixture.componentInstance as unknown as {
      form: { patchValue(value: unknown): void };
    };
    component.form.patchValue({ day: '2027-06-02', kind: 'dinner', option_code: 'GALA' });
    button(root, 'Ajouter le repas').click();
    await settle();
    expect(api['createMeal']).toHaveBeenCalledWith(
      3,
      expect.objectContaining({
        day: '2027-06-02',
        kind: 'dinner',
        option_code: 'GALA',
        margin_percent: 5,
      }),
    );
    expect(text(root)).toContain('Repas ajouté.');
    (
      root.querySelector('[aria-label="Supprimer le repas Déjeuner — Buffet"]') as HTMLElement
    ).click();
    await settle();
    expect(api['deleteMeal']).toHaveBeenCalledWith(3, 4);
  });

  it('lecture seule : ni formulaire ni actions ; options illisibles sans erreur', async () => {
    const { root } = await setup(CateringPage, READER);
    expect(registrations['options']).toHaveBeenCalled();
    expect(text(root)).not.toContain('Nouveau repas');
    expect(text(root)).not.toContain('Actions');
  });
});

describe('Postes des bénévoles (plan L8, N9)', () => {
  it('places manquantes, affectation d’un bénévole libre, retrait', async () => {
    const { root, settle } = await setup(ShiftsPage, LOGISTICS);
    expect(text(root)).toContain('1 bénévole(s) sur 3');
    expect(text(root)).toContain('2 place(s) à pourvoir');
    const picker = root.querySelector<HTMLSelectElement>(
      'select[aria-label="Bénévole à affecter au poste Accueil du matin"]',
    )!;
    expect(Array.from(picker.options).map((option) => option.textContent!.trim())).toEqual([
      'Awa Koné',
    ]);
    button(root, 'Affecter').click();
    await settle();
    expect(api['assign']).toHaveBeenCalledWith(3, 6, 22);
    (
      root.querySelector(
        '[aria-label="Retirer Koffi Yao du poste Accueil du matin"]',
      ) as HTMLElement
    ).click();
    await settle();
    expect(api['unassign']).toHaveBeenCalledWith(3, 6, 21);
  });

  it('chevauchement refusé par le serveur : message traduit', async () => {
    const { root, settle } = await setup(ShiftsPage, LOGISTICS, {}, (mocks) => {
      mocks['assign'].mockRejectedValue(new GcApiError(409, 'shift_overlap', 'Chevauchement'));
    });
    button(root, 'Affecter').click();
    await settle();
    expect(root.querySelector('gc-error-summary')!.textContent).not.toBe('');
    expect(text(root)).not.toContain('Bénévole affecté.');
  });

  it('création d’un poste à l’heure du lieu, nombre converti', async () => {
    const { fixture, root, settle } = await setup(ShiftsPage, LOGISTICS);
    const component = fixture.componentInstance as unknown as {
      form: { patchValue(value: unknown): void };
    };
    component.form.patchValue({
      title_fr: 'Vestiaire',
      starts_local: '2027-06-01T08:00',
      ends_local: '2027-06-01T12:00',
      needed: '2',
    });
    button(root, 'Ajouter le poste').click();
    await settle();
    expect(api['createShift']).toHaveBeenCalledWith(
      3,
      expect.objectContaining({
        title_fr: 'Vestiaire',
        starts_local: '2027-06-01T08:00',
        needed: 2,
      }),
    );
  });
});

describe('Mon planning (plan L8, N9)', () => {
  it('postes du bénévole et fichier iCal', async () => {
    const { root, settle } = await setup(MyShiftsPage, VOLUNTEER);
    expect(text(root)).toContain('Accueil du matin');
    expect(text(root)).toContain('Badge visible');
    button(root, 'Télécharger mon planning (iCal)').click();
    await settle();
    expect(api['myCalendar']).toHaveBeenCalledWith(3);
  });

  it('aucun poste : message', async () => {
    const { root } = await setup(MyShiftsPage, VOLUNTEER, {}, (mocks) => {
      mocks['myShifts'].mockResolvedValue([]);
    });
    expect(text(root)).toContain('Aucun poste ne vous est encore confié.');
  });
});
