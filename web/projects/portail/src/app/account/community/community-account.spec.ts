import { signal, Type } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute } from '@angular/router';
import { GcApiError, Me, MeStore, MySurveyDetail, MyVisit, Notification } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';

import { UnsubscribePage } from '../../pages/unsubscribe/unsubscribe-page';
import { NotificationsPage } from '../notifications/notifications-page';
import { NotificationsStore } from '../notifications/notifications.store';
import { RegistrationService } from '../registration/registration.service';
import { provideAccountTesting } from '../testing';
import { CommunityService } from './community.service';
import { DietaryCard } from './dietary-card';
import { PreferencesPage } from './preferences-page';
import { SurveyPage } from './survey-page';
import { VisitPage } from './visit-page';

const SPACES = new RegExp('[' + String.fromCharCode(0xa0, 0x202f) + ']', 'g');

function text(root: HTMLElement): string {
  return (root.textContent ?? '').replace(SPACES, ' ').replace(/\s+/g, ' ');
}

function button(root: HTMLElement, label: string): HTMLButtonElement {
  const found = Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find((item) =>
    item.textContent!.includes(label),
  );
  if (!found) throw new Error(`Bouton « ${label} » absent`);
  return found;
}

const ME = {
  id: 1,
  email: 'ama@example.org',
  locale: 'fr',
  profile_complete: true,
  privacy_notice_pending: false,
  pending_invitations: [],
  mfa_enabled: false,
  mfa_verified: false,
  editions: [
    {
      id: 3,
      code: 'GC27',
      title_fr: 'GEST-CONF 2027',
      title_en: 'GEST-CONF 2027',
      year: 2027,
      status: 'published',
      roles: [{ role: 'SPEAKER', oc_function: '' }],
      capabilities: [],
      mfa_required: false,
    },
  ],
} as unknown as Me;

const VISIT: MyVisit = {
  edition_id: 3,
  edition_code: 'GC27',
  timezone: 'Africa/Abidjan',
  technical_needs: ['projector'],
  technical_note: '',
  arrival_local: '2027-06-01T09:30',
  arrival_means: 'plane',
  arrival_reference: 'AF 702',
  departure_local: null,
  departure_means: '',
  departure_reference: '',
  accommodation_needed: true,
  transfer_needed: false,
  speaker_note: '',
  hotel: 'Hôtel du Plateau',
  check_in: '2027-05-31',
  check_out: '2027-06-03',
  status: 'booked',
};

let service: Record<string, ReturnType<typeof vi.fn>>;

function mockService(): Record<string, ReturnType<typeof vi.fn>> {
  return {
    visit: vi.fn().mockResolvedValue(VISIT),
    updateVisit: vi.fn().mockResolvedValue(VISIT),
    dietary: vi.fn().mockResolvedValue({
      eligible: true,
      diets: ['vegetarian'],
      allergies: '',
      consented_at: '2027-05-01T08:00:00Z',
    }),
    declareDietary: vi.fn().mockResolvedValue({
      eligible: true,
      diets: ['vegetarian', 'gluten_free'],
      allergies: 'Arachide',
      consented_at: '2027-05-02T08:00:00Z',
    }),
    withdrawDietary: vi.fn().mockResolvedValue({
      eligible: true,
      diets: [],
      allergies: '',
      consented_at: null,
    }),
    subscription: vi.fn().mockResolvedValue({ subscribed: true }),
    setSubscription: vi.fn().mockResolvedValue({ subscribed: false }),
    survey: vi.fn(),
    answer: vi.fn().mockResolvedValue({}),
    unsubscribe: vi.fn().mockResolvedValue({
      edition_title_fr: 'GEST-CONF 2027',
      edition_title_en: 'GEST-CONF 2027',
    }),
  };
}

async function render<T>(
  component: Type<T>,
  options: { inputs?: Record<string, unknown>; params?: Record<string, string> } = {},
  prepare: (mocks: typeof service) => void = () => undefined,
) {
  service = mockService();
  prepare(service);
  TestBed.configureTestingModule({
    providers: [
      ...provideAccountTesting(),
      { provide: CommunityService, useValue: service },
      { provide: MeStore, useValue: { me: signal(ME), load: vi.fn().mockResolvedValue(ME) } },
      {
        provide: RegistrationService,
        useValue: {
          list: vi
            .fn()
            .mockResolvedValue([
              { edition: { id: 4, code: 'GC28', title_fr: 'GEST-CONF 2028', title_en: '' } },
            ]),
        },
      },
      {
        provide: ActivatedRoute,
        useValue: { snapshot: { paramMap: new Map(Object.entries(options.params ?? {})) } },
      },
    ],
  });
  await useTestLanguage('fr');
  const fixture = TestBed.createComponent(component);
  for (const [name, value] of Object.entries(options.inputs ?? {})) {
    fixture.componentRef.setInput(name, value);
  }
  fixture.detectChanges();
  await fixture.whenStable();
  fixture.detectChanges();
  const settle = async () => {
    await fixture.whenStable();
    fixture.detectChanges();
  };
  return { fixture, root: fixture.nativeElement as HTMLElement, settle };
}

