import { TestBed } from '@angular/core/testing';
import { GcApiError, MyCertificate, MyLetter, MyRegistration } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';

import { myRegistration } from '../../site/registration/testing';
import { RegistrationService } from '../registration/registration.service';
import { provideAccountTesting } from '../testing';
import { DocumentsPage } from './documents-page';
import { DocumentsService, formatDay } from './documents.service';

function text(root: HTMLElement): string {
  return (root.textContent ?? '').replace(/[\u00a0\u202f]/g, ' ').replace(/\s+/g, ' ');
}

async function settle(fixture: { detectChanges(): void }): Promise<void> {
  for (let i = 0; i < 5; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  fixture.detectChanges();
}

function button(root: HTMLElement, label: string): HTMLButtonElement {
  const found = Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find((item) =>
    item.textContent!.includes(label),
  );
  if (!found) throw new Error(`Bouton « ${label} » absent`);
  return found;
}

function certificate(overrides: Partial<MyCertificate> = {}): MyCertificate {
  return {
    id: 5,
    nature: 'participation',
    edition_code: 'GC27',
    edition_title_fr: 'GEST-CONF 2027',
    edition_title_en: 'GEST-CONF 2027',
    title: '',
    issued_at: '2027-06-04T10:00:00Z',
    revoked: false,
    verification_url: 'https://conf.example/verification/ABCDEF234567',
    ...overrides,
  };
}

function letter(overrides: Partial<MyLetter> = {}): MyLetter {
  return {
    id: 8,
    status: 'requested',
    passport_name: 'KONE AWA',
    nationality: 'Ivoirienne',
    passport_number_masked: '•••••345',
    stay_from: '2027-05-30',
    stay_to: '2027-06-05',
    embassy: 'Ambassade de France, Abidjan',
    refuse_reason: '',
    requested_at: '2027-04-01T10:00:00Z',
    issued_at: null,
    verification_url: '',
    ...overrides,
  };
}

describe('« Mes documents » (plan L7, K15)', () => {
  let service: Record<string, ReturnType<typeof vi.fn>>;

  async function render(
    registrations: MyRegistration[],
    certificates: MyCertificate[] = [],
    current: MyLetter | null = null,
  ) {
    service = {
      certificates: vi.fn().mockResolvedValue(certificates),
      letter: vi.fn().mockResolvedValue(current),
      requestLetter: vi.fn().mockResolvedValue(letter()),
    };
    TestBed.configureTestingModule({
      providers: [
        ...provideAccountTesting(),
        { provide: DocumentsService, useValue: service },
        {
          provide: RegistrationService,
          useValue: { list: vi.fn().mockResolvedValue(registrations) },
        },
      ],
    });
    await useTestLanguage('fr');
    const fixture = TestBed.createComponent(DocumentsPage);
    fixture.detectChanges();
    await settle(fixture);
    return { fixture, root: fixture.nativeElement as HTMLElement };
  }

  it('badge dès la confirmation (lien authentifié), attestations valides et révoquées', async () => {
    const { root } = await render(
      [myRegistration({ id: 12, status: 'confirmed', has_qr: true })],
      [
        certificate(),
        certificate({ id: 6, nature: 'presentation', title: 'Réseaux de capteurs', revoked: true }),
      ],
    );
    expect(root.querySelector('a[href="/api/v1/registrations/12/badge"]')).not.toBeNull();
    expect(text(root)).toContain('Attestation de participation — GEST-CONF 2027');
    expect(root.querySelector('a[href="/api/v1/me/certificates/5/pdf"]')).not.toBeNull();
    expect(
      root.querySelector('a[href="https://conf.example/verification/ABCDEF234567"]'),
    ).not.toBeNull();
    // Révoquée : signalée, sans PDF.
    expect(text(root)).toContain('« Réseaux de capteurs »');
    expect(text(root)).toContain('Révoquée');
    expect(root.querySelector('a[href="/api/v1/me/certificates/6/pdf"]')).toBeNull();
  });

  it('inscription en attente : pas encore de badge ; aucune attestation', async () => {
    const { root } = await render([myRegistration({ id: 12, status: 'pending' })]);
    expect(root.querySelector('a[href$="/badge"]')).toBeNull();
    expect(text(root)).toContain(
      'Votre badge sera disponible dès que votre inscription sera confirmée',
    );
    expect(text(root)).toContain('Aucune attestation pour le moment');
    expect(service['letter']).toHaveBeenCalledWith(12);
  });

  it('sans inscription en cours : pas de demande de lettre possible', async () => {
    const { root } = await render([myRegistration({ status: 'cancelled' })]);
    expect(service['letter']).not.toHaveBeenCalled();
    expect(text(root)).toContain('Une inscription en cours est nécessaire');
  });

  it('demande de lettre : formulaire, envoi, suivi « en cours d’examen »', async () => {
    const { fixture, root } = await render([myRegistration({ id: 12, status: 'confirmed' })]);
    button(root, "Demander une lettre d'invitation").click();
    await settle(fixture);
    const page = fixture.componentInstance as unknown as {
      letterForm: { setValue(value: object): void };
    };
    page.letterForm.setValue({
      passport_name: ' KONE AWA ',
      nationality: 'Ivoirienne',
      passport_number: '20AB12345',
      stay_from: '2027-05-30',
      stay_to: '2027-06-05',
      embassy: 'Ambassade de France, Abidjan',
    });
    root.querySelector('form')!.dispatchEvent(new Event('submit'));
    await settle(fixture);
    expect(service['requestLetter']).toHaveBeenCalledWith(12, {
      passport_name: 'KONE AWA',
      nationality: 'Ivoirienne',
      passport_number: '20AB12345',
      stay_from: '2027-05-30',
      stay_to: '2027-06-05',
      embassy: 'Ambassade de France, Abidjan',
    });
    expect(text(root)).toContain('Demande envoyée');
    expect(text(root)).toContain("Demande en cours d'examen");
    expect(text(root)).toContain('•••••345');
    // Une demande en cours : pas de nouvelle demande.
    expect(root.textContent).not.toContain('Faire une nouvelle demande');
  });

  it('refus de règle (409) : message du serveur ; erreur de champ posée sur le champ', async () => {
    const { fixture, root } = await render([myRegistration({ id: 12, status: 'confirmed' })]);
    service['requestLetter'].mockRejectedValue(
      new GcApiError(400, 'validation_error', 'Invalide', {
        stay_to: ['Séjour de 90 jours au plus.'],
      }),
    );
    button(root, "Demander une lettre d'invitation").click();
    await settle(fixture);
    const page = fixture.componentInstance as unknown as {
      letterForm: { setValue(value: object): void; controls: { stay_to: { errors: unknown } } };
    };
    page.letterForm.setValue({
      passport_name: 'KONE AWA',
      nationality: 'Ivoirienne',
      passport_number: '20AB12345',
      stay_from: '2027-01-01',
      stay_to: '2027-12-31',
      embassy: 'Ambassade',
    });
    root.querySelector('form')!.dispatchEvent(new Event('submit'));
    await settle(fixture);
    expect(page.letterForm.controls.stay_to.errors).toEqual({
      server: ['Séjour de 90 jours au plus.'],
    });
  });

  it('lettre refusée : motif, nouvelle demande pré-remplie sans le numéro de passeport', async () => {
    const { fixture, root } = await render(
      [myRegistration({ id: 12, status: 'confirmed' })],
      [],
      letter({ status: 'refused', refuse_reason: 'Dates hors conférence' }),
    );
    expect(text(root)).toContain('Motif du refus : Dates hors conférence');
    button(root, 'Faire une nouvelle demande').click();
    await settle(fixture);
    const page = fixture.componentInstance as unknown as {
      letterForm: { getRawValue(): Record<string, string> };
    };
    expect(page.letterForm.getRawValue()).toMatchObject({
      passport_name: 'KONE AWA',
      passport_number: '',
      embassy: 'Ambassade de France, Abidjan',
    });
  });

  it('lettre émise : téléchargement et rappel de sa portée', async () => {
    const { root } = await render(
      [myRegistration({ id: 12, status: 'confirmed' })],
      [],
      letter({ status: 'issued', issued_at: '2027-04-02T10:00:00Z' }),
    );
    expect(
      root.querySelector('a[href="/api/v1/registrations/12/invitation-letter/pdf"]'),
    ).not.toBeNull();
    expect(text(root)).toContain("n'engage pas l'organisation");
  });

  it('date civile dans la langue de l’interface, sans décalage de fuseau', () => {
    expect(formatDay('2027-06-01', 'fr')).toBe('1 juin 2027');
    expect(formatDay('2027-06-01', 'en')).toBe('June 1, 2027');
  });
});
