import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import {
  Api,
  AssignmentCreateRequest,
  AssignmentManage,
  CandidateList,
  ConflictManage,
  DecisionBatchResult,
  DecisionOutcome,
  DecisionWriteRequest,
  DeclineRequest,
  Expertise,
  Grid,
  GridCreateRequest,
  manageAssignmentCancel,
  manageAssignmentCreate,
  manageAssignmentUpdate,
  manageConflictCreate,
  manageDecisionsBatch,
  manageDecisionsPublish,
  manageGridCreate,
  manageGridDelete,
  manageGridDuplicate,
  manageGridsList,
  manageGridUpdate,
  manageRanking,
  ManageRanking$Params,
  manageReviewProgress,
  manageReviewsExport,
  manageReviewSubmissionCandidates,
  manageReviewSubmissionDecision,
  manageReviewSubmissionDecisionDelete,
  manageReviewSubmissionDiscussionMessage,
  manageReviewSubmissionDiscussionOpen,
  manageReviewSubmissionPromote,
  manageReviewSubmissionRetrieve,
  manageReviewSubmissionReviews,
  manageReviewSubmissionScreening,
  manageReviewSubmissionsList,
  ManageReviewSubmissionsList$Params,
  OpenReviewAuthor,
  PaginatedReviewSubmissionList,
  PatchedGridUpdateRequest,
  PublishResult,
  Ranking,
  ReviewerAssignment,
  ReviewerAssignmentDetail,
  reviewerAssignmentAuthors,
  reviewerAssignmentDecline,
  reviewerAssignmentRetrieve,
  reviewerAssignmentsList,
  ReviewerDiscussion,
  reviewerDiscussionMessage,
  reviewerDiscussionRetrieve,
  reviewerExpertiseRetrieve,
  reviewerExpertiseUpdate,
  ReviewerReview,
  reviewerReviewSave,
  reviewerReviewSubmit,
  ReviewProgress,
  ReviewSubmissionDetail,
  ReviewWriteRequest,
  ScreeningDecision,
  SubmissionReviews,
} from '@gestconf/shared';
import { firstValueFrom } from 'rxjs';

/** Issues d'une décision (H16), dans l'ordre d'affichage. */
export const OUTCOMES: readonly DecisionOutcome[] = [
  'accepted',
  'accepted_minor',
  'waitlist',
  'rejected',
];

/** Filtres du suivi de l'évaluation (plan L4 §4). */
export type FollowUpFilters = Omit<ManageReviewSubmissionsList$Params, 'edition_id'>;
export type RankingFilters = Omit<ManageRanking$Params, 'edition_id'>;

/**
 * Évaluation et décision dans la gestion (client généré, plan L4 §4). Relecteur :
 * `reviews.write` (ses affectations seulement, RG-03, RG-04) ; président : `reviews.manage`,
 * `reviews.read_all`, `decisions.*`, `grids.write`. Le serveur vérifie chaque appel
 * (règle n° 2) ; l'interface ne fait que s'adapter.
 */
@Injectable({ providedIn: 'root' })
export class ReviewsApi {
  private readonly api = inject(Api);
  private readonly http = inject(HttpClient);

  // --- Relecteur ----------------------------------------------------------------------------

  myAssignments(editionId: number): Promise<ReviewerAssignment[]> {
    return this.api.invoke(reviewerAssignmentsList, { edition_id: editionId });
  }

  assignment(editionId: number, assignmentId: number): Promise<ReviewerAssignmentDetail> {
    return this.api.invoke(reviewerAssignmentRetrieve, {
      edition_id: editionId,
      assignment_id: assignmentId,
    });
  }

  authors(editionId: number, assignmentId: number): Promise<OpenReviewAuthor[]> {
    return this.api.invoke(reviewerAssignmentAuthors, {
      edition_id: editionId,
      assignment_id: assignmentId,
    });
  }