describe('Régime alimentaire (plan L8, N7, RG-23)', () => {
  it('consentement exigé à chaque déclaration, puis enregistrement', async () => {
    const { fixture, root, settle } = await render(DietaryCard, { inputs: { editionId: 3 } });
    expect(text(root)).toContain('Régime alimentaire');
    button(root, 'Enregistrer').click();
    await settle();
    expect(service['declareDietary']).not.toHaveBeenCalled();
    expect(text(root)).toContain('Cochez la case de consentement');
    const component = fixture.componentInstance as unknown as {
      form: { patchValue(value: unknown): void };
      toggle(item: string, checked: boolean): void;
    };
    component.toggle('gluten_free', true);
    component.form.patchValue({ allergies: ' Arachide ', consent: true });
    button(root, 'Enregistrer').click();
    await settle();
    expect(service['declareDietary']).toHaveBeenCalledWith(3, {
      diets: ['vegetarian', 'gluten_free'],
      allergies: 'Arachide',
      consent: true,
    });
    expect(text(root)).toContain('Régime enregistré.');
    button(root, 'Retirer ma déclaration').click();
    await settle();
    expect(service['withdrawDietary']).toHaveBeenCalledWith(3);
  });

  it('personne non concernée : la carte ne s’affiche pas', async () => {
    const { root } = await render(DietaryCard, { inputs: { editionId: 3 } }, (mocks) => {
      mocks['dietary'].mockResolvedValue({
        eligible: false,
        diets: [],
        allergies: '',
        consented_at: null,
      });
    });
    expect(root.querySelector('section')).toBeNull();
  });
});

describe('« Ma venue » (plan L8, N6)', () => {
  it('ce que le comité a organisé, besoins et voyages à l’heure de la conférence', async () => {
    const { root, settle } = await render(VisitPage);
    expect(service['visit']).toHaveBeenCalledWith(3);
    expect(text(root)).toContain('Réservé');
    expect(text(root)).toContain('Hôtel du Plateau');
    expect(text(root)).toContain('Africa/Abidjan');
    button(root, 'Enregistrer').click();
    await settle();
    expect(service['updateVisit']).toHaveBeenCalledWith(
      3,
      expect.objectContaining({
        technical_needs: ['projector'],
        arrival_local: '2027-06-01T09:30',
        departure_local: null,
        accommodation_needed: true,
      }),
    );
    expect(text(root)).toContain('Informations enregistrées.');
  });
});

describe('Régime et annonces (plan L8, N7, N11)', () => {
  it('éditions des rôles et des inscriptions ; désabonnement des annonces', async () => {
    const { root, settle } = await render(PreferencesPage);
    // Lectures en chaîne (compte, inscriptions, abonnements) : attendre la dernière.
    await settle();
    await settle();
    await settle();
    const headings = Array.from(root.querySelectorAll('h2')).map((item) => item.textContent!);
    expect(headings.some((value) => value.includes('GC27 — GEST-CONF 2027'))).toBe(true);
    expect(headings.some((value) => value.includes('GC28 — GEST-CONF 2028'))).toBe(true);
    const checkbox = root.querySelector<HTMLInputElement>('mat-checkbox input')!;
    checkbox.click();
    await settle();
    expect(service['setSubscription']).toHaveBeenCalledWith(3, false);
    expect(text(root)).toContain('Vous ne recevrez plus les annonces par e-mail.');
  });
});

