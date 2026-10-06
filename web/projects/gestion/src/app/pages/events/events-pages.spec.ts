import { Type } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { MeEdition } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';
import { of } from 'rxjs';

import { CHAIR_EDITION, provideGestionTesting } from '../../../testing/gestion-testing';
import { MemoryBackend, OFFLINE_BACKEND } from '../../core/checkin-offline';
import { EventsApi } from '../../core/events-api';
import { ReceptionInstaller } from '../../core/reception';
import { RegistrationsApi } from '../../core/registrations-api';
import { category } from '../registrations/testing';
import { AttendancePage } from './attendance-page';
import { BadgesPage } from './badges-page';
import { CertificateSettingsPage } from './certificate-settings-page';
import { CertificatesPage } from './certificates-page';
import { CounterPage } from './counter-page';
import { DaySessionsPage } from './day-sessions-page';
import { LetterDetailPage } from './letter-detail-page';
import { LettersPage } from './letters-page';
import { ReceptionPage } from './reception-page';
import { SignaturePage } from './signature-page';
import {
  bundle,
  certificate,
  certificateSettings,
  checkinResult,
  checkinRow,
  daySession,
  letter,
  overview,
  signature,
  template,
} from './testing';

/** Bénévole (K1) : pointage seulement. */
const VOLUNTEER: MeEdition = {
  ...CHAIR_EDITION,
  roles: [{ role: 'VOLUNTEER', oc_function: '' }],
  capabilities: ['checkin.scan'],
};

/** CO « secrétariat » : tout le jour J, attestations et lettres (K1). */
const SECRETARIAT: MeEdition = {
  ...CHAIR_EDITION,
  roles: [{ role: 'OC_MEMBER', oc_function: 'secretariat' }],
  capabilities: [
    'edition.read',
    'registrations.read',
    'registrations.manage',
    'checkin.scan',
    'checkin.manage',
    'certificates.manage',
    'letters.manage',
  ],
};

