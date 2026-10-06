import { inject, Injectable } from '@angular/core';
import {
  Api,
  AuthorWriteRequest,
  PatchedSubmissionWriteRequest,
  PublicEdition,
  publicCurrentEdition,
  Submission,
  SubmissionCheck,
  submissionsAuthors,
  submissionsCheck,
  submissionsConfirmPresentation,
  submissionsCreate,
  submissionsDelete,
  submissionsFileRemove,
  submissionsFinalVersion,
  submissionsFileUpload,
  submissionsList,
  submissionsRetrieve,
  submissionsSubmit,
  submissionsTimeline,
  submissionsUpdate,
  submissionsWithdraw,
  Timeline,
} from '@gestconf/shared';

/**
 * Espace auteur (plan L3 §4, §5), par le client généré. Le serveur décide de tout : droits,
 * complétude (RG-01), fenêtre d'écriture (RG-02) ; `revision` part en If-Match pour ne jamais
 * écraser une écriture faite ailleurs (412 « stale_revision »).
 */
@Injectable({ providedIn: 'root' })
export class SubmissionsService {
  private readonly api = inject(Api);

  currentEdition(): Promise<PublicEdition> {
    return this.api.invoke(publicCurrentEdition);
  }

  list(): Promise<Submission[]> {
    return this.api.invoke(submissionsList, {});
  }

  create(editionCode: string): Promise<Submission> {
    return this.api.invoke(submissionsCreate, { body: { edition: editionCode } });
  }

  get(id: number): Promise<Submission> {
    return this.api.invoke(submissionsRetrieve, { submission_id: id });
  }

  update(submission: Submission, body: PatchedSubmissionWriteRequest): Promise<Submission> {
    return this.api.invoke(submissionsUpdate, {
      submission_id: submission.id,
      'If-Match': submission.revision,
      body,
    });
  }

  setAuthors(submission: Submission, authors: AuthorWriteRequest[]): Promise<Submission> {
    return this.api.invoke(submissionsAuthors, {
      submission_id: submission.id,
      'If-Match': submission.revision,
      body: { authors },
    });
  }

  upload(submission: Submission, file: File): Promise<Submission> {
    return this.api.invoke(submissionsFileUpload, {
      submission_id: submission.id,
      'If-Match': submission.revision,
      body: { file },
    });
  }

  removeFile(submission: Submission): Promise<Submission> {
    return this.api.invoke(submissionsFileRemove, {
      submission_id: submission.id,
      'If-Match': submission.revision,
    });
  }

  check(id: number): Promise<SubmissionCheck> {
    return this.api.invoke(submissionsCheck, { submission_id: id });
  }

  submit(id: number): Promise<Submission> {
    return this.api.invoke(submissionsSubmit, { submission_id: id });
  }

  withdraw(id: number, reason: string): Promise<Submission> {
    return this.api.invoke(submissionsWithdraw, { submission_id: id, body: { reason } });
  }

  remove(id: number): Promise<void> {
    return this.api.invoke(submissionsDelete, { submission_id: id });
  }

  timeline(id: number): Promise<Timeline> {
    return this.api.invoke(submissionsTimeline, { submission_id: id });
  }

  /** Fichier courant (endpoint authentifié, règle n° 8). */
  fileUrl(id: number): string {
    return `/api/v1/submissions/${id}/file/content`;
  }

  /** Version finale (H18) : PDF nominatif et lettre de réponse ; remplace le dépôt précédent. */
  finalVersion(id: number, file: File, responseLetter: string): Promise<Submission> {
    return this.api.invoke(submissionsFinalVersion, {
      submission_id: id,
      body: { file, response_letter: responseLetter },
    });
  }

  /** I5 (plan L5) : présentateurs désignés (positions des auteurs) et venue confirmée. */
  confirmPresentation(id: number, presenters: number[]): Promise<Submission> {
    return this.api.invoke(submissionsConfirmPresentation, {
      submission_id: id,
      body: { presenters },
    });
  }

  /** Version finale courante (endpoint authentifié, règle n° 8). */
  finalVersionUrl(id: number): string {
    return `/api/v1/submissions/${id}/final-version/content`;
  }
}

/** Mots du résumé, comme le serveur (apostrophes et traits d'union internes compris). */
export function wordCount(text: string): number {
  return (text.match(/[\p{L}\p{N}_]+(?:['’-][\p{L}\p{N}_]+)*/gu) ?? []).length;
}

/** Appel ouvert d'après les dates clés publiques (le serveur revérifie, RG-02). */
export function callIsOpen(edition: PublicEdition, now = Date.now()): boolean {
  const at = (code: string) => edition.key_dates.find((d) => d.code === code)?.at;
  const opens = at('call_open');
  const closes = at('call_close');
  return !!opens && !!closes && Date.parse(opens) <= now && now < Date.parse(closes);
}