describe('Questionnaire (plan L8, N12, RG-21)', () => {
  const SURVEY: MySurveyDetail = {
    id: 6,
    edition_id: 3,
    edition_code: 'GC27',
    title_fr: 'Votre avis',
    title_en: '',
    intro_fr: 'Merci de votre venue.',
    intro_en: '',
    session_title: '',
    closes_at: '2027-06-10T18:00:00Z',
    is_open: true,
    answered: false,
    questions: [
      {
        id: 1,
        kind: 'rating',
        label_fr: 'Organisation',
        label_en: '',
        choices: [],
        required: true,
        position: 0,
      },
      {
        id: 2,
        kind: 'multiple',
        label_fr: 'Formats appréciés',
        label_en: '',
        choices: [
          { value: '1', label_fr: 'Ateliers', label_en: '' },
          { value: '2', label_fr: 'Plénières', label_en: '' },
        ],
        required: false,
        position: 1,
      },
      {
        id: 3,
        kind: 'text',
        label_fr: 'Commentaire',
        label_en: '',
        choices: [],
        required: false,
        position: 2,
      },
    ],
  };

  it('anonymat annoncé, obligatoire vérifiée, réponse envoyée une fois', async () => {
    const { root, settle } = await render(SurveyPage, { params: { surveyId: '6' } }, (mocks) =>
      mocks['survey'].mockResolvedValue(SURVEY),
    );
    expect(service['survey']).toHaveBeenCalledWith(6);
    expect(text(root)).toContain('Votre réponse est anonyme');
    button(root, 'Envoyer ma réponse').click();
    await settle();
    expect(service['answer']).not.toHaveBeenCalled();
    expect(text(root)).toContain('Répondez à la question « Organisation »');
    root.querySelector<HTMLInputElement>('input[type="radio"][value="4"]')!.click();
    root.querySelector<HTMLInputElement>('input[type="checkbox"][value="2"]')!.click();
    const area = root.querySelector<HTMLTextAreaElement>('textarea')!;
    area.value = 'Très bien';
    area.dispatchEvent(new Event('input'));
    button(root, 'Envoyer ma réponse').click();
    await settle();
    expect(service['answer']).toHaveBeenCalledWith(6, { 1: 4, 2: ['2'], 3: 'Très bien' });
    expect(text(root)).toContain('Merci, votre réponse est enregistrée.');
  });
});

describe('Désabonnement par lien (plan L8, N11)', () => {
  it('un clic confirme ; jeton altéré : message clair', async () => {
    const { root, settle } = await render(UnsubscribePage, { params: { token: 'abc:def' } });
    expect(service['unsubscribe']).not.toHaveBeenCalled();
    button(root, 'Confirmer le désabonnement').click();
    await settle();
    expect(service['unsubscribe']).toHaveBeenCalledWith('abc:def');
    expect(text(root)).toContain('« GEST-CONF 2027 »');
    TestBed.resetTestingModule();
    const broken = await render(UnsubscribePage, { params: { token: 'x' } }, (mocks) => {
      mocks['unsubscribe'].mockRejectedValue(
        new GcApiError(400, 'unsubscribe_link_invalid', 'Lien invalide'),
      );
    });
    button(broken.root, 'Confirmer le désabonnement').click();
    await broken.settle();
    expect(text(broken.root)).toContain("Ce lien de désabonnement n'est pas valide.");
  });
});

describe('Cloche : natures du lot L8', () => {
  it('textes et liens (questionnaire, gestion)', async () => {
    const items: Notification[] = [
      {
        id: 1,
        kind: 'survey_invitation',
        payload: {
          survey_id: 6,
          title_fr: 'Votre avis',
          title_en: 'Your opinion',
          edition_code: 'GC27',
        },
        created_at: '2027-06-03T18:00:00Z',
        read_at: null,
      },
      {
        id: 2,
        kind: 'task_assigned',
        payload: { edition_id: 3, task_id: 5, title: 'Réserver le traiteur', edition_code: 'GC27' },
        created_at: '2027-05-01T08:00:00Z',
        read_at: null,
      },
      {
        id: 3,
        kind: 'shift_assigned',
        payload: {
          edition_id: 3,
          shift_id: 9,
          title: 'Accueil',
          starts_at: '2027-06-01T07:00:00Z',
          edition_code: 'GC27',
        },
        created_at: '2027-05-02T08:00:00Z',
        read_at: '2027-05-02T09:00:00Z',
      },
    ];
    TestBed.configureTestingModule({
      providers: [
        ...provideAccountTesting(),
        {
          provide: NotificationsStore,
          useValue: {
            unread: vi.fn(() => 2),
            list: vi.fn().mockResolvedValue({ unread: 2, results: items }),
            markRead: vi.fn().mockResolvedValue(undefined),
          },
        },
      ],
    });
    await useTestLanguage('fr');
    const fixture = TestBed.createComponent(NotificationsPage);
    await fixture.whenStable();
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;
    expect(text(root)).toContain('Votre avis compte (GC27) : questionnaire « Votre avis ».');
    expect(text(root)).toContain('Une tâche vous est confiée (GC27) : « Réserver le traiteur ».');
    expect(text(root)).toContain('Un poste de bénévole vous est confié (GC27) : « Accueil »');
    expect(root.querySelector('a[href="/compte/questionnaires/6"]')).not.toBeNull();
    expect(
      root.querySelector('a[href="/gestion/editions/3/organisation/taches/5"]'),
    ).not.toBeNull();
    expect(root.querySelector('a[href="/gestion/editions/3/jour-j/mon-planning"]')).not.toBeNull();
  });
});
