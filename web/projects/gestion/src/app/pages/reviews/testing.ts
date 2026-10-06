import {
  CandidateList,
  ReviewerAssignment,
  ReviewerAssignmentDetail,
  ReviewerDiscussion,
  ReviewSubmissionDetail,
  SubmissionReviews,
} from '@gestconf/shared';

/** Affectation de test : soumission anonymisée (RG-04), grille par défaut, sans évaluation. */
export function assignmentDetail(
  overrides: Partial<ReviewerAssignmentDetail> = {},
): ReviewerAssignmentDetail {
  return {
    id: 12,
    status: 'active',
    assigned_at: '2027-04-01T10:00:00Z',
    due_at: '2027-05-01T21:59:00Z',
    pseudonym_rank: 2,
    can_edit: true,
    discussion_open: false,
    double_blind: true,
    review_status: null,
    review: null,
    submission: {
      id: 7,
      reference: 'GC27-0001',
      title: 'Réseaux de neurones',
      abstract: 'Un résumé.',
      keywords: ['IA'],
      language: 'fr',
      status: 'under_review',
      has_file: true,
      track: { code: 'ia', name_fr: 'IA', name_en: 'AI' },
      submission_type: { code: 'oral', label_fr: 'Oral', label_en: 'Oral' },
    },
    grid: {
      id: 1,
      name: 'Grille',
      version: 1,
      scale_min: 0,
      scale_max: 5,
      criteria: [
        { code: 'originalite', label_fr: 'Originalité', weight: '25.00', is_required: true },
        { code: 'methode', label_fr: 'Méthode', weight: '30.00', is_required: true },
        { code: 'pertinence', label_fr: 'Pertinence', weight: '15.00', is_required: true },
        { code: 'redaction', label_fr: 'Rédaction', weight: '15.00', is_required: true },
        { code: 'impact', label_fr: 'Impact', weight: '15.00', is_required: false },
      ],
    },
    ...overrides,
  };
}

export function assignmentRow(overrides: Partial<ReviewerAssignment> = {}): ReviewerAssignment {
  const detail = assignmentDetail();
  return {
    id: detail.id,
    status: 'active',
    assigned_at: detail.assigned_at,
    due_at: detail.due_at,
    pseudonym_rank: 2,
    can_edit: true,
    review_status: null,
    submission: {
      id: 7,
      reference: 'GC27-0001',
      title: 'Réseaux de neurones',
      language: 'fr',
      status: 'under_review',
      track: detail.submission.track,
      submission_type: detail.submission.submission_type,
    },
    ...overrides,
  };
}

export function discussion(): ReviewerDiscussion {
  return {
    opened_at: '2027-05-02T10:00:00Z',
    final_score: '71.00',
    spread: '10.00',
    reviews: [
      {
        pseudonym_rank: 1,
        mine: false,
        recommendation: 'accept',
        confidence: 4,
        comment_to_authors: 'Bien.',
        comment_to_committee: '',
        weighted_score: '76.00',
        suggested_type: null,
        scores: {},
      },
      {
        pseudonym_rank: 2,
        mine: true,
        recommendation: 'accept_minor',
        confidence: 3,
        comment_to_authors: 'À reprendre.',
        comment_to_committee: '',
        weighted_score: '66.00',
        suggested_type: null,
        scores: {},
      },
    ],
    messages: [
      { id: 1, pseudonym_rank: null, mine: false, body: 'Avis ?', at: '2027-05-02T11:00:00Z' },
      { id: 2, pseudonym_rank: 1, mine: false, body: 'Je maintiens.', at: '2027-05-02T12:00:00Z' },
    ],
  };
}

/** Soumission du pilotage : en recevabilité, un relecteur affecté sur deux requis. */
export function followUpDetail(
  overrides: Partial<ReviewSubmissionDetail> = {},
): ReviewSubmissionDetail {
  return {
    id: 7,
    reference: 'GC27-0001',
    title: 'Réseaux de neurones',
    status: 'screening',
    track: 'ia',
    submission_type: 'oral',
    language: 'fr',
    submitted_at: '2027-03-01T10:00:00Z',
    abstract: 'Un résumé.',
    keywords: ['IA'],
    assignment_count: 1,
    review_count: 0,
    late_count: 0,
    required: 2,
    decision: null,
    conflicts: [],
    assignments: [
      {
        id: 31,
        reviewer: { id: 50, name: 'Rita Relectrice' },
        assigned_by: { id: 1, name: 'Présidente' },
        assigned_at: '2027-04-01T10:00:00Z',
        due_at: '2027-05-01T21:59:00Z',
        status: 'active',
        reason: '',
        conflict_override_reason: '',
        pseudonym_rank: 1,
        reminders: [],
        review_status: null,
      },
    ],
    ...overrides,
  };
}

export function candidates(): CandidateList {
  return {
    max_load: 10,
    track: 'ia',
    candidates: [
      {
        id: 50,
        name: 'Rita Relectrice',
        institution: '',
        load: 1,
        tracks: ['ia'],
        assignment_id: 31,
        conflicts: [],
      },
      {
        id: 51,
        name: 'Paul Collègue',
        institution: 'Université de Cocody',
        load: 0,
        tracks: [],
        assignment_id: null,
        conflicts: [{ kind: 'institution', overridable: true, overridden: false }],
      },
      {
        id: 52,
        name: 'Kofi Mensah',
        institution: '',
        load: 0,
        tracks: [],
        assignment_id: null,
        conflicts: [{ kind: 'author', overridable: false, overridden: false }],
      },
    ],
  };
}

export function submissionReviews(overrides: Partial<SubmissionReviews> = {}): SubmissionReviews {
  return {
    final_score: '71.00',
    spread: '40.00',
    threshold: '30.00',
    divergent: true,
    discussion_opened_at: null,
    messages: [],
    reviews: [
      {
        id: 3,
        assignment_id: 31,
        reviewer: { id: 50, name: 'Rita Relectrice' },
        pseudonym_rank: 1,
        recommendation: 'accept',
        confidence: 4,
        comment_to_authors: 'Bien.',
        comment_to_committee: 'Confidentiel.',
        ethics_flag: false,
        plagiarism_flag: false,
        suggested_type: null,
        weighted_score: '91.00',
        submitted_at: '2027-04-20T10:00:00Z',
        version: 1,
        scores: {},
      },
    ],
    ...overrides,
  };
}
