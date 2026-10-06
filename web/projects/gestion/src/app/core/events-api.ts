import { inject, Injectable } from '@angular/core';
import {
  Api,
  BadgeBatches,
  Bundle,
  Certificate,
  CertificateNature,
  CertificateOverview,
  CertificateSettings,
  Checkin,
  CheckinResult,
  CheckinSummary,
  CounterRequestRequest,
  CounterResponse,
  DaySession,
  DocumentNature,
  DocumentTemplate,
  ManageCertificatesList$Params,
  ManageCheckinList$Params,
  ManageLetterDetail,
  ManageLettersList$Params,
  PaginatedCertificateList,
  PaginatedCheckinListItemList,
  PaginatedManageLetterList,
  PatchedCertificateSettingsRequest,
  PatchedDocumentTemplateUpdateRequest,
  PatchedSignatureRequest,
  Signatory,
  Signature,
  SyncItemRequest,
  SyncResponse,
  manageBadgeRegenerate,
  manageBadgesBatches,
  manageCertificateHeaderDelete,
  manageCertificateHeaderUpload,
  manageCertificateRevoke,
  manageCertificateSettingsRetrieve,
  manageCertificateSettingsUpdate,
  manageCertificateSignatories,
  manageCertificateSigningKeyDelete,
  manageCertificateSigningKeyUpload,
  manageCertificateTemplateUpdate,
  manageCertificateTemplates,
  manageCertificatesIssue,
  manageCertificatesList,
  manageCertificatesOverview,
  manageCheckinBundle,
  manageCheckinCancel,
  manageCheckinExport,
  manageCheckinList,
  manageCheckinManual,
  manageCheckinScan,
  manageCheckinSummary,
  manageCheckinSync,
  manageDayAttendance,
  manageDayAttendanceExport,
  manageDayAttendanceScan,
  manageDayPresented,
  manageDaySessions,
  manageDayUnpresented,
  manageLetterIssue,
  manageLetterRefuse,
  manageLetterRetrieve,
  manageLetterRevoke,
  manageLettersList,
  manageRegistrationsCounter,
  manageSignatureImageUpload,
  manageSignatureRetrieve,
  manageSignatureUpdate,
} from '@gestconf/shared';

export type CheckinFilters = Omit<ManageCheckinList$Params, 'edition_id'>;
export type CertificateFilters = Omit<ManageCertificatesList$Params, 'edition_id'>;
export type LetterFilters = Omit<ManageLettersList$Params, 'edition_id'>;

/** Pointage d'un badge lu ou d'une référence saisie (accueil ou entrée de session). */
export interface CheckinAttempt {
  idempotency_key: string;
  device: string;
  token?: string;
  reference?: string;
}

/**
 * Jour J, attestations, lettres et signature dans la gestion (plan L7, K15 ; client généré).
 * Pointage `checkin.scan`, suivi des présences `checkin.manage`, badges
 * `registrations.read`, comptoir `registrations.manage`, attestations `certificates.manage`,
 * lettres `letters.manage`, signature `signature.manage` (le signataire seul, K18) ; le
 * président de séance émarge **ses** sessions. Tout est revérifié par le serveur (règle
 * n° 2) ; les écritures sensibles demandent une réauthentification récente, que
 * l'intercepteur ouvre avant de rejouer la requête.
 */
@Injectable({ providedIn: 'root' })
export class EventsApi {
  private readonly api = inject(Api);

  // --- Accueil (K4, K5) ---------------------------------------------------------------------

  bundle(editionId: number): Promise<Bundle> {
    return this.api.invoke(manageCheckinBundle, { edition_id: editionId });
  }

  scan(editionId: number, attempt: CheckinAttempt): Promise<CheckinResult> {
    return this.api.invoke(manageCheckinScan, {
      edition_id: editionId,
      body: {
        token: attempt.token ?? '',
        device: attempt.device,
        idempotency_key: attempt.idempotency_key,
      },
    });
  }

  manual(editionId: number, attempt: CheckinAttempt): Promise<CheckinResult> {
    return this.api.invoke(manageCheckinManual, {
      edition_id: editionId,
      body: {
        reference: attempt.reference ?? '',
        device: attempt.device,
        idempotency_key: attempt.idempotency_key,
      },
    });
  }

  sync(editionId: number, device: string, items: SyncItemRequest[]): Promise<SyncResponse> {
    return this.api.invoke(manageCheckinSync, { edition_id: editionId, body: { device, items } });
  }

  summary(editionId: number): Promise<CheckinSummary> {
    return this.api.invoke(manageCheckinSummary, { edition_id: editionId });
  }

