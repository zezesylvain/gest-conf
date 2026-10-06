import { Type } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { GcApiError, MeEdition } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';
import { of } from 'rxjs';

import {
  CHAIR_EDITION,
  FINANCE_EDITION,
  provideGestionTesting,
} from '../../../testing/gestion-testing';
import { EditionApi } from '../../core/edition-api';
import { RegistrationsApi } from '../../core/registrations-api';
import { category, profile, settings } from '../registrations/testing';
import { BillingProfilePage } from './billing-profile-page';
import { feeCells, parseCountries, PricingPage } from './pricing-page';

function text(root: HTMLElement): string {
  return (root.textContent ?? '').replace(/[\u00a0\u202f]/g, ' ');
}

function button(root: HTMLElement, label: string): HTMLButtonElement | undefined {
  return Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find((item) =>
    item.textContent!.includes(label),
  );
}

let api: Record<string, ReturnType<typeof vi.fn>>;

async function setup<T>(component: Type<T>, edition: MeEdition) {
  api = {
    settings: vi.fn().mockResolvedValue(settings()),
    updateSettings: vi.fn().mockResolvedValue(settings()),
    categories: vi.fn().mockResolvedValue([category()]),
    createCategory: vi.fn().mockResolvedValue(category({ id: 2 })),
    updateCategory: vi.fn().mockResolvedValue(category()),
    deleteCategory: vi.fn().mockResolvedValue(undefined),
    setFees: vi.fn().mockResolvedValue(category()),
    options: vi.fn().mockResolvedValue([
      {
        id: 1,
        code: 'gala',
        label_fr: 'Dîner de gala',
        label_en: 'Gala dinner',
        price_local: '10000.00',
        price_international: '15000.00',
        quota: 100,
        reserved: 12,
        categories: [],
        is_active: true,
        position: 0,
      },
    ]),
    promoCodes: vi.fn().mockResolvedValue([
      {
        id: 1,
        code: 'ETU10',
        kind: 'percent',
        value: '10.00',
        scope: 'registration',
        categories: ['student'],
        max_uses: 50,
        reserved_uses: 1,
        consumed_uses: 3,
        valid_until: '2027-04-30T23:59:00Z',
        valid_until_local: '2027-04-30T23:59:00',
        is_active: true,
      },
    ]),
    createPromoCode: vi.fn().mockResolvedValue({}),
    billingProfile: vi.fn().mockResolvedValue(profile()),
    updateBillingProfile: vi
      .fn()
      .mockResolvedValue(
        profile({ legal_name: 'Université', address: 'Abidjan', is_complete: true }),
      ),
  };
  TestBed.configureTestingModule({
    providers: [
      ...provideGestionTesting([edition]),
      { provide: RegistrationsApi, useValue: api },
      {
        provide: EditionApi,
        useValue: { edition: vi.fn().mockResolvedValue({ timezone: 'Africa/Abidjan' }) },
      },
      { provide: MatDialog, useValue: { open: () => ({ afterClosed: () => of(true) }) } },
    ],
  });
  await useTestLanguage('fr');
  const fixture = TestBed.createComponent(component);
  fixture.componentRef.setInput('editionId', '3');
  await fixture.whenStable();
  fixture.detectChanges();
  return { fixture, root: fixture.nativeElement as HTMLElement };
}

describe('Outils de la grille des tarifs (J2)', () => {
  it('cellules remplies seulement, montants nettoyés', () => {
    expect(
      feeCells({
        early_local: ' 40000 ',
        early_international: '',
        regular_local: '50000',
        onsite_international: '90000.50',
      }),
    ).toEqual([
      { period: 'early', zone: 'local', amount: '40000' },
      { period: 'regular', zone: 'local', amount: '50000' },
      { period: 'onsite', zone: 'international', amount: '90000.50' },
    ]);
  });

  it('pays locaux : séparateurs souples, majuscules', () => {
    expect(parseCountries('ci, SN ; bf\nml')).toEqual(['CI', 'SN', 'BF', 'ML']);
    expect(parseCountries('  ')).toEqual([]);
  });
});

