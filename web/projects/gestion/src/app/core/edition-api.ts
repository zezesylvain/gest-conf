import { inject, Injectable } from '@angular/core';
import {
  Api,
  Confidentiality,
  Edition,
  EditionStatus,
  EditionSummary,
  InvitationBatch,
  InvitationCreateRequest,
  InvitationWithEmail,
  KeyDate,
  KeyDateWriteRequest,
  manageAuditList,
  ManageAuditList$Params,
  manageConfidentialityRetrieve,
  manageConfidentialityUpdate,
  manageEditionRetrieve,
  manageEditionsKeyDatesCreate,
  manageEditionsKeyDatesDestroy,
  manageEditionsKeyDatesList,
  manageEditionsKeyDatesPartialUpdate,
  manageEditionsList,
  manageEditionsSubmissionTypesCreate,
  manageEditionsSubmissionTypesDestroy,
  manageEditionsSubmissionTypesList,
  manageEditionsSubmissionTypesPartialUpdate,
  manageEditionsTracksCreate,
  manageEditionsTracksDestroy,
  manageEditionsTracksList,
  manageEditionsTracksPartialUpdate,
  manageEditionStatus,
  manageEditionUpdate,
  manageInvitationCancel,
  manageInvitationResend,
  manageInvitationsCreate,
  manageInvitationsList,
  ManageInvitationsList$Params,
  manageMemberRevoke,
  manageMembersList,
  MemberWithEmail,
  PaginatedAuditEntryList,
  PaginatedInvitationWithEmailList,
  PatchedConfidentialityRequest,
  PatchedEditionRequest,
  PatchedKeyDateWriteRequest,
  PatchedSubmissionTypeRequest,
  PatchedTrackRequest,
  SubmissionType,
  SubmissionTypeRequest,
  Track,
  TrackRequest,
} from '@gestconf/shared';

/**
 * Données d'une édition (client généré, plan L1 §10.1 : jamais `HttpClient` directement).
 * Les droits sont vérifiés par le serveur à chaque appel (règle n° 2).
 */
@Injectable({ providedIn: 'root' })
export class EditionApi {
  private readonly api = inject(Api);

  editions(): Promise<EditionSummary[]> {
    return this.api.invoke(manageEditionsList);
  }

  edition(id: number): Promise<Edition> {
    return this.api.invoke(manageEditionRetrieve, { edition_id: id });
  }

  updateEdition(id: number, body: PatchedEditionRequest): Promise<Edition> {
    return this.api.invoke(manageEditionUpdate, { edition_id: id, body });
  }

  changeStatus(id: number, status: EditionStatus, reason = ''): Promise<Edition> {
    return this.api.invoke(manageEditionStatus, { edition_id: id, body: { status, reason } });
  }

  confidentiality(id: number): Promise<Confidentiality> {
    return this.api.invoke(manageConfidentialityRetrieve, { edition_id: id });
  }

  updateConfidentiality(id: number, body: PatchedConfidentialityRequest): Promise<Confidentiality> {
    return this.api.invoke(manageConfidentialityUpdate, { edition_id: id, body });
  }

  tracks(id: number): Promise<Track[]> {
    return this.api.invoke(manageEditionsTracksList, { edition_id: id });
  }

  createTrack(id: number, body: TrackRequest): Promise<Track> {
    return this.api.invoke(manageEditionsTracksCreate, { edition_id: id, body });
  }

  updateTrack(id: number, itemId: number, body: PatchedTrackRequest): Promise<Track> {
    return this.api.invoke(manageEditionsTracksPartialUpdate, {
      edition_id: id,
      item_id: itemId,
      body,
    });
  }

  deleteTrack(id: number, itemId: number): Promise<void> {
    return this.api.invoke(manageEditionsTracksDestroy, { edition_id: id, item_id: itemId });
  }

  submissionTypes(id: number): Promise<SubmissionType[]> {
    return this.api.invoke(manageEditionsSubmissionTypesList, { edition_id: id });
  }

  createSubmissionType(id: number, body: SubmissionTypeRequest): Promise<SubmissionType> {
    return this.api.invoke(manageEditionsSubmissionTypesCreate, { edition_id: id, body });
  }

  updateSubmissionType(
    id: number,
    itemId: number,
    body: PatchedSubmissionTypeRequest,
  ): Promise<SubmissionType> {
    return this.api.invoke(manageEditionsSubmissionTypesPartialUpdate, {
      edition_id: id,
      item_id: itemId,
      body,
    });
  }

  deleteSubmissionType(id: number, itemId: number): Promise<void> {
    return this.api.invoke(manageEditionsSubmissionTypesDestroy, {
      edition_id: id,
      item_id: itemId,
    });
  }

  keyDates(id: number): Promise<KeyDate[]> {
    return this.api.invoke(manageEditionsKeyDatesList, { edition_id: id });
  }

  createKeyDate(id: number, body: KeyDateWriteRequest): Promise<KeyDate> {
    return this.api.invoke(manageEditionsKeyDatesCreate, { edition_id: id, body });
  }

  updateKeyDate(id: number, itemId: number, body: PatchedKeyDateWriteRequest): Promise<KeyDate> {
    return this.api.invoke(manageEditionsKeyDatesPartialUpdate, {
      edition_id: id,
      item_id: itemId,
      body,
    });
  }

  deleteKeyDate(id: number, itemId: number): Promise<void> {
    return this.api.invoke(manageEditionsKeyDatesDestroy, { edition_id: id, item_id: itemId });
  }

  members(id: number): Promise<MemberWithEmail[]> {
    return this.api.invoke(manageMembersList, { edition_id: id });
  }

  revokeMember(id: number, roleId: number, reason: string): Promise<MemberWithEmail> {
    return this.api.invoke(manageMemberRevoke, {
      edition_id: id,
      role_id: roleId,
      body: { reason },
    });
  }

  invitations(params: ManageInvitationsList$Params): Promise<PaginatedInvitationWithEmailList> {
    return this.api.invoke(manageInvitationsList, params);
  }

  invite(id: number, body: InvitationCreateRequest): Promise<InvitationBatch> {
    return this.api.invoke(manageInvitationsCreate, { edition_id: id, body });
  }

  resendInvitation(id: number, invitationId: number): Promise<InvitationWithEmail> {
    return this.api.invoke(manageInvitationResend, {
      edition_id: id,
      invitation_id: invitationId,
    });
  }

  cancelInvitation(id: number, invitationId: number): Promise<InvitationWithEmail> {
    return this.api.invoke(manageInvitationCancel, {
      edition_id: id,
      invitation_id: invitationId,
    });
  }

  audit(params: ManageAuditList$Params): Promise<PaginatedAuditEntryList> {
    return this.api.invoke(manageAuditList, params);
  }
}
