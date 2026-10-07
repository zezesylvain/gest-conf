import { Type } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { Router } from '@angular/router';
import { AnnouncementDetail, MeEdition, SurveyDetail, SurveyResults } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';
import { of } from 'rxjs';

import { CHAIR_EDITION, provideGestionTesting } from '../../../testing/gestion-testing';
import { CommunicationApi } from '../../core/communication-api';
import { ProgramApi } from '../../core/program-api';
import { AnnouncementDetailPage } from './announcement-detail-page';
import { AnnouncementsPage } from './announcements-page';
import { choicesFrom } from './communication-support';
import { SurveyDetailPage } from './survey-detail-page';
import { SurveysPage } from './surveys-page';

/** CO « communication » : annonces et questionnaires (plan L8, N2). */
const COMMUNICATION: MeEdition = {
  ...CHAIR_EDITION,
  roles: [{ role: 'OC_MEMBER', oc_function: 'communication' }],
  capabilities: ['edition.read', 'program.read', 'communications.send', 'surveys.manage'],
};

function announcement(overrides: Partial<AnnouncementDetail> = {}): AnnouncementDetail {
  return {
    id: 4,
    title_fr: 'Changement de salle',
    title_en: 'Room change',
    body_fr: '<p>La plénière a lieu en salle A.</p>',
    body_en: '',
    on_news: true,
    on_banner: false,
    on_bell: true,
    by_email: true,
    segment: 'registrations.confirmed',
    banner_message_fr: '',
    banner_message_en: '',
    banner_starts_local: null,
    banner_ends_local: null,
    status: 'draft',
    published_at: null,
    withdrawn_at: null,
    sending_status: 'none',
    recipients_count: 0,
    emails_count: 0,
    created_at: '2027-05-01T08:00:00Z',
    sending: {
      recipients: 0,
      delivered: 0,
      emails: 0,
      sent: 0,
      queued: 0,
      failed: 0,
      cancelled: 0,
      remaining_hours: 0,
    },
    ...overrides,
  };
}

function survey(overrides: Partial<SurveyDetail> = {}): SurveyDetail {
  return {
    id: 6,
    scope: 'global',
    session: null,
    session_title: '',
    title_fr: 'Votre avis',
    title_en: 'Your opinion',
    intro_fr: '',
    intro_en: '',
    opens_local: '2027-06-03T18:00',
    closes_local: '2027-06-10T18:00',
    status: 'draft',
    is_open: false,
    locked: false,
    stats: { invited: 0, answered: 0, responses: 0, threshold: 5 },
    questions: [
      {
        id: 1,
        kind: 'rating',
        label_fr: 'Organisation',
        label_en: 'Organisation',
        choices: [],
        required: true,
        position: 0,
      },
    ],
    ...overrides,
  };
}

