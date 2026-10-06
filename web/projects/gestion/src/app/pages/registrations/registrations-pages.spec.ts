import { Type } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { Router } from '@angular/router';
import { MeEdition } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';
import { of } from 'rxjs';

import {
  CHAIR_EDITION,
  FINANCE_EDITION,
  provideGestionTesting,
} from '../../../testing/gestion-testing';
import { EditionApi } from '../../core/edition-api';
import { money, RegistrationsApi } from '../../core/registrations-api';
import { BillingDocumentsPage } from './billing-documents-page';
import { FinancePage } from './finance-page';
import { PaymentsPage } from './payments-page';
import { RegistrationDetailPage } from './registration-detail-page';
import { RegistrationsPage } from './registrations-page';
import { category, dashboard, listRow, profile, registration } from './testing';

/** CO sans fonction : lecture des inscriptions seulement (J1). */
const OC: MeEdition = {
  ...CHAIR_EDITION,
  roles: [{ role: 'OC_MEMBER', oc_function: '' }],
  capabilities: ['edition.read', 'submissions.read', 'program.read', 'registrations.read'],
};

/** Texte d'un élément, espaces insécables (montants, dates) ramenées à des espaces. */
function text(root: HTMLElement): string {
  return (root.textContent ?? '').replace(/[\u00a0\u202f]/g, ' ');
}

function button(root: HTMLElement, label: string): HTMLButtonElement | undefined {
  return Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find((item) =>
    item.textContent!.includes(label),
  );
}

let api: Record<string, ReturnType<typeof vi.fn>>;

function mockApi(): Record<string, ReturnType<typeof vi.fn>> {
  return {
    list: vi.fn().mockResolvedValue({ count: 1, next: null, previous: null, results: [listRow()] }),
    get: vi.fn().mockResolvedValue(registration()),
    create: vi.fn().mockResolvedValue(registration({ id: 13 })),
    categories: vi.fn().mockResolvedValue([category()]),
    options: vi.fn().mockResolvedValue([]),
    exportRegistrations: vi.fn().mockResolvedValue(new Blob(['a;b'])),
    recordPayment: vi.fn().mockResolvedValue(registration({ status: 'confirmed' })),
    waive: vi.fn().mockResolvedValue(registration({ status: 'confirmed', method: 'waiver' })),
    cancel: vi.fn().mockResolvedValue(registration({ status: 'cancelled' })),
    recordRefund: vi.fn().mockResolvedValue(registration({ status: 'cancelled' })),
    issueProforma: vi.fn().mockResolvedValue(registration()),
    payments: vi.fn().mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          id: 4,
          reference: 'GC27-I00012-P1',
          registration_id: 12,
          registration_reference: 'GC27-I00012',
          customer: 'Awa Koné',
          provider: 'cinetpay',
          method: 'online',
          status: 'succeeded',
          provider_reference: 'CP-778',
          provider_status: 'ACCEPTED',
          amount: '50000.00',
          currency: 'XOF',
          created_at: '2026-10-02T10:00:00Z',
          completed_at: '2026-10-02T10:05:00Z',
          received_on: null,
          note: '',
        },
      ],
    }),
    exportPayments: vi.fn().mockResolvedValue(new Blob(['a;b'])),
    documents: vi.fn().mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          id: 9,
          kind: 'credit_note',
          number: 'AV-GC27-2026-00001',
          registration_id: 12,
          registration_reference: 'GC27-I00012',
          customer: 'Awa Koné',
          original: 'F-GC27-2026-00001',
          amount: '20000.00',
          currency: 'XOF',
          issued_at: '2026-10-03T10:00:00Z',
        },
      ],
    }),
    exportDocuments: vi.fn().mockResolvedValue(new Blob(['a;b'])),
    dashboard: vi.fn().mockResolvedValue(dashboard()),
    billingProfile: vi.fn().mockResolvedValue(profile()),
    issuePendingInvoices: vi.fn().mockResolvedValue({ issued: 2 }),
  };
}

