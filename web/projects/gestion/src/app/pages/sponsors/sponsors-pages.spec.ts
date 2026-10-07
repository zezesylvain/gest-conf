import { Type } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { Router } from '@angular/router';
import { GcApiError, MeEdition, SponsorDetail, SponsorLevel } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';
import { of } from 'rxjs';

import { CHAIR_EDITION, provideGestionTesting } from '../../../testing/gestion-testing';
import { SponsorsApi } from '../../core/sponsors-api';
import { SponsorDetailPage } from './sponsor-detail-page';
import { SponsorLevelsPage } from './sponsor-levels-page';
import { SponsorsPage } from './sponsors-page';

/** CO « relations extérieures » : partenaires en lecture et en écriture (plan L8, N2). */
const RELATIONS: MeEdition = {
  ...CHAIR_EDITION,
  roles: [{ role: 'OC_MEMBER', oc_function: 'external_relations' }],
  capabilities: ['edition.read', 'sponsors.read', 'sponsors.write'],
};

/** CO « finances » : partenaires en lecture seule. */
const READER: MeEdition = {
  ...CHAIR_EDITION,
  roles: [{ role: 'OC_MEMBER', oc_function: 'finance' }],
  capabilities: ['edition.read', 'sponsors.read'],
};

function level(overrides: Partial<SponsorLevel> = {}): SponsorLevel {
  return {
    id: 2,
    name_fr: 'Or',
    name_en: 'Gold',
    amount: '5000000.00',
    benefits_fr: 'Stand\nLogo sur les badges',
    benefits_en: 'Booth\nLogo on badges',
    logo_size: 'large',
    position: 0,
    sponsor_count: 1,
    ...overrides,
  };
}