const RESULTS: SurveyResults = {
  invited: 40,
  answered: 12,
  responses: 12,
  threshold: 5,
  questions: [
    {
      id: 1,
      kind: 'rating',
      label_fr: 'Organisation',
      label_en: 'Organisation',
      answers: 12,
      average: '4.25',
      counts: [
        { value: '5', label_fr: '5', label_en: '5', count: 6 },
        { value: '4', label_fr: '4', label_en: '4', count: 6 },
      ],
    },
    {
      id: 2,
      kind: 'text',
      label_fr: 'Commentaire',
      label_en: 'Comment',
      answers: 7,
      average: null,
      counts: [],
    },
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

let api: Record<string, ReturnType<typeof vi.fn>>;

function mockApi(): Record<string, ReturnType<typeof vi.fn>> {
  return {
    segments: vi.fn().mockResolvedValue([
      { code: 'registrations.confirmed', label: 'Inscrits confirmés', recipients: 120 },
      { code: 'committees.organizing', label: "Comité d'organisation", recipients: 9 },
    ]),
    announcements: vi.fn().mockResolvedValue([announcement()]),
    announcement: vi.fn().mockResolvedValue(announcement()),
    createAnnouncement: vi.fn().mockResolvedValue(announcement({ id: 9 })),
    updateAnnouncement: vi.fn().mockResolvedValue(announcement()),
    deleteAnnouncement: vi.fn().mockResolvedValue(undefined),
    preview: vi.fn().mockResolvedValue({
      subject: '[GEST-CONF] Annonce de la conférence',
      body_text: 'Changement de salle\n\nLa plénière a lieu en salle A.',
      body_html: '<p>…</p>',
      recipients: 120,
      opted_out: 3,
      emails: 117,
      estimated_hours: 2,
    }),
    sendTest: vi.fn().mockResolvedValue(undefined),
    publishAnnouncement: vi.fn().mockResolvedValue(
      announcement({
        status: 'published',
        published_at: '2027-05-02T08:00:00Z',
        sending_status: 'queuing',
        recipients_count: 120,
        emails_count: 117,
        sending: {
          recipients: 120,
          delivered: 40,
          emails: 117,
          sent: 10,
          queued: 30,
          failed: 0,
          cancelled: 0,
          remaining_hours: 2,
        },
      }),
    ),
    withdrawAnnouncement: vi.fn().mockResolvedValue(announcement({ status: 'withdrawn' })),
    cancelSending: vi.fn().mockResolvedValue({ cancelled: 77 }),
    surveys: vi.fn().mockResolvedValue([survey()]),
    survey: vi.fn().mockResolvedValue(survey()),
    createSurvey: vi.fn().mockResolvedValue(survey({ id: 7 })),
    updateSurvey: vi.fn().mockResolvedValue(survey()),
    deleteSurvey: vi.fn().mockResolvedValue(undefined),
    publishSurvey: vi.fn().mockResolvedValue(survey({ status: 'published' })),
    duplicateSurvey: vi.fn().mockResolvedValue(survey({ id: 8 })),
    addQuestion: vi.fn().mockResolvedValue({}),
    updateQuestion: vi.fn().mockResolvedValue({}),
    deleteQuestion: vi.fn().mockResolvedValue(undefined),
    results: vi.fn().mockResolvedValue({ ...RESULTS, responses: 3, questions: [] }),
    exportSurvey: vi.fn().mockResolvedValue(new Blob(['a;b'])),
  };
}

async function setup<T>(
  component: Type<T>,
  inputs: Record<string, string> = {},
  prepare: (mocks: typeof api) => void = () => undefined,
) {
  api = mockApi();
  prepare(api);
  TestBed.configureTestingModule({
    providers: [
      ...provideGestionTesting([COMMUNICATION]),
      { provide: CommunicationApi, useValue: api },
      {
        provide: ProgramApi,
        useValue: {
          board: vi.fn().mockResolvedValue({
            sessions: [{ id: 21, title_fr: 'Plénière', title_en: 'Plenary', kind: 'plenary' }],
          }),
        },
      },
      {
        provide: MatDialog,
        useValue: { open: () => ({ afterClosed: () => of({ confirmed: true }) }) },
      },
    ],
  });
  await useTestLanguage('fr');
  const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
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
  return { fixture, root: fixture.nativeElement as HTMLElement, settle, navigate };
}

describe('Annonces (plan L8, N10, N11)', () => {
  it('liste : canaux, segment nommé, état ; création puis ouverture de la fiche', async () => {
    const { fixture, root, settle, navigate } = await setup(AnnouncementsPage);
    expect(text(root)).toContain('Changement de salle');
    expect(text(root)).toContain('Actualités');
    expect(text(root)).toContain('Cloche');
    expect(text(root)).toContain('Inscrits confirmés');
    expect(text(root)).toContain('Brouillon');
    const component = fixture.componentInstance as unknown as {
      form: { setValue(value: unknown): void };
    };
    component.form.setValue({ title_fr: ' Programme publié ' });
    button(root, "Créer et ouvrir l'annonce").click();
    await settle();
    expect(api['createAnnouncement']).toHaveBeenCalledWith(3, { title_fr: 'Programme publié' });
    expect(navigate).toHaveBeenCalledWith(['/editions', '3', 'communication', 'annonces', 9]);
  });

  it('fiche : aperçu chiffré, essai, publication confirmée avec le nombre de destinataires', async () => {
    const { root, settle } = await setup(AnnouncementDetailPage, { announcementId: '4' });
    expect(api['announcement']).toHaveBeenCalledWith(3, 4);
    button(root, 'Aperçu en français').click();
    await settle();
    expect(api['preview']).toHaveBeenCalledWith(3, 4, 'fr');
    expect(text(root)).toContain('120 destinataire(s) dont 3 désabonné(s) : 117 e-mail(s)');
    expect(text(root)).toContain('La plénière a lieu en salle A.');
    button(root, "M'envoyer un essai").click();
    await settle();
    expect(api['sendTest']).toHaveBeenCalledWith(3, 4);
    expect(text(root)).toContain('Essai envoyé');
    button(root, 'Publier').click();
    await settle();
    expect(api['publishAnnouncement']).toHaveBeenCalledWith(3, 4);
    expect(text(root)).toContain('Annonce publiée.');
    expect(text(root)).toContain('E-mails partis');
    expect(text(root)).toContain('10 / 117');
    // Publiée : cloche, e-mail et destinataires figés.
    expect(
      root.querySelector<HTMLInputElement>('mat-checkbox[formcontrolname="by_email"] input')!
        .disabled,
    ).toBe(true);
  });

  it('enregistrement : fenêtre du bandeau vide envoyée nulle ; annulation de l’envoi', async () => {
    const { fixture, root, settle } = await setup(
      AnnouncementDetailPage,
      { announcementId: '4' },
      (mocks) => {
        const sending = announcement({ status: 'published', sending_status: 'queued' });
        mocks['announcement'].mockResolvedValue(sending);
        mocks['updateAnnouncement'].mockResolvedValue(sending);
      },
    );
    const component = fixture.componentInstance as unknown as {
      form: { patchValue(value: unknown): void };
    };
    component.form.patchValue({ on_banner: true, banner_message_fr: 'Salle A' });
    await settle();
    button(root, 'Enregistrer').click();
    await settle();
    expect(api['updateAnnouncement']).toHaveBeenCalledWith(
      3,
      4,
      expect.objectContaining({
        on_banner: true,
        banner_message_fr: 'Salle A',
        banner_starts_local: null,
        banner_ends_local: null,
      }),
    );
    // Champs figés après publication : absents du corps envoyé.
    expect(api['updateAnnouncement'].mock.calls[0][2]).not.toHaveProperty('segment');
    button(root, "Annuler l'envoi").click();
    await settle();
    expect(api['cancelSending']).toHaveBeenCalledWith(3, 4);
    expect(text(root)).toContain('77 e-mail(s) annulé(s).');
  });
});

describe('Questionnaires (plan L8, N12, RG-21)', () => {
  it('choix saisis une ligne par choix, lignes anglaises appariées', () => {
    expect(choicesFrom('Oui\n\n Non \nPeut-être', 'Yes\nNo')).toEqual([
      { label_fr: 'Oui', label_en: 'Yes' },
      { label_fr: 'Non', label_en: 'No' },
      { label_fr: 'Peut-être', label_en: '' },
    ]);
  });

  it('liste et création d’un questionnaire de session', async () => {
    const { fixture, root, settle, navigate } = await setup(SurveysPage);
    expect(text(root)).toContain('Votre avis');
    expect(text(root)).toContain('0 réponse(s) sur 0 invité(s)');
    const component = fixture.componentInstance as unknown as {
      form: { setValue(value: unknown): void };
    };
    component.form.setValue({
      title_fr: 'Plénière',
      scope: 'session',
      session: 21,
      default_questions: false,
    });
    button(root, 'Créer et ouvrir le questionnaire').click();
    await settle();
    expect(api['createSurvey']).toHaveBeenCalledWith(3, {
      title_fr: 'Plénière',
      scope: 'session',
      session: 21,
      default_questions: false,
    });
    expect(navigate).toHaveBeenCalledWith(['/editions', '3', 'communication', 'questionnaires', 7]);
  });

  it('fiche : seuil non atteint, question à choix ajoutée, publication', async () => {
    const { fixture, root, settle } = await setup(SurveyDetailPage, { surveyId: '6' });
    expect(text(root)).toContain("les résultats s'affichent à partir de 5");
    const component = fixture.componentInstance as unknown as {
      questionForm: { setValue(value: unknown): void };
    };
    component.questionForm.setValue({
      kind: 'single',
      label_fr: 'Venue',
      label_en: '',
      required: false,
      choices_fr: 'Oui\nNon',
      choices_en: 'Yes\nNo',
    });
    await settle();
    button(root, 'Ajouter la question').click();
    await settle();
    expect(api['addQuestion']).toHaveBeenCalledWith(3, 6, {
      kind: 'single',
      label_fr: 'Venue',
      label_en: '',
      required: false,
      choices: [
        { label_fr: 'Oui', label_en: 'Yes' },
        { label_fr: 'Non', label_en: 'No' },
      ],
    });
    button(root, 'Publier').click();
    await settle();
    expect(api['publishSurvey']).toHaveBeenCalledWith(3, 6);
    expect(text(root)).toContain('Questionnaire publié.');
  });

  it('verrouillé et publié : questions figées, seule la clôture change ; résultats et export', async () => {
    const { root, settle } = await setup(SurveyDetailPage, { surveyId: '6' }, (mocks) => {
      mocks['survey'].mockResolvedValue(survey({ status: 'published', locked: true }));
      mocks['results'].mockResolvedValue(RESULTS);
    });
    expect(text(root)).toContain('les questions ne changent plus');
    expect(text(root)).not.toContain('Ajouter la question');
    expect(text(root)).toContain('Moyenne : 4.25 sur 5');
    expect(text(root)).toContain('7 commentaire(s)');
    button(root, 'Enregistrer').click();
    await settle();
    expect(api['updateSurvey'].mock.calls[0][2]).toEqual({
      title_fr: 'Votre avis',
      title_en: 'Your opinion',
      intro_fr: '',
      intro_en: '',
      closes_local: '2027-06-10T18:00',
    });
    button(root, 'Exporter (XLSX)').click();
    await settle();
    expect(api['exportSurvey']).toHaveBeenCalledWith(3, 6, 'xlsx');
  });
});
