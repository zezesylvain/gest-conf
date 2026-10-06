import type { MyRegistration, PublicRegistration } from '@gestconf/shared';

/** Catalogue de test : deux catégories, une option réservée aux chercheurs, deux moyens. */
export const CATALOG: PublicRegistration = {
  currency: 'XOF',
  timezone: 'Africa/Abidjan',
  opens_at: '2027-01-15T00:00:00Z',
  early_bird_end: '2027-04-30T23:59:00Z',
  closes_at: '2027-05-31T23:59:00Z',
  local_countries: ['CI', 'SN'],
  methods: ['online', 'transfer', 'onsite'],
  categories: [
    {
      code: 'researcher',
      label_fr: 'Chercheur',
      label_en: 'Researcher',
      description_fr: '',
      description_en: '',
      requires_proof: false,
      fees: [
        { period: 'early', zone: 'local', amount: '40000.00' },
        { period: 'regular', zone: 'local', amount: '50000.00' },
        { period: 'regular', zone: 'international', amount: '150000.00' },
      ],
    },
    {
      code: 'student',
      label_fr: 'Étudiant',
      label_en: 'Student',
      description_fr: 'Carte en cours de validité.',
      description_en: 'Valid card.',
      requires_proof: true,
      fees: [{ period: 'regular', zone: 'local', amount: '15000.00' }],
    },
  ],
  options: [
    {
      code: 'gala',
      label_fr: 'Dîner de gala',
      label_en: 'Gala dinner',
      description_fr: '',
      description_en: '',
      price_local: '10000.00',
      price_international: '15000.00',
      limited: true,
      categories: ['researcher'],
    },
  ],
};

export function myRegistration(overrides: Partial<MyRegistration> = {}): MyRegistration {
  return {
    id: 12,
    reference: 'GC27-I00012',
    edition: {
      code: 'GC27',
      title_fr: 'GEST-CONF 2027',
      title_en: 'GEST-CONF 2027',
      timezone: 'Africa/Abidjan',
    },
    category: {
      code: 'researcher',
      label_fr: 'Chercheur',
      label_en: 'Researcher',
      requires_proof: false,
    },
    period: 'regular',
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
        amount: '50000.00',
      },
    ],
    billing_name: 'Awa Koné',
    billing_organization: '',
    billing_address: '',
    due_at: '2027-02-15T00:00:00Z',
    created_at: '2027-01-16T10:00:00Z',
    confirmed_at: null,
    closed_at: null,
    refund_due: null,
    refund_percent: null,
    cancellation_deadline: null,
    can_cancel: true,
    has_qr: false,
    proof: null,
    documents: [],
    payments: [],
    ...overrides,
  };
}
