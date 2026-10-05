import { SubmissionManage, SubmissionManageDetail } from '@gestconf/shared';

/** Ligne de liste de test (soumise, deux auteurs). */
export function row(overrides: Partial<SubmissionManage> = {}): SubmissionManage {
  return {
    id: 7,
    reference: 'GC27-0001',
    status: 'submitted',
    title: 'Apprentissage profond',
    track: 'ia',
    submission_type: 'oral',
    language: 'fr',
    authors_label: 'Awa Koné ; Mariam Traoré',
    authors_count: 2,
    pages: 3,
    extension_until: null,
    submitted_at: '2026-10-01T10:00:00Z',
    updated_at: '2026-10-01T10:00:00Z',
    ...overrides,
  };
}

/** Détail de test : un PDF en deux versions, un historique, aucune dérogation. */
export function detail(overrides: Partial<SubmissionManageDetail> = {}): SubmissionManageDetail {
  return {
    ...row(),
    abstract: 'Un résumé.',
    keywords: ['ia', 'santé'],
    withdrawn_at: null,
    withdraw_reason: '',
    submitter_name: 'Awa Koné',
    authors: [
      {
        position: 1,
        first_name: 'Awa',
        last_name: 'Koné',
        email: 'awa@univ.ci',
        institution: 'UFHB',
        country: 'CI',
        is_corresponding: true,
        is_presenter: true,
        has_account: true,
      },
    ],
    files: [
      {
        id: 12,
        kind: 'main',
        version: 2,
        original_name: 'article.pdf',
        size: 1000,
        pages: 3,
        metadata_removed: true,
        uploaded_at: '2026-10-02T10:00:00Z',
      },
      {
        id: 11,
        kind: 'main',
        version: 1,
        original_name: 'brouillon.pdf',
        size: 900,
        pages: 2,
        metadata_removed: true,
        uploaded_at: '2026-10-01T10:00:00Z',
      },
    ],
    declarations: [{ code: 'originality', accepted: true, text_version: '2026-10-v0' }],
    history: [
      {
        from_status: 'draft',
        to_status: 'submitted',
        at: '2026-10-01T10:00:00Z',
        reason: '',
        actor_name: 'Awa Koné',
      },
    ],
    revisions: [],
    extensions: [],
    can_extend: true,
    ...overrides,
  };
}