async function setup<T>(
  component: Type<T>,
  edition: MeEdition,
  inputs: Record<string, string> = {},
) {
  api = mockApi();
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
  for (const [name, value] of Object.entries(inputs)) {
    fixture.componentRef.setInput(name, value);
  }
  await fixture.whenStable();
  fixture.detectChanges();
  return { fixture, root: fixture.nativeElement as HTMLElement };
}

describe('money', () => {
  it('montant décimal au format de la langue et de la devise ; tiret si absent', () => {
    expect(money('50000.00', 'XOF', 'fr').replace(/[\u00a0\u202f]/g, ' ')).toContain('50 000');
    expect(money('12.5', 'EUR', 'en')).toBe('€12.50');
    expect(money(null, 'XOF', 'fr')).toBe('—');
  });
});

describe('RegistrationsPage (plan L6, J12)', () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => 'blob:csv');
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  });

  afterEach(() => vi.restoreAllMocks());

  it('liste : référence, participant, statut et moyen traduits, total, échéance', async () => {
    const { root } = await setup(RegistrationsPage, CHAIR_EDITION);
    const row = text(root.querySelector('tbody tr')!);
    expect(row).toContain('GC27-I00012');
    expect(row).toContain('Awa Koné');
    expect(row).toContain('awa@univ.ci');
    expect(row).toContain('en attente de paiement');
    expect(row).toContain('virement');
    expect(row).toContain('50 000');
    expect(row).toContain('à régler avant le');
    expect(api['list']).toHaveBeenCalledWith(3, { page: 1, page_size: 25 });
    expect(text(root)).toContain('1 inscription(s)');
  });

  it('filtres transmis au serveur ; export CSV aux mêmes filtres (réauthentification)', async () => {
    const { fixture } = await setup(RegistrationsPage, CHAIR_EDITION);
    const page = fixture.componentInstance as unknown as {
      form: { patchValue(v: object): void };
      search(): Promise<void>;
      exportCsv(): Promise<void>;
    };
    page.form.patchValue({ q: ' Koné ', status: 'confirmed', category: 'researcher', method: '' });
    await page.search();
    expect(api['list']).toHaveBeenLastCalledWith(3, {
      q: 'Koné',
      status: 'confirmed',
      category: 'researcher',
      page: 1,
      page_size: 25,
    });
    await page.exportCsv();
    expect(api['exportRegistrations']).toHaveBeenCalledWith(3, {
      q: 'Koné',
      status: 'confirmed',
      category: 'researcher',
    });
    expect(URL.createObjectURL).toHaveBeenCalled();
  });

  it('J1 : saisie par le CO « finances » pour un compte existant, puis fiche', async () => {
    const { fixture, root } = await setup(RegistrationsPage, FINANCE_EDITION);
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    button(root, 'Saisir une inscription')!.click();
    fixture.detectChanges();
    const page = fixture.componentInstance as unknown as {
      orderForm: { patchValue(v: object): void };
      create(): Promise<void>;
    };
    page.orderForm.patchValue({
      email: 'awa@univ.ci',
      category: 'researcher',
      method: 'onsite',
      promo_code: ' ',
    });
    await page.create();
    expect(api['create']).toHaveBeenCalledWith(3, {
      email: 'awa@univ.ci',
      category: 'researcher',
      method: 'onsite',
      options: [],
      billing_name: '',
      billing_organization: '',
      billing_address: '',
    });
    expect(navigate).toHaveBeenCalledWith(['/editions', '3', 'inscriptions', 13]);
  });

  it('Chair et CO sans fonction : consultation seule (pas de saisie)', async () => {
    for (const edition of [CHAIR_EDITION, OC]) {
      TestBed.resetTestingModule();
      const { root } = await setup(RegistrationsPage, edition);
      expect(button(root, 'Saisir une inscription')).toBeUndefined();
      expect(button(root, 'Exporter (CSV)')).toBeDefined();
    }
  });
});

