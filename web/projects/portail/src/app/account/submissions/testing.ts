import { PublicEdition, Submission } from '@gestconf/shared';

/** Édition publique de test : appel ouvert de janvier à décembre 2026 (heure UTC). */
export function testEdition(overrides: Partial<PublicEdition> = {}): PublicEdition {
  return {
    code: 'GC27',
    slug: 'gc27',
    year: 2027,
    title_fr: 'Colloque 2027',
    title_en: 'Conference 2027',
    theme_fr: '',
    theme_en: '',
    city: 'Abidjan',
    country: 'CI',
    venue: '',
    timezone: 'Africa/Abidjan',
    start_date: '2027-03-01',
    end_date: '2027-03-03',
    submission_languages: ['fr', 'en'],
    tracks: [
      {
        code: 'AI',
        name_fr: 'Intelligence artificielle',
        name_en: 'AI',
        description_fr: '',
        description_en: '',
      },
    ],
    submission_types: [
      {
        code: 'ORAL',
        label_fr: 'Communication orale',
        label_en: 'Oral paper',
        description_fr: '',
        description_en: '',
        abstract_max_words: 300,
        default_duration_min: 20,
        file_policy: 'required',
        max_file_mb: 10,
      },
    ],
    key_dates: [
      { code: 'call_open', at: '2026-01-01T00:00:00Z', at_local: '', label_fr: '', label_en: '' },
      { code: 'call_close', at: '2026-12-31T23:59:00Z', at_local: '', label_fr: '', label_en: '' },
    ],
    ...overrides,
  };
}

/** Brouillon de test (révision 3), modifiable. */
export function testSubmission(overrides: Partial<Submission> = {}): Submission {
  return {
    id: 7,
    edition: 1,
    edition_code: 'GC27',
    reference: null,
    status: 'draft',
    title: 'Réseaux de neurones',
    abstract: 'Un résumé court.',
    keywords: ['IA', 'réseaux'],
    language: 'fr',
    track: 'AI',
    submission_type: 'ORAL',
    revision: 3,
    can_edit: true,
    deadline: '2026-12-31T23:59:00Z',
    double_blind: true,
    allowed_actions: ['submit'],
    authors: [
      {
        position: 1,
        first_name: 'Awa',
        last_name: 'Koné',
        email: 'awa.kone@univ.ci',
        institution: 'Université FHB',
        country: 'CI',
        is_corresponding: true,
        is_presenter: true,
        has_account: true,
      },
    ],
    declarations: [
      { code: 'originality', accepted: true, text_version: '2026-10-v0' },
      { code: 'ethics', accepted: false, text_version: '2026-10-v0' },
    ],
    file: null,
    created_at: '2026-10-01T10:00:00Z',
    updated_at: '2026-10-01T10:00:00Z',
    submitted_at: null,
    withdrawn_at: null,
    withdraw_reason: '',
    ...overrides,
  };
}