  checkins(editionId: number, filters: CheckinFilters): Promise<PaginatedCheckinListItemList> {
    return this.api.invoke(manageCheckinList, { edition_id: editionId, ...filters });
  }

  cancelCheckin(editionId: number, checkinId: number, reason: string): Promise<Checkin> {
    return this.api.invoke(manageCheckinCancel, {
      edition_id: editionId,
      checkin_id: checkinId,
      body: { reason },
    });
  }

  exportCheckins(editionId: number): Promise<Blob> {
    return this.api.invoke(manageCheckinExport, { edition_id: editionId });
  }

  // --- Sessions du jour (K7, K8) ----------------------------------------------------------------

  daySessions(editionId: number): Promise<DaySession[]> {
    return this.api.invoke(manageDaySessions, { edition_id: editionId });
  }

  attendance(
    editionId: number,
    sessionId: number,
    filters: { q?: string; page?: number; page_size?: number } = {},
  ): Promise<PaginatedCheckinListItemList> {
    return this.api.invoke(manageDayAttendance, {
      edition_id: editionId,
      session_id: sessionId,
      ...filters,
    });
  }

  sessionScan(
    editionId: number,
    sessionId: number,
    attempt: CheckinAttempt,
  ): Promise<CheckinResult> {
    return this.api.invoke(manageDayAttendanceScan, {
      edition_id: editionId,
      session_id: sessionId,
      body: {
        token: attempt.token ?? '',
        device: attempt.device,
        idempotency_key: attempt.idempotency_key,
      },
    });
  }

  exportAttendance(editionId: number, sessionId: number): Promise<Blob> {
    return this.api.invoke(manageDayAttendanceExport, {
      edition_id: editionId,
      session_id: sessionId,
    });
  }

  markPresented(editionId: number, sessionId: number, slotId: number): Promise<DaySession> {
    return this.api.invoke(manageDayPresented, {
      edition_id: editionId,
      session_id: sessionId,
      slot_id: slotId,
    });
  }

  unmarkPresented(
    editionId: number,
    sessionId: number,
    slotId: number,
    reason: string,
  ): Promise<DaySession> {
    return this.api.invoke(manageDayUnpresented, {
      edition_id: editionId,
      session_id: sessionId,
      slot_id: slotId,
      body: { reason },
    });
  }

  // --- Badges et comptoir (K2, K3, K13) ---------------------------------------------------------

  badgeBatches(editionId: number, category?: string): Promise<BadgeBatches> {
    return this.api.invoke(manageBadgesBatches, { edition_id: editionId, category });
  }

  regenerateBadge(editionId: number, registrationId: number, reason: string): Promise<void> {
    return this.api.invoke(manageBadgeRegenerate, {
      edition_id: editionId,
      registration_id: registrationId,
      body: { reason },
    });
  }

  counter(editionId: number, body: CounterRequestRequest): Promise<CounterResponse> {
    return this.api.invoke(manageRegistrationsCounter, { edition_id: editionId, body });
  }

  // --- Attestations (K9 à K11, K19) ---------------------------------------------------------------

  certificateSettings(editionId: number): Promise<CertificateSettings> {
    return this.api.invoke(manageCertificateSettingsRetrieve, { edition_id: editionId });
  }

  updateCertificateSettings(
    editionId: number,
    body: PatchedCertificateSettingsRequest,
  ): Promise<CertificateSettings> {
    return this.api.invoke(manageCertificateSettingsUpdate, { edition_id: editionId, body });
  }

  uploadHeader(editionId: number, file: Blob): Promise<CertificateSettings> {
    return this.api.invoke(manageCertificateHeaderUpload, {
      edition_id: editionId,
      body: { file },
    });
  }

  deleteHeader(editionId: number): Promise<CertificateSettings> {
    return this.api.invoke(manageCertificateHeaderDelete, { edition_id: editionId });
  }

  uploadSigningKey(editionId: number, file: Blob, password: string): Promise<CertificateSettings> {
    return this.api.invoke(manageCertificateSigningKeyUpload, {
      edition_id: editionId,
      body: { file, password },
    });
  }

  deleteSigningKey(editionId: number): Promise<CertificateSettings> {
    return this.api.invoke(manageCertificateSigningKeyDelete, { edition_id: editionId });
  }

  templates(editionId: number): Promise<DocumentTemplate[]> {
    return this.api.invoke(manageCertificateTemplates, { edition_id: editionId });
  }