describe('PricingPage (plan L6, J2, J5, J9 ; D13)', () => {
  it('lecture seule sans pricing.write (Chair) : grille affichée, formulaires fermés', async () => {
    const { fixture, root } = await setup(PricingPage, CHAIR_EDITION);
    const content = text(root);
    expect(content).toContain('Lecture seule');
    expect(content).toContain('40 000');
    expect(content).toContain('Dîner de gala');
    expect(content).toContain('12 / 100 réservées');
    expect(content).toContain('3 consommée(s), 1 réservée(s) / 50');
    expect(button(root, 'Ajouter une catégorie')).toBeUndefined();
    expect(button(root, 'Enregistrer')).toBeUndefined();
    const page = fixture.componentInstance as unknown as { settingsForm: { disabled: boolean } };
    expect(page.settingsForm.disabled).toBe(true);
  });

  it('D13 : date limite d’annulation saisie à l’heure de l’édition, pays normalisés', async () => {
    const { fixture } = await setup(PricingPage, FINANCE_EDITION);
    const page = fixture.componentInstance as unknown as {
      settingsForm: { getRawValue(): Record<string, unknown>; patchValue(v: object): void };
      saveSettings(): Promise<void>;
    };
    expect(page.settingsForm.getRawValue()['cancellation_deadline_local']).toBe('2027-05-01T00:00');
    expect(page.settingsForm.getRawValue()['local_countries']).toBe('CI, SN');
    page.settingsForm.patchValue({ local_countries: 'ci sn bf', online_enabled: true });
    await page.saveSettings();
    expect(api['updateSettings']).toHaveBeenCalledWith(3, {
      currency: 'XOF',
      online_enabled: true,
      transfer_enabled: true,
      onsite_enabled: true,
      online_deadline_hours: 48,
      transfer_deadline_days: 30,
      local_countries: ['CI', 'SN', 'BF'],
      cancellation_deadline_local: '2027-05-01T00:00',
      refund_percent_before: 80,
      refund_percent_after: 0,
    });
  });

  it('pays invalide : message, aucun appel', async () => {
    const { fixture, root } = await setup(PricingPage, FINANCE_EDITION);
    const page = fixture.componentInstance as unknown as {
      settingsForm: { patchValue(v: object): void };
      saveSettings(): Promise<void>;
    };
    page.settingsForm.patchValue({ local_countries: 'CIV' });
    await page.saveSettings();
    fixture.detectChanges();
    expect(api['updateSettings']).not.toHaveBeenCalled();
    expect(text(root)).toContain('codes ISO à deux lettres');
  });

  it('J2 : grille remplacée, cellule vidée = combinaison retirée', async () => {
    const { fixture, root } = await setup(PricingPage, FINANCE_EDITION);
    button(root, 'Tarifs')!.click();
    fixture.detectChanges();
    const page = fixture.componentInstance as unknown as {
      feesForm: { getRawValue(): Record<string, string>; patchValue(v: object): void };
      saveFees(): Promise<void>;
    };
    expect(page.feesForm.getRawValue()['early_local']).toBe('40000.00');
    page.feesForm.patchValue({ regular_local: '', onsite_local: '60000' });
    await page.saveFees();
    expect(api['setFees']).toHaveBeenCalledWith(3, 1, [
      { period: 'early', zone: 'local', amount: '40000.00' },
      { period: 'onsite', zone: 'local', amount: '60000' },
    ]);
  });

  it('catégorie utilisée : pas de suppression proposée ; refus du serveur affiché', async () => {
    const { fixture, root } = await setup(PricingPage, FINANCE_EDITION);
    const actions = root.querySelector('tbody tr td.actions')!;
    expect(actions.textContent).not.toContain('Supprimer');
    api['createPromoCode'].mockRejectedValue(
      new GcApiError(400, 'invalid', 'Données invalides.', { code: ['Code déjà utilisé.'] }),
    );
    button(root, 'Ajouter un code promo')!.click();
    fixture.detectChanges();
    const page = fixture.componentInstance as unknown as {
      promoForm: { patchValue(v: object): void };
      savePromo(): Promise<void>;
    };
    page.promoForm.patchValue({ code: 'ETU10', value: '10' });
    await page.savePromo();
    fixture.detectChanges();
    expect(api['createPromoCode']).toHaveBeenCalledWith(3, {
      code: 'ETU10',
      kind: 'percent',
      value: '10',
      scope: 'registration',
      categories: [],
      max_uses: null,
      valid_until_local: null,
      is_active: true,
    });
    expect(text(root)).toContain('Code déjà utilisé.');
  });
});

describe('BillingProfilePage (plan L6, J8 ; Q8)', () => {
  it('mentions incomplètes signalées ; lecture seule sans pricing.write', async () => {
    const { fixture, root } = await setup(BillingProfilePage, CHAIR_EDITION);
    expect(text(root)).toContain('aucune facture ne s');
    const page = fixture.componentInstance as unknown as { form: { disabled: boolean } };
    expect(page.form.disabled).toBe(true);
    expect(button(root, 'Enregistrer')).toBeUndefined();
  });

  it('enregistrement : taux vide = pas de TVA (null)', async () => {
    const { fixture, root } = await setup(BillingProfilePage, FINANCE_EDITION);
    const page = fixture.componentInstance as unknown as {
      form: { patchValue(v: object): void };
      save(): Promise<void>;
    };
    page.form.patchValue({
      legal_name: 'Université',
      address: 'Abidjan',
      vat_note: 'TVA non applicable',
    });
    await page.save();
    fixture.detectChanges();
    expect(api['updateBillingProfile']).toHaveBeenCalledWith(3, {
      legal_name: 'Université',
      address: 'Abidjan',
      tax_identifiers: '',
      vat_rate: null,
      vat_note: 'TVA non applicable',
      bank_details: '',
      footer: '',
      invoice_prefix: 'F',
      credit_note_prefix: 'AV',
      proforma_prefix: 'PF',
    });
    expect(text(root)).toContain('Mentions complètes');
  });
});