describe('RegistrationDetailPage (plan L6, J7, J9)', () => {
  it('commande, pièces par l’endpoint authentifié, historique ; Chair sans action', async () => {
    const { root } = await setup(RegistrationDetailPage, CHAIR_EDITION, { registrationId: '12' });
    expect(api['get']).toHaveBeenCalledWith(3, 12);
    expect(root.querySelector('h1')!.textContent).toContain('GC27-I00012');
    const content = text(root);
    expect(content).toContain('Inscription Chercheur');
    expect(content).toContain('Dîner de gala');
    expect(content).toContain('préférentiel');
    const link = root.querySelector<HTMLAnchorElement>('a[download]')!;
    expect(link.getAttribute('href')).toBe(
      '/api/v1/manage/editions/3/registrations/12/documents/3',
    );
    expect(link.textContent).toContain('PF-GC27-2026-00001');
    expect(root.querySelector('#actions-title')).toBeNull();
  });

  it('J7 : paiement reçu hors ligne, montant total proposé, inscription confirmée', async () => {
    const { fixture, root } = await setup(RegistrationDetailPage, FINANCE_EDITION, {
      registrationId: '12',
    });
    button(root, 'Enregistrer un paiement reçu')!.click();
    fixture.detectChanges();
    const page = fixture.componentInstance as unknown as {
      paymentForm: { getRawValue(): Record<string, string>; patchValue(v: object): void };
      recordPayment(): Promise<void>;
    };
    expect(page.paymentForm.getRawValue()['amount']).toBe('50000.00');
    expect(page.paymentForm.getRawValue()['method']).toBe('transfer');
    page.paymentForm.patchValue({ received_on: '2026-10-05', reference: ' VIR-1 ' });
    await page.recordPayment();
    fixture.detectChanges();
    expect(api['recordPayment']).toHaveBeenCalledWith(3, 12, {
      method: 'transfer',
      amount: '50000.00',
      received_on: '2026-10-05',
      reference: 'VIR-1',
      note: '',
    });
    expect(text(root)).toContain('Paiement enregistré');
    expect(text(root)).toContain('confirmée');
  });

  it('J4 : gratuité refusée sans motif (aucun appel), accordée avec', async () => {
    const { fixture, root } = await setup(RegistrationDetailPage, FINANCE_EDITION, {
      registrationId: '12',
    });
    button(root, 'Accorder la gratuité')!.click();
    fixture.detectChanges();
    const page = fixture.componentInstance as unknown as {
      reasonForm: { setValue(v: object): void };
      waive(): Promise<void>;
    };
    await page.waive();
    expect(api['waive']).not.toHaveBeenCalled();
    page.reasonForm.setValue({ reason: ' Orateur invité ' });
    await page.waive();
    expect(api['waive']).toHaveBeenCalledWith(3, 12, { reason: 'Orateur invité' });
  });

  it('J9 : annulation confirmée, part remboursée vide = règle de l’édition', async () => {
    const { fixture, root } = await setup(RegistrationDetailPage, FINANCE_EDITION, {
      registrationId: '12',
    });
    button(root, "Annuler l'inscription")!.click();
    fixture.detectChanges();
    const page = fixture.componentInstance as unknown as {
      cancelForm: { patchValue(v: object): void };
      cancel(): Promise<void>;
    };
    page.cancelForm.patchValue({ reason: 'Doublon' });
    await page.cancel();
    expect(api['cancel']).toHaveBeenCalledWith(3, 12, { reason: 'Doublon', refund_percent: null });
  });

  it('J9 : remboursement après annulation d’une inscription facturée ; reste dû proposé', async () => {
    api = mockApi();
    const cancelled = registration({
      status: 'cancelled',
      refund_due: '40000.00',
      documents: [
        {
          id: 4,
          kind: 'invoice',
          number: 'F-GC27-2026-00001',
          amount: '50000.00',
          currency: 'XOF',
          issued_at: '2026-10-03T10:00:00Z',
        },
      ],
      refunds: [
        {
          id: 1,
          amount: '10000.00',
          method: 'virement',
          reference: '',
          refunded_on: '2026-10-04',
          credit_note: 'AV-GC27-2026-00001',
        },
      ],
    });
    const { fixture, root } = await setup(RegistrationDetailPage, FINANCE_EDITION, {
      registrationId: '12',
    });
    api['get'].mockResolvedValue(cancelled);
    await (fixture.componentInstance as unknown as { ngOnInit(): Promise<void> }).ngOnInit();
    fixture.detectChanges();
    expect(button(root, 'Enregistrer un paiement reçu')).toBeUndefined();
    button(root, 'Enregistrer un remboursement')!.click();
    fixture.detectChanges();
    const page = fixture.componentInstance as unknown as {
      refundForm: { getRawValue(): Record<string, string>; patchValue(v: object): void };
      recordRefund(): Promise<void>;
    };
    expect(page.refundForm.getRawValue()['amount']).toBe('30000.00');
    page.refundForm.patchValue({ method: 'mobile money', refunded_on: '2026-10-05' });
    await page.recordRefund();
    expect(api['recordRefund']).toHaveBeenCalledWith(3, 12, {
      amount: '30000.00',
      method: 'mobile money',
      reference: '',
      refunded_on: '2026-10-05',
    });
  });
});