  updateTemplate(
    editionId: number,
    nature: DocumentNature,
    body: PatchedDocumentTemplateUpdateRequest,
  ): Promise<DocumentTemplate> {
    return this.api.invoke(manageCertificateTemplateUpdate, {
      edition_id: editionId,
      nature,
      body,
    });
  }

  signatories(editionId: number): Promise<Signatory[]> {
    return this.api.invoke(manageCertificateSignatories, { edition_id: editionId });
  }

  overview(editionId: number): Promise<CertificateOverview[]> {
    return this.api.invoke(manageCertificatesOverview, { edition_id: editionId });
  }

  issue(editionId: number, nature: CertificateNature): Promise<{ job_id: number }> {
    return this.api.invoke(manageCertificatesIssue, { edition_id: editionId, body: { nature } });
  }

  certificates(editionId: number, filters: CertificateFilters): Promise<PaginatedCertificateList> {
    return this.api.invoke(manageCertificatesList, { edition_id: editionId, ...filters });
  }

  revokeCertificate(
    editionId: number,
    certificateId: number,
    reason: string,
  ): Promise<Certificate> {
    return this.api.invoke(manageCertificateRevoke, {
      edition_id: editionId,
      certificate_id: certificateId,
      body: { reason },
    });
  }

  // --- Lettres d'invitation (K12) -------------------------------------------------------------------

  letters(editionId: number, filters: LetterFilters): Promise<PaginatedManageLetterList> {
    return this.api.invoke(manageLettersList, { edition_id: editionId, ...filters });
  }

  letter(editionId: number, letterId: number): Promise<ManageLetterDetail> {
    return this.api.invoke(manageLetterRetrieve, { edition_id: editionId, letter_id: letterId });
  }

  issueLetter(editionId: number, letterId: number): Promise<ManageLetterDetail> {
    return this.api.invoke(manageLetterIssue, { edition_id: editionId, letter_id: letterId });
  }

  refuseLetter(editionId: number, letterId: number, reason: string): Promise<ManageLetterDetail> {
    return this.api.invoke(manageLetterRefuse, {
      edition_id: editionId,
      letter_id: letterId,
      body: { reason },
    });
  }

  revokeLetter(editionId: number, letterId: number, reason: string): Promise<ManageLetterDetail> {
    return this.api.invoke(manageLetterRevoke, {
      edition_id: editionId,
      letter_id: letterId,
      body: { reason },
    });
  }

  // --- Signature du signataire (K18) ----------------------------------------------------------------

  signature(editionId: number): Promise<Signature> {
    return this.api.invoke(manageSignatureRetrieve, { edition_id: editionId });
  }

  updateSignature(editionId: number, body: PatchedSignatureRequest): Promise<Signature> {
    return this.api.invoke(manageSignatureUpdate, { edition_id: editionId, body });
  }

  uploadSignatureImage(editionId: number, file: Blob): Promise<Signature> {
    return this.api.invoke(manageSignatureImageUpload, { edition_id: editionId, body: { file } });
  }
}

/**
 * Adresses des fichiers servis par des endpoints authentifiés (règle n° 8), ouverts par un
 * lien ou une image : même origine, le cookie de session suffit. Les badges ne sont pas
 * stockés (K3) ; le paramètre `v` fait recharger une image remplacée.
 */
const MANAGE = '/api/v1/manage/editions';

export const eventsUrls = {
  badgeSheets(editionId: number | string, batch: number, category?: string): string {
    const query = new URLSearchParams({ batch: String(batch) });
    if (category) query.set('category', category);
    return `${MANAGE}/${editionId}/registrations/badges?${query}`;
  },
  badge(editionId: number | string, registrationId: number): string {
    return `${MANAGE}/${editionId}/registrations/${registrationId}/badge`;
  },
  certificatePdf(editionId: number | string, certificateId: number): string {
    return `${MANAGE}/${editionId}/certificates/${certificateId}/pdf`;
  },
  preview(editionId: number | string, nature: DocumentNature): string {
    return `${MANAGE}/${editionId}/certificates/templates/${nature}/preview`;
  },
  header(editionId: number | string, version: string | number | null): string {
    return `${MANAGE}/${editionId}/certificates/settings/header?v=${encodeURIComponent(version ?? '')}`;
  },
  letterPdf(editionId: number | string, letterId: number): string {
    return `${MANAGE}/${editionId}/invitation-letters/${letterId}/pdf`;
  },
  signatureImage(editionId: number | string, version: string | null): string {
    return `${MANAGE}/${editionId}/signature/image?v=${encodeURIComponent(version ?? '')}`;
  },
};