  saveReview(
    editionId: number,
    assignmentId: number,
    body: ReviewWriteRequest,
  ): Promise<ReviewerReview> {
    return this.api.invoke(reviewerReviewSave, {
      edition_id: editionId,
      assignment_id: assignmentId,
      body,
    });
  }

  submitReview(
    editionId: number,
    assignmentId: number,
    body: ReviewWriteRequest,
  ): Promise<ReviewerReview> {
    return this.api.invoke(reviewerReviewSubmit, {
      edition_id: editionId,
      assignment_id: assignmentId,
      body,
    });
  }

  decline(editionId: number, assignmentId: number, body: DeclineRequest): Promise<void> {
    return this.api.invoke(reviewerAssignmentDecline, {
      edition_id: editionId,
      assignment_id: assignmentId,
      body,
    });
  }

  discussion(editionId: number, assignmentId: number): Promise<ReviewerDiscussion> {
    return this.api.invoke(reviewerDiscussionRetrieve, {
      edition_id: editionId,
      assignment_id: assignmentId,
    });
  }

  postReviewerMessage(
    editionId: number,
    assignmentId: number,
    body: string,
  ): Promise<ReviewerDiscussion> {
    return this.api.invoke(reviewerDiscussionMessage, {
      edition_id: editionId,
      assignment_id: assignmentId,
      body: { body },
    });
  }

  expertise(editionId: number): Promise<Expertise> {
    return this.api.invoke(reviewerExpertiseRetrieve, { edition_id: editionId });
  }

  updateExpertise(editionId: number, tracks: string[]): Promise<Expertise> {
    return this.api.invoke(reviewerExpertiseUpdate, {
      edition_id: editionId,
      body: { tracks },
    });
  }

  // --- Président : suivi, recevabilité, affectations ------------------------------------

  followUp(editionId: number, filters: FollowUpFilters): Promise<PaginatedReviewSubmissionList> {
    return this.api.invoke(manageReviewSubmissionsList, { edition_id: editionId, ...filters });
  }

  progress(editionId: number): Promise<ReviewProgress> {
    return this.api.invoke(manageReviewProgress, { edition_id: editionId });
  }

  submission(editionId: number, submissionId: number): Promise<ReviewSubmissionDetail> {
    return this.api.invoke(manageReviewSubmissionRetrieve, {
      edition_id: editionId,
      submission_id: submissionId,
    });
  }

  candidates(editionId: number, submissionId: number): Promise<CandidateList> {
    return this.api.invoke(manageReviewSubmissionCandidates, {
      edition_id: editionId,
      submission_id: submissionId,
    });
  }

  screen(
    editionId: number,
    submissionId: number,
    decision: ScreeningDecision,
    reason: string,
  ): Promise<ReviewSubmissionDetail> {
    return this.api.invoke(manageReviewSubmissionScreening, {
      edition_id: editionId,
      submission_id: submissionId,
      body: { decision, reason },
    });
  }

  assign(editionId: number, body: AssignmentCreateRequest): Promise<AssignmentManage> {
    return this.api.invoke(manageAssignmentCreate, { edition_id: editionId, body });
  }

  changeDueDate(
    editionId: number,
    assignmentId: number,
    dueLocal: string,
  ): Promise<AssignmentManage> {
    return this.api.invoke(manageAssignmentUpdate, {
      edition_id: editionId,
      assignment_id: assignmentId,
      body: { due_local: dueLocal },
    });
  }

  cancelAssignment(
    editionId: number,
    assignmentId: number,
    reason: string,
  ): Promise<AssignmentManage> {
    return this.api.invoke(manageAssignmentCancel, {
      edition_id: editionId,
      assignment_id: assignmentId,
      body: { reason },
    });
  }

  declareConflict(
    editionId: number,
    submission: number,
    reviewer: number,
    reason: string,
  ): Promise<ConflictManage> {
    return this.api.invoke(manageConflictCreate, {
      edition_id: editionId,
      body: { submission, reviewer, reason },
    });
  }

  // --- Président : évaluations, discussion, décisions -----------------------------------