describe('PaymentsPage et BillingDocumentsPage (finance.read)', () => {
  it('paiements : fournisseur, statut traduit, référence du fournisseur, filtres', async () => {
    const { fixture, root } = await setup(PaymentsPage, CHAIR_EDITION);
    const row = text(root.querySelector('tbody tr')!);
    expect(row).toContain('GC27-I00012-P1');
    expect(row).toContain('CP-778');
    expect(row).toContain('CinetPay');
    expect(row).toContain('réussi');
    const page = fixture.componentInstance as unknown as {
      form: { patchValue(v: object): void };
      search(): Promise<void>;
    };
    page.form.patchValue({ status: 'succeeded', provider: 'cinetpay' });
    await page.search();
    expect(api['payments']).toHaveBeenLastCalledWith(3, {
      status: 'succeeded',
      provider: 'cinetpay',
      page: 1,
      page_size: 25,
    });
  });

  it('pièces : PDF par l’endpoint authentifié (règle n° 8), facture d’origine de l’avoir', async () => {
    const { root } = await setup(BillingDocumentsPage, CHAIR_EDITION);
    const link = root.querySelector<HTMLAnchorElement>('tbody a[download]')!;
    expect(link.getAttribute('href')).toBe(
      '/api/v1/manage/editions/3/registrations/12/documents/9',
    );
    expect(text(root)).toContain('sur la facture F-GC27-2026-00001');
    expect(text(root)).toContain('Avoir');
  });
});

describe('FinancePage (plan L6, J12)', () => {
  it('montants, points à traiter, mentions incomplètes signalées ; Chair sans émission', async () => {
    const { root } = await setup(FinancePage, CHAIR_EDITION);
    const content = text(root);
    expect(content).toContain('250 000');
    expect(content).toContain('230 000');
    expect(content).toContain('Factures en attente des mentions de facturation : 2');
    expect(content).toContain('inscription non confirmée (annulée ou expirée) : 1');
    expect(content).toContain('Mentions de facturation incomplètes');
    expect(button(root, 'Émettre les factures en attente')).toBeUndefined();
  });

  it('CO « finances », mentions complètes : émission des factures en attente', async () => {
    const { fixture, root } = await setup(FinancePage, FINANCE_EDITION);
    api['billingProfile'].mockResolvedValue(profile({ is_complete: true }));
    await (fixture.componentInstance as unknown as { ngOnInit(): Promise<void> }).ngOnInit();
    fixture.detectChanges();
    button(root, 'Émettre les factures en attente')!.click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(api['issuePendingInvoices']).toHaveBeenCalledWith(3);
    expect(text(root)).toContain('2 facture(s) émise(s).');
  });
});
