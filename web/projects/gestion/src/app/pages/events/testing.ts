import type {
  Bundle,
  Certificate,
  CertificateOverview,
  CertificateSettings,
  CheckinListItem,
  CheckinResult,
  DaySession,
  DocumentTemplate,
  ManageLetterDetail,
  Signature,
} from '@gestconf/shared';

/** Liste de test : deux confirmés (dont un déjà pointé), un badge annulé, un remplacé. */
export function bundle(overrides: Partial<Bundle> = {}): Bundle {
  return {
    edition_id: 3,
    generated_at: '2027-06-01T07:00:00Z',
    expires_at: '2099-06-03T07:00:00Z',
    categories: [{ code: 'researcher', label_fr: 'Chercheur', label_en: 'Researcher' }],
    entries: [
      {
        token_hash: 'h-awa',
        reference: 'GC27-I00012',
        name: 'Awa Koné',
        category: 'researcher',
        checked_in: false,
      },
      {
        token_hash: 'h-yao',
        reference: 'GC27-I00013',
        name: 'Koffi Yao',
        category: 'researcher',
        checked_in: true,
      },
    ],
    retired: [
      { token_hash: 'h-cancelled', reference: 'GC27-I00014', reason: 'cancelled' },
      { token_hash: 'h-old', reference: 'GC27-I00012', reason: 'replaced' },
    ],
    ...overrides,
  };
}

export const PERSON = {
  id: 12,
  reference: 'GC27-I00012',
  name: 'Awa Koné',
  category: 'researcher',
  category_label_fr: 'Chercheur',
  category_label_en: 'Researcher',
  status: 'confirmed' as const,
};

export function checkinResult(overrides: Partial<CheckinResult> = {}): CheckinResult {
  return {
    outcome: 'checked_in',
    idempotency_key: 'k-00000001',
    registration: PERSON,
    checkin: null,
    ...overrides,
  };
}

export function checkinRow(overrides: Partial<CheckinListItem> = {}): CheckinListItem {
  return {
    id: 7,
    registration: PERSON,
    method: 'scan',
    scanned_at: '2027-06-01T08:00:00Z',
    received_at: '2027-06-01T08:00:01Z',
    recorded_by: 'Bénévole Un',
    device: 'entrée',
    cancelled_at: null,
    cancelled_by: '',
    cancel_reason: '',
    ...overrides,
  };
}

export function daySession(overrides: Partial<DaySession> = {}): DaySession {
  return {
    id: 21,
    title_fr: 'Session plénière',
    title_en: 'Plenary session',
    starts_at: '2027-06-01T09:00:00Z',
    ends_at: '2027-06-01T10:30:00Z',
    room: 'Amphi A',
    chairs: ['Pr Yao'],
    chaired: false,
    attendance: 4,
    slots: [
      {
        id: 31,
        submission_id: 101,
        reference: 'GC27-S0101',
        title: 'Réseaux de capteurs',
        presenters: ['Awa Koné'],
        starts_at: '2027-06-01T09:00:00Z',
        ends_at: '2027-06-01T09:20:00Z',
        status: 'scheduled',
      },
      {
        id: 32,
        submission_id: 102,
        reference: 'GC27-S0102',
        title: 'Apprentissage frugal',
        presenters: ['Koffi Yao'],
        starts_at: '2027-06-01T09:20:00Z',
        ends_at: '2027-06-01T09:40:00Z',
        status: 'presented',
      },
    ],
    ...overrides,
  };
}

export function overview(overrides: Partial<CertificateOverview> = {}): CertificateOverview {
  return {
    nature: 'participation',
    enabled: true,
    ready: true,
    problem: '',
    eligible: 40,
    issued: 0,
    revoked: 0,
    unreachable: 0,
    pending: false,
    ...overrides,
  };
}

export function certificate(overrides: Partial<Certificate> = {}): Certificate {
  return {
    id: 5,
    reference: 'GC27-A00005',
    nature: 'participation',
    name: 'Awa Koné',
    institution: 'UFHB',
    user_id: 9,
    issued_at: '2027-06-04T10:00:00Z',
    signatory_name: 'Pr Yao',
    signing_mode: 'image',
    revoked_at: null,
    revoke_reason: '',
    ...overrides,
  };
}

export function certificateSettings(
  overrides: Partial<CertificateSettings> = {},
): CertificateSettings {
  return {
    signing_mode: 'image',
    layout: 'signature_right',
    review_enabled: false,
    has_header: false,
    header_width: null,
    header_height: null,
    signing_available: true,
    signing_key: null,
    ...overrides,
  };
}

export function template(overrides: Partial<DocumentTemplate> = {}): DocumentTemplate {
  return {
    nature: 'participation',
    title_fr: 'Attestation de participation',
    title_en: 'Certificate of attendance',
    body_fr: 'Nous attestons que {name} a participé à {edition}.',
    body_en: 'This is to certify that {name} attended {edition}.',
    footer_fr: '',
    footer_en: '',
    customized: {
      title_fr: false,
      title_en: false,
      body_fr: false,
      body_en: false,
      footer_fr: false,
      footer_en: false,
    },
    placeholders: ['name', 'edition', 'dates', 'venue'],
    signatory: null,
    ...overrides,
  };
}

export function letter(overrides: Partial<ManageLetterDetail> = {}): ManageLetterDetail {
  return {
    id: 8,
    registration_id: 12,
    registration_status: 'confirmed',
    reference: 'GC27-I00012',
    person: 'Awa Koné',
    passport_name: 'KONE AWA',
    nationality: 'CI',
    passport_number: '20AB12345',
    passport_number_masked: '•••••2345',
    stay_from: '2027-05-30',
    stay_to: '2027-06-05',
    embassy: 'Ambassade de France à Abidjan',
    status: 'requested',
    requested_at: '2027-04-01T10:00:00Z',
    decided_by: '',
    issued_at: null,
    refuse_reason: '',
    revoked_at: null,
    revoke_reason: '',
    signatory_name: '',
    verification_url: '',
    ...overrides,
  };
}

export function signature(overrides: Partial<Signature> = {}): Signature {
  return {
    display_name: 'Pr Koffi Yao',
    title_fr: 'Président',
    title_en: 'Chair',
    has_image: false,
    image_width: null,
    image_height: null,
    image_uploaded_at: null,
    complete: false,
    updated_at: null,
    ...overrides,
  };
}