  reviews(editionId: number, submissionId: number): Promise<SubmissionReviews> {
    return this.api.invoke(manageReviewSubmissionReviews, {
      edition_id: editionId,
      submission_id: submissionId,
    });
  }

  openDiscussion(editionId: number, submissionId: number): Promise<SubmissionReviews> {
    return this.api.invoke(manageReviewSubmissionDiscussionOpen, {
      edition_id: editionId,
      submission_id: submissionId,
    });
  }

  postChairMessage(
    editionId: number,
    submissionId: number,
    body: string,
  ): Promise<SubmissionReviews> {
    return this.api.invoke(manageReviewSubmissionDiscussionMessage, {
      edition_id: editionId,
      submission_id: submissionId,
      body: { body },
    });
  }

  decide(
    editionId: number,
    submissionId: number,
    body: DecisionWriteRequest,
  ): Promise<ReviewSubmissionDetail> {
    return this.api.invoke(manageReviewSubmissionDecision, {
      edition_id: editionId,
      submission_id: submissionId,
      body,
    });
  }

  cancelDecision(editionId: number, submissionId: number): Promise<ReviewSubmissionDetail> {
    return this.api.invoke(manageReviewSubmissionDecisionDelete, {
      edition_id: editionId,
      submission_id: submissionId,
    });
  }

  promote(editionId: number, submissionId: number): Promise<ReviewSubmissionDetail> {
    return this.api.invoke(manageReviewSubmissionPromote, {
      edition_id: editionId,
      submission_id: submissionId,
    });
  }

  decideBatch(
    editionId: number,
    items: (DecisionWriteRequest & { submission: number })[],
  ): Promise<DecisionBatchResult> {
    return this.api.invoke(manageDecisionsBatch, { edition_id: editionId, body: { items } });
  }

  publish(editionId: number): Promise<PublishResult> {
    return this.api.invoke(manageDecisionsPublish, { edition_id: editionId });
  }

  ranking(editionId: number, filters: RankingFilters): Promise<Ranking> {
    return this.api.invoke(manageRanking, { edition_id: editionId, ...filters });
  }

  /**
   * Export CSV nominatif (réauthentification récente, journalisé) : lu en texte par
   * `HttpClient`, pour que l'intercepteur ouvre la fenêtre de réauthentification puis
   * rejoue la requête ; un simple lien rendrait l'erreur JSON au navigateur.
   */
  exportCsv(editionId: number): Promise<string> {
    const path = manageReviewsExport.PATH.replace('{edition_id}', String(editionId));
    return firstValueFrom(this.http.get(`${this.api.rootUrl}${path}`, { responseType: 'text' }));
  }

  // --- Grilles (RG-05) ----------------------------------------------------------------------

  grids(editionId: number): Promise<Grid[]> {
    return this.api.invoke(manageGridsList, { edition_id: editionId });
  }

  createGrid(editionId: number, body: GridCreateRequest): Promise<Grid> {
    return this.api.invoke(manageGridCreate, { edition_id: editionId, body });
  }

  updateGrid(editionId: number, gridId: number, body: PatchedGridUpdateRequest): Promise<Grid> {
    return this.api.invoke(manageGridUpdate, { edition_id: editionId, grid_id: gridId, body });
  }

  duplicateGrid(editionId: number, gridId: number): Promise<Grid> {
    return this.api.invoke(manageGridDuplicate, { edition_id: editionId, grid_id: gridId });
  }

  deleteGrid(editionId: number, gridId: number): Promise<void> {
    return this.api.invoke(manageGridDelete, { edition_id: editionId, grid_id: gridId });
  }
}

/** PDF de l'affectation, servi au relecteur (règle n° 8 ; nom générique, RG-04). */
export function reviewerFileUrl(editionId: number | string, assignmentId: number): string {
  return `/api/v1/manage/editions/${editionId}/reviews/assignments/${assignmentId}/file`;
}

/** Enregistre un texte comme fichier (export CSV), sans quitter la page. */
export function saveText(content: string, name: string, type = 'text/csv;charset=utf-8'): void {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}