function detail(overrides: Partial<SponsorDetail> = {}): SponsorDetail {
  return {
    id: 8,
    name: 'Banque du Golfe',
    level: 2,
    published: true,
    status: 'agreed',
    agreed_amount: '5000000.00',
    received_amount: null,
    received_on: null,
    position: 0,
    logo: {
      url: '/api/v1/public/files/abc/logo.png',
      preview_url: '/api/v1/manage/editions/3/sponsors/8/logo',
      width: 300,
      height: 120,
    },
    benefits_due: 2,
    benefits_delivered: 1,
    website: 'https://banque.example',
    description_fr: 'Banque régionale',
    description_en: 'Regional bank',
    contact_name: 'Awa Koné',
    contact_email: 'awa@banque.example',
    contact_phone: '+225 01 02 03 04',
    note: 'Relancer en mai',
    benefits: [
      { id: 31, label: 'Stand', delivered_on: '2027-05-02', position: 0 },
      { id: 32, label: 'Logo sur les badges', delivered_on: null, position: 1 },
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
    sponsors: vi.fn().mockResolvedValue({
      totals: {
        currency: 'XOF',
        agreed: '5000000.00',
        received: '0.00',
        by_status: { prospect: 2, agreed: 1 },
      },
      sponsors: [
        detail(),
        detail({
          id: 9,
          name: 'Télécom',
          level: null,
          published: false,
          status: 'prospect',
          agreed_amount: null,
        }),
      ],
    }),
    sponsor: vi.fn().mockResolvedValue(detail()),
    create: vi.fn().mockResolvedValue(detail({ id: 10, name: 'Nouveau' })),
    update: vi.fn().mockResolvedValue(detail({ status: 'received' })),
    remove: vi.fn().mockResolvedValue(undefined),
    exportSponsors: vi.fn().mockResolvedValue(new Blob(['a;b'])),
    uploadLogo: vi.fn().mockResolvedValue(detail()),
    removeLogo: vi.fn().mockResolvedValue(detail({ logo: null })),
    addBenefit: vi.fn().mockResolvedValue(detail()),
    markBenefit: vi.fn().mockResolvedValue(detail()),
    removeBenefit: vi.fn().mockResolvedValue(detail()),
    levels: vi
      .fn()
      .mockResolvedValue([
        level(),
        level({ id: 3, name_fr: 'Argent', name_en: 'Silver', sponsor_count: 0 }),
      ]),
    createLevel: vi
      .fn()
      .mockResolvedValue([
        level(),
        level({ id: 3, name_fr: 'Argent', name_en: 'Silver', sponsor_count: 0 }),
      ]),
    updateLevel: vi.fn().mockResolvedValue([level()]),
    deleteLevel: vi.fn().mockResolvedValue([level()]),
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
      { provide: SponsorsApi, useValue: api },
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

describe('Partenaires (plan L8, N5)', () => {
  it('totaux, effectifs par statut, niveau, contreparties, publication ; export', async () => {
    const { root, settle } = await setup(SponsorsPage, READER);
    expect(text(root)).toContain('Contributions convenues');
    expect(text(root)).toContain('5 000 000');
    expect(text(root)).toContain('Prospect');
    expect(text(root)).toContain('Or');
    expect(text(root)).toContain('1 livrée(s) sur 2');
    expect(text(root)).toContain('Non publié');
    expect(root.querySelector('a[href="/editions/3/partenaires/8"]')).not.toBeNull();
    expect(text(root)).not.toContain('Nouveau partenaire');
    button(root, 'Exporter (XLSX)').click();
    await settle();
    expect(api['exportSponsors']).toHaveBeenCalledWith(3, 'xlsx');
  });

  it('création : nom nettoyé, puis ouverture de la fiche', async () => {
    const { fixture, root, settle, navigate } = await setup(SponsorsPage, RELATIONS);
    const component = fixture.componentInstance as unknown as {
      form: { patchValue(value: unknown): void };
    };
    component.form.patchValue({ name: ' Nouveau ', level: 2 });
    button(root, 'Créer et ouvrir la fiche').click();
    await settle();
    expect(api['create']).toHaveBeenCalledWith(3, {
      name: 'Nouveau',
      level: 2,
      status: 'prospect',
    });
    expect(navigate).toHaveBeenCalledWith(['/editions', '3', 'partenaires', 10]);
  });
});

describe('Fiche d’un partenaire (plan L8, N5)', () => {
  it('parties publique et privée, montants vides envoyés nuls, logo affiché', async () => {
    const { fixture, root, settle } = await setup(SponsorDetailPage, RELATIONS, {
      sponsorId: '8',
    });
    expect(api['sponsor']).toHaveBeenCalledWith(3, 8);
    // Aperçu authentifié : l'adresse publique ne sert pas le logo d'un partenaire non publié.
    expect(root.querySelector('img[alt="Logo de Banque du Golfe"]')!.getAttribute('src')).toBe(
      '/api/v1/manage/editions/3/sponsors/8/logo',
    );
    expect(text(root)).toContain('livrée le');
    const component = fixture.componentInstance as unknown as {
      form: { patchValue(value: unknown): void };
    };
    component.form.patchValue({
      status: 'received',
      received_amount: '5000000',
      received_on: '2027-05-10',
    });
    button(root, 'Enregistrer').click();
    await settle();
    expect(api['update']).toHaveBeenCalledWith(
      3,
      8,
      expect.objectContaining({
        status: 'received',
        received_amount: '5000000',
        received_on: '2027-05-10',
        contact_email: 'awa@banque.example',
      }),
    );
    expect(text(root)).toContain('Fiche enregistrée.');
  });

  it('contribution reçue sans montant : refus du serveur affiché', async () => {
    const { root, settle } = await setup(
      SponsorDetailPage,
      RELATIONS,
      { sponsorId: '8' },
      (mocks) => {
        mocks['update'].mockRejectedValue(
          new GcApiError(400, 'invalid', 'Invalide', {
            received_amount: ['Montant reçu et date obligatoires.'],
          }),
        );
      },
    );
    button(root, 'Enregistrer').click();
    await settle();
    expect(text(root)).toContain('Montant reçu et date obligatoires.');
  });

  it('contreparties : cochée livrée aujourd’hui, décochée, ajoutée ; logo retiré ; suppression', async () => {
    const { fixture, root, settle, navigate } = await setup(SponsorDetailPage, RELATIONS, {
      sponsorId: '8',
    });
    const component = fixture.componentInstance as unknown as {
      toggleBenefit(benefit: unknown, delivered: boolean): Promise<void>;
      benefitForm: { setValue(value: unknown): void };
    };
    await component.toggleBenefit({ id: 32 }, true);
    expect(api['markBenefit']).toHaveBeenCalledWith(
      3,
      8,
      32,
      expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
    );
    await component.toggleBenefit({ id: 31 }, false);
    expect(api['markBenefit']).toHaveBeenCalledWith(3, 8, 31, null);
    component.benefitForm.setValue({ label: ' Visibilité ' });
    await settle();
    button(root, 'Ajouter la contrepartie').click();
    await settle();
    expect(api['addBenefit']).toHaveBeenCalledWith(3, 8, 'Visibilité');
    button(root, 'Retirer le logo').click();
    await settle();
    expect(api['removeLogo']).toHaveBeenCalledWith(3, 8);
    button(root, 'Supprimer le partenaire').click();
    await settle();
    expect(api['remove']).toHaveBeenCalledWith(3, 8);
    expect(navigate).toHaveBeenCalledWith(['/editions', '3', 'partenaires']);
  });

  it('lecture seule : champs figés, ni dépôt de logo ni suppression', async () => {
    const { root } = await setup(SponsorDetailPage, READER, { sponsorId: '8' });
    expect(root.querySelector<HTMLInputElement>('input[formcontrolname="name"]')!.disabled).toBe(
      true,
    );
    expect(root.querySelector('input[type="file"]')).toBeNull();
    expect(text(root)).not.toContain('Supprimer le partenaire');
  });
});

describe('Niveaux de partenariat (plan L8, N5)', () => {
  it('montant dans la devise, niveau attribué non supprimable, création', async () => {
    const { fixture, root, settle } = await setup(SponsorLevelsPage, RELATIONS);
    expect(text(root)).toContain('Or');
    expect(text(root)).toContain('5 000 000');
    expect(text(root)).toContain('Grande');
    expect(root.querySelector('[aria-label="Supprimer le niveau Or"]')).toBeNull();
    expect(root.querySelector('[aria-label="Supprimer le niveau Argent"]')).not.toBeNull();
    const component = fixture.componentInstance as unknown as {
      form: { patchValue(value: unknown): void };
    };
    component.form.patchValue({ name_fr: 'Bronze', amount: '' });
    button(root, 'Ajouter le niveau').click();
    await settle();
    expect(api['createLevel']).toHaveBeenCalledWith(
      3,
      expect.objectContaining({ name_fr: 'Bronze', amount: null, logo_size: 'medium' }),
    );
    (root.querySelector('[aria-label="Supprimer le niveau Argent"]') as HTMLElement).click();
    await settle();
    expect(api['deleteLevel']).toHaveBeenCalledWith(3, 3);
  });

  it('lecture seule : ni formulaire ni actions', async () => {
    const { root } = await setup(SponsorLevelsPage, READER);
    expect(text(root)).not.toContain('Nouveau niveau');
    expect(text(root)).not.toContain('Actions');
  });
});
