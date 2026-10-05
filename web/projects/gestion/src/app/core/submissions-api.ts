import { inject, Injectable } from '@angular/core';
import {
  Api,
  ExtensionGrantRequest,
  manageSubmissionExtensionGrant,
  manageSubmissionExtensionRevoke,
  manageSubmissionRetrieve,
  manageSubmissionsList,
  ManageSubmissionsList$Params,
  manageSubmissionsStats,
  PaginatedSubmissionManageList,
  SubmissionManageDetail,
  SubmissionStats,
} from '@gestconf/shared';

/** Filtres de la liste et de l'export (mêmes paramètres, plan L3 §4). */
export type SubmissionFilters = Omit<ManageSubmissionsList$Params, 'edition_id'>;

/**
 * Soumissions d'une édition dans la gestion (client généré). Lecture `submissions.read`,
 * dérogations `submissions.extend`, export `submissions.export` : vérifiés par le serveur à
 * chaque appel (règle n° 2), l'interface ne fait que s'adapter.
 */
@Injectable({ providedIn: 'root' })
export class SubmissionsApi {
  private readonly api = inject(Api);

  list(editionId: number, filters: SubmissionFilters): Promise<PaginatedSubmissionManageList> {
    return this.api.invoke(manageSubmissionsList, { edition_id: editionId, ...filters });
  }

  stats(editionId: number): Promise<SubmissionStats> {
    return this.api.invoke(manageSubmissionsStats, { edition_id: editionId });
  }

  get(editionId: number, submissionId: number): Promise<SubmissionManageDetail> {
    return this.api.invoke(manageSubmissionRetrieve, {
      edition_id: editionId,
      submission_id: submissionId,
    });
  }

  grantExtension(
    editionId: number,
    submissionId: number,
    body: ExtensionGrantRequest,
  ): Promise<SubmissionManageDetail> {
    return this.api.invoke(manageSubmissionExtensionGrant, {
      edition_id: editionId,
      submission_id: submissionId,
      body,
    });
  }

  revokeExtension(
    editionId: number,
    submissionId: number,
    extensionId: number,
  ): Promise<SubmissionManageDetail> {
    return this.api.invoke(manageSubmissionExtensionRevoke, {
      edition_id: editionId,
      submission_id: submissionId,
      extension_id: extensionId,
    });
  }
}

/**
 * Adresses des téléchargements (endpoints authentifiés, règle n° 8) : de simples liens, que
 * le navigateur suit avec la session. Les filtres de l'export sont ceux de la liste.
 */
export function exportUrl(editionId: number | string, filters: SubmissionFilters): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (key === 'page' || key === 'page_size' || value === undefined || value === '') {
      continue;
    }
    for (const item of Array.isArray(value) ? value : [value]) {
      query.append(key, String(item));
    }
  }
  const suffix = query.toString();
  return `/api/v1/manage/editions/${editionId}/submissions/export${suffix ? `?${suffix}` : ''}`;
}

export function fileUrl(
  editionId: number | string,
  submissionId: number | string,
  fileId: number,
): string {
  return `/api/v1/manage/editions/${editionId}/submissions/${submissionId}/files/${fileId}/content`;
}
