import type {
  BillingProfile,
  Category,
  FinanceDashboard,
  ManageRegistration,
  ManageRegistrationList,
  RegistrationSettings,
} from '@gestconf/shared';

/** Ligne de liste de test : inscription en attente, par virement. */
export function listRow(overrides: Partial<ManageRegistrationList> = {}): ManageRegistrationList {
  return {
    id: 12,
    reference: 'GC27-I00012',
    person: { id: 5, name: 'Awa Koné', email: 'awa@univ.ci', country: 'CI' },
    category: {
      code: 'researcher',
      label_fr: 'Chercheur',
      label_en: 'Researcher',
      requires_proof: false,
    },
    status: 'pending',
    method: 'transfer',
    total: '50000.00',
    currency: 'XOF',
    due_at: '2026-11-01T00:00:00Z',
    created_at: '2026-10-02T10:00:00Z',
    confirmed_at: null,
    has_proof: false,
    has_invoice: false,
    ...overrides,
  };
}

/** Détail de test : en attente, une ligne d'inscription et une option, une pro forma. */
export function registration(overrides: Partial<ManageRegistration> = {}): ManageRegistration {
  return {
    id: 12,
    reference: 'GC27-I00012',
    edition: {
      code: 'GC27',
      title_fr: 'GEST-CONF 2027',
      title_en: 'GEST-CONF 2027',
      timezone: 'Africa/Abidjan',
    },
    person: { id: 5, name: 'Awa Koné', email: 'awa@univ.ci', country: 'CI' },
    category: {
      code: 'researcher',
      label_fr: 'Chercheur',
      label_en: 'Researcher',
      requires_proof: false,
    },
    period: 'early',
    zone: 'local',
    status: 'pending',
    method: 'transfer',
    total: '50000.00',
    currency: 'XOF',
    lines: [
      {
        kind: 'registration',
        code: 'researcher',
        label_fr: 'Inscription Chercheur',
        label_en: 'Researcher registration',
        amount: '40000.00',
      },
      {
        kind: 'option',
        code: 'gala',
        label_fr: 'Dîner de gala',
        label_en: 'Gala dinner',
        amount: '10000.00',
      },
    ],
    billing_name: 'Awa Koné',
    billing_organization: 'UFHB',
    billing_address: 'Abidjan',
    due_at: '2026-11-01T00:00:00Z',
    created_at: '2026-10-02T10:00:00Z',
    confirmed_at: null,
    closed_at: null,
    refund_due: null,
    has_qr: false,
    proof: null,
    documents: [
      {
        id: 3,
        kind: 'proforma',
        number: 'PF-GC27-2026-00001',
        amount: '50000.00',
        currency: 'XOF',
        issued_at: '2026-10-02T10:00:00Z',
      },
    ],
    payments: [],
    refunds: [],
    history: [
      {
        from_status: '',
        to_status: 'pending',
        at: '2026-10-02T10:00:00Z',
        actor: 'Awa Koné',
        reason: '',
      },
    ],
    ...overrides,
  };
}

export function category(overrides: Partial<Category> = {}): Category {
  return {
    id: 1,
    code: 'researcher',
    label_fr: 'Chercheur',
    label_en: 'Researcher',
    requires_proof: false,
    is_active: true,
    position: 0,
    in_use: true,
    fees: [
      { period: 'early', zone: 'local', amount: '40000.00' },
      { period: 'regular', zone: 'local', amount: '50000.00' },
    ],
    ...overrides,
  };
}

export function settings(overrides: Partial<RegistrationSettings> = {}): RegistrationSettings {
  return {
    currency: 'XOF',
    local_countries: ['CI', 'SN'],
    online_enabled: false,
    transfer_enabled: true,
    onsite_enabled: true,
    online_deadline_hours: 48,
    transfer_deadline_days: 30,
    cancellation_deadline: '2027-05-01T00:00:00Z',
    cancellation_deadline_local: '2027-05-01T00:00:00',
    refund_percent_before: 80,
    refund_percent_after: 0,
    ...overrides,
  };
}

export function profile(overrides: Partial<BillingProfile> = {}): BillingProfile {
  return {
    legal_name: '',
    address: '',
    tax_identifiers: '',
    vat_rate: null,
    vat_note: '',
    bank_details: '',
    footer: '',
    invoice_prefix: 'F',
    credit_note_prefix: 'AV',
    proforma_prefix: 'PF',
    is_complete: false,
    ...overrides,
  };
}

export function dashboard(overrides: Partial<FinanceDashboard> = {}): FinanceDashboard {
  return {
    currency: 'XOF',
    registrations: { pending: 2, confirmed: 5, cancelled: 1, expired: 0 },
    collected: '250000.00',
    refunded: '20000.00',
    net: '230000.00',
    outstanding: '100000.00',
    refunds_due: '0.00',
    by_method: [{ method: 'transfer', count: 5, amount: '250000.00' }],
    by_category: [
      {
        code: 'researcher',
        label_fr: 'Chercheur',
        label_en: 'Researcher',
        confirmed: 5,
        amount: '250000.00',
      },
    ],
    invoices: { count: 5, amount: '250000.00' },
    credit_notes: { count: 1, amount: '20000.00' },
    pending_invoices: 2,
    orphan_payments: 1,
    waivers: 0,
    ...overrides,
  };
}