/** Président de séance seul (K7). */
const SESSION_CHAIR: MeEdition = {
  ...CHAIR_EDITION,
  roles: [{ role: 'SESSION_CHAIR', oc_function: '' }],
  capabilities: ['sessions.chair'],
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
let installer: { install: ReturnType<typeof vi.fn> };

function mockApi(): Record<string, ReturnType<typeof vi.fn>> {
  return {
    bundle: vi.fn().mockResolvedValue(bundle()),
    scan: vi.fn().mockResolvedValue(checkinResult()),
    manual: vi.fn().mockResolvedValue(checkinResult()),
    sessionScan: vi.fn().mockResolvedValue(checkinResult()),
    sync: vi.fn().mockResolvedValue({ results: [] }),
    summary: vi.fn().mockResolvedValue({ checked_in: 3, confirmed: 40, pending: 2 }),
    checkins: vi
      .fn()
      .mockResolvedValue({ count: 1, next: null, previous: null, results: [checkinRow()] }),
    cancelCheckin: vi.fn().mockResolvedValue({}),
    exportCheckins: vi.fn().mockResolvedValue(new Blob(['a;b'])),
    daySessions: vi.fn().mockResolvedValue([daySession()]),
    attendance: vi
      .fn()
      .mockResolvedValue({ count: 1, next: null, previous: null, results: [checkinRow()] }),
    exportAttendance: vi.fn().mockResolvedValue(new Blob(['a;b'])),
    markPresented: vi.fn(),
    unmarkPresented: vi.fn(),
    badgeBatches: vi.fn().mockResolvedValue({ count: 250, batches: 2, batch_size: 200 }),
    counter: vi.fn().mockResolvedValue({
      registration_id: 44,
      reference: 'GC27-I00044',
      status: 'confirmed',
      total: '25000.00',
      currency: 'XOF',
      account_created: true,
    }),
    certificateSettings: vi.fn().mockResolvedValue(certificateSettings()),
    updateCertificateSettings: vi.fn().mockResolvedValue(certificateSettings()),
    templates: vi.fn().mockResolvedValue([template(), template({ nature: 'letter' })]),
    updateTemplate: vi
      .fn()
      .mockImplementation(async (_e: number, nature: string) =>
        template({ nature: nature as never }),
      ),
    signatories: vi
      .fn()
      .mockResolvedValue([
        { id: 2, display_name: 'Pr Yao', title_fr: 'Président', title_en: 'Chair' },
      ]),
    overview: vi
      .fn()
      .mockResolvedValue([
        overview(),
        overview({ nature: 'presentation', ready: false, problem: 'signatory_missing' }),
        overview({ nature: 'review', enabled: false, ready: false }),
      ]),
    issue: vi.fn().mockResolvedValue({ job_id: 9 }),
    certificates: vi
      .fn()
      .mockResolvedValue({ count: 1, next: null, previous: null, results: [certificate()] }),
    revokeCertificate: vi
      .fn()
      .mockResolvedValue(certificate({ revoked_at: '2027-06-05T10:00:00Z' })),
    letters: vi
      .fn()
      .mockResolvedValue({ count: 1, next: null, previous: null, results: [letter()] }),
    letter: vi.fn().mockResolvedValue(letter()),
    issueLetter: vi
      .fn()
      .mockResolvedValue(letter({ status: 'issued', issued_at: '2027-04-02T10:00:00Z' })),
    refuseLetter: vi.fn().mockResolvedValue(letter({ status: 'refused', refuse_reason: 'motif' })),
    revokeLetter: vi.fn(),
    signature: vi.fn().mockResolvedValue(signature()),
    updateSignature: vi.fn().mockResolvedValue(signature({ display_name: 'Pr K. Yao' })),
    uploadSignatureImage: vi.fn(),
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
  installer = { install: vi.fn().mockResolvedValue(false) };
  TestBed.configureTestingModule({
    providers: [
      ...provideGestionTesting([edition]),
      { provide: EventsApi, useValue: api },
      { provide: OFFLINE_BACKEND, useValue: new MemoryBackend() },
      { provide: ReceptionInstaller, useValue: installer },
      {
        provide: RegistrationsApi,
        useValue: {
          categories: vi.fn().mockResolvedValue([category({ badge_color: '#aa0000' })]),
          options: vi.fn().mockResolvedValue([]),
        },
      },
      {
        provide: MatDialog,
        useValue: {
          open: () => ({ afterClosed: () => of({ confirmed: true, reason: ' motif ' }) }),
        },
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

describe('Accueil (plan L7, K4 à K7)', () => {
  afterEach(() => localStorage.clear());

  it('écran installable, compteurs, liste à télécharger, mode accueil proposé au bénévole', async () => {
    const { root } = await setup(ReceptionPage, VOLUNTEER);
    expect(installer.install).toHaveBeenCalled();
    expect(text(root)).toContain('3 pointé(s) à l’accueil'.replace('’', "'"));
    expect(text(root)).toContain('Aucune liste hors ligne');
    expect(text(root)).toContain('Télécharger la liste hors ligne');
    // Saisie de la référence : checkin.manage seulement.
    expect(root.querySelector('input[formcontrolname=reference]')).toBeNull();
  });

  it('badge lu : résultat annoncé (zone aria-live), nom et catégorie', async () => {
    const { fixture, root, settle } = await setup(ReceptionPage, VOLUNTEER);
    await (fixture.componentInstance as unknown as { read(t: string): Promise<void> }).read(
      'jeton',
    );
    await settle();
    const zone = root.querySelector('[aria-live=assertive]')!;
    expect(text(zone as HTMLElement)).toContain('Pointé');
    expect(text(zone as HTMLElement)).toContain('Awa Koné');
    expect(text(zone as HTMLElement)).toContain('Chercheur');
    expect(zone.querySelector('.result.ok')).not.toBeNull();
  });

  it('téléchargement de la liste : gardée sur l’appareil et décrite', async () => {
    const { root, settle } = await setup(ReceptionPage, VOLUNTEER);
    button(root, 'Télécharger la liste hors ligne').click();
    await settle();
    expect(api['bundle']).toHaveBeenCalledWith(3);
    expect(text(root)).toContain('Liste de 2 participant(s)');
  });

  it('CO « secrétariat » : saisie de la référence en secours', async () => {
    const { root, settle } = await setup(ReceptionPage, SECRETARIAT);
    const input = root.querySelector<HTMLInputElement>('input[formcontrolname=reference]')!;
    input.value = 'gc27-i00012';
    input.dispatchEvent(new Event('input'));
    button(root, 'Pointer').click();
    await settle();
    expect(api['manual']).toHaveBeenCalledWith(
      3,
      expect.objectContaining({ reference: 'GC27-I00012' }),
    );
  });

  it('président de séance : mode session imposé, pas de liste hors ligne ni de compteurs', async () => {
    const { root } = await setup(ReceptionPage, SESSION_CHAIR);
    expect(api['summary']).not.toHaveBeenCalled();
    expect(text(root)).toContain('Président de séance');
    expect(text(root)).toContain('Entrée de la session : Session plénière');
  });
});

describe('Sessions du jour (plan L7, K7, K8)', () => {
  it('président de cette séance : « Marquer présentée », sans correction', async () => {
    const { root, settle } = await setup(DaySessionsPage, SESSION_CHAIR, {}, (mocks) => {
      mocks['daySessions'].mockResolvedValue([daySession({ chaired: true })]);
      mocks['markPresented'].mockResolvedValue(daySession({ chaired: true }));
    });
    expect(text(root)).toContain('vous présidez');
    button(root, 'Marquer présentée').click();
    await settle();
    expect(api['markPresented']).toHaveBeenCalledWith(3, 21, 31);
    expect(text(root)).toContain('« Réseaux de capteurs » marquée présentée');
    expect(root.textContent).not.toContain('Corriger : non présentée');
  });

  it('session d’un autre : ni « présentée » ni correction sans program.write', async () => {
    const { root } = await setup(DaySessionsPage, VOLUNTEER);
    expect(text(root)).toContain('Session plénière');
    expect(root.textContent).not.toContain('Marquer présentée');
    expect(root.textContent).not.toContain('Corriger : non présentée');
    // Présents : checkin.manage ou présidence.
    expect(root.textContent).not.toContain('Exporter les présents');
  });

  it('CO « programme » : correction d’une « présentée », avec motif', async () => {
    const { root, settle } = await setup(DaySessionsPage, {
      ...CHAIR_EDITION,
      capabilities: ['checkin.scan', 'program.read', 'program.write'],
    });
    api['unmarkPresented'].mockResolvedValue(daySession());
    button(root, 'Corriger : non présentée').click();
    await settle();
    expect(api['unmarkPresented']).toHaveBeenCalledWith(3, 21, 32, 'motif');
  });
});

describe('Présences (plan L7, K4)', () => {
  it('liste, annulation motivée d’un pointage', async () => {
    const { root, settle } = await setup(AttendancePage, SECRETARIAT);
    expect(text(root)).toContain('Awa Koné');
    expect(text(root)).toContain('scan du badge');
    button(root, 'Annuler le pointage').click();
    await settle();
    expect(api['cancelCheckin']).toHaveBeenCalledWith(3, 7, 'motif');
    expect(text(root)).toContain('Pointage de Awa Koné annulé');
  });
});

describe('Badges (plan L7, K3)', () => {
  it('lots de 200 au plus, liens filtrés par la catégorie choisie', async () => {
    const { root } = await setup(BadgesPage, SECRETARIAT);
    expect(api['badgeBatches']).toHaveBeenCalledWith(3, undefined);
    const links = Array.from(root.querySelectorAll<HTMLAnchorElement>('a[target=_blank]'));
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/api/v1/manage/editions/3/registrations/badges?batch=1',
      '/api/v1/manage/editions/3/registrations/badges?batch=2',
    ]);
    expect(text(root)).toContain('badges 201 à 250');
  });
});

describe('Comptoir (plan L7, K13)', () => {
  it('inscription d’une personne sans compte, paiement reçu, badge à imprimer', async () => {
    const { fixture, root, settle } = await setup(CounterPage, SECRETARIAT);
    const page = fixture.componentInstance as unknown as {
      form: { setValue(value: unknown): void };
    };
    page.form.setValue({
      email: 'nouvelle@univ.ci',
      first_name: 'Aya',
      last_name: 'Traoré',
      institution: 'UFHB',
      country: 'CI',
      category: 'researcher',
      options: [],
      paid: true,
    });
    button(root, 'Inscrire').click();
    await settle();
    expect(api['counter']).toHaveBeenCalledWith(3, {
      email: 'nouvelle@univ.ci',
      first_name: 'Aya',
      last_name: 'Traoré',
      institution: 'UFHB',
      country: 'CI',
      category: 'researcher',
      options: [],
      paid: true,
    });
    expect(text(root)).toContain('Inscription GC27-I00044 enregistrée');
    expect(text(root)).toContain('Compte créé sans mot de passe');
    expect(
      root.querySelector('a[href="/api/v1/manage/editions/3/registrations/44/badge"]'),
    ).not.toBeNull();
  });
});

describe('Attestations (plan L7, K9 à K11)', () => {
  it('suivi par nature : émission si prête, condition manquante sinon, nature désactivée', async () => {
    const { root, settle } = await setup(CertificatesPage, SECRETARIAT);
    expect(text(root)).toContain('Aucun signataire n’est désigné'.replace('’', "'"));
    expect(text(root)).toContain('Désactivée pour l’édition'.replace('’', "'"));
    button(root, 'Émettre').click();
    await settle();
    expect(api['issue']).toHaveBeenCalledWith(3, 'participation');
    expect(text(root)).toContain('Émission des attestations de Participation demandée');
  });

  it('révocation motivée ; PDF par lien authentifié', async () => {
    const { root, settle } = await setup(CertificatesPage, SECRETARIAT);
    expect(
      root.querySelector('a[href="/api/v1/manage/editions/3/certificates/5/pdf"]'),
    ).not.toBeNull();
    button(root, 'Révoquer').click();
    await settle();
    expect(api['revokeCertificate']).toHaveBeenCalledWith(3, 5, 'motif');
  });
});

describe('Modèle des attestations (plan L7, K18, K19)', () => {
  it('textes par défaut laissés tels quels : envoyés vides ; signataire désigné', async () => {
    const { fixture, root, settle } = await setup(CertificateSettingsPage, SECRETARIAT);
    const page = fixture.componentInstance as unknown as {
      forms: Map<string, { controls: Record<string, { setValue(v: unknown): void }> }>;
    };
    page.forms.get('participation')!.controls['signatory'].setValue(2);
    page.forms.get('participation')!.controls['title_fr'].setValue('Attestation officielle');
    const forms = root.querySelectorAll('form');
    // Formulaires : réglages, certificat, puis un par nature.
    const participation = Array.from(forms).find((form) =>
      form.textContent!.includes('Variables permises'),
    )!;
    participation.dispatchEvent(new Event('submit'));
    await settle();
    expect(api['updateTemplate']).toHaveBeenCalledWith(3, 'participation', {
      title_fr: 'Attestation officielle',
      title_en: '',
      body_fr: '',
      body_en: '',
      footer_fr: '',
      footer_en: '',
      signatory: 2,
    });
  });

  it('aperçu par lien ; avertissement sans clés de chiffrement', async () => {
    const { root } = await setup(CertificateSettingsPage, SECRETARIAT);
    expect(
      root.querySelector(
        'a[href="/api/v1/manage/editions/3/certificates/templates/letter/preview"]',
      ),
    ).not.toBeNull();
    expect(root.textContent).not.toContain('Signature PAdES indisponible');
  });
});

describe('Lettres d’invitation (plan L7, K12)', () => {
  it('liste : demandes à instruire par défaut, numéro masqué', async () => {
    const { root } = await setup(LettersPage, SECRETARIAT);
    expect(api['letters']).toHaveBeenCalledWith(3, { page: 1, page_size: 25, status: 'requested' });
    expect(text(root)).toContain('•••••2345');
    expect(root.textContent).not.toContain('20AB12345');
  });

  it('fiche : émettre, refuser avec motif', async () => {
    const { root, settle } = await setup(LetterDetailPage, SECRETARIAT, { letterId: '8' });
    expect(text(root)).toContain('20AB12345');
    button(root, 'Refuser').click();
    await settle();
    expect(api['refuseLetter']).toHaveBeenCalledWith(3, 8, 'motif');
    expect(text(root)).toContain('Demande refusée');
  });

  it('fiche : émission', async () => {
    const { root, settle } = await setup(LetterDetailPage, SECRETARIAT, { letterId: '8' });
    button(root, 'Émettre la lettre').click();
    await settle();
    expect(api['issueLetter']).toHaveBeenCalledWith(3, 8);
    expect(
      root.querySelector('a[href="/api/v1/manage/editions/3/invitation-letters/8/pdf"]'),
    ).not.toBeNull();
  });
});

describe('Ma signature (plan L7, K18)', () => {
  it('le signataire enregistre son nom et sa fonction ; image exigée pour le dépôt', async () => {
    const { root, settle } = await setup(SignaturePage, {
      ...CHAIR_EDITION,
      capabilities: ['signature.manage'],
    });
    expect(text(root)).toContain('Signature incomplète');
    button(root, 'Déposer l’image'.replace('’', "'")).click();
    await settle();
    expect(api['uploadSignatureImage']).not.toHaveBeenCalled();
    expect(text(root)).toContain('Choisissez un fichier PNG ou JPEG');
    root.querySelector('form')!.dispatchEvent(new Event('submit'));
    await settle();
    expect(api['updateSignature']).toHaveBeenCalledWith(3, {
      display_name: 'Pr Koffi Yao',
      title_fr: 'Président',
      title_en: 'Chair',
    });
    expect(text(root)).toContain('Signature enregistrée');
  });
});
