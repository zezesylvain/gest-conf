import { inject, Injectable } from '@angular/core';
import {
  ActivityEntry,
  Api,
  Budget,
  BudgetLineWriteRequest,
  ManageTasksList$Params,
  PatchedBudgetLineWriteRequest,
  PatchedTaskWriteRequest,
  Task,
  TaskDetail,
  TaskPerson,
  TaskWriteRequest,
  manageActivity,
  manageBudgetExport,
  manageBudgetLinesCreate,
  manageBudgetLinesDestroy,
  manageBudgetLinesProofDownload,
  manageBudgetLinesProofRemove,
  manageBudgetLinesProofUpload,
  manageBudgetLinesUpdate,
  manageBudgetRetrieve,
  manageTasksArchive,
  manageTasksAttachmentsDownload,
  manageTasksAttachmentsRemove,
  manageTasksAttachmentsUpload,
  manageTasksComment,
  manageTasksCreate,
  manageTasksList,
  manageTasksMembers,
  manageTasksRestore,
  manageTasksRetrieve,
  manageTasksUpdate,
} from '@gestconf/shared';

export type TaskFilters = Omit<ManageTasksList$Params, 'edition_id'>;

/**
 * Organisation du CO dans la gestion (plan L8, N3, N4, N14 ; client généré) : tâches
 * (`tasks.read`, `tasks.write`), budget (`budget.read`, `budget.write`), fil d'activité
 * (`tasks.read`). Chaque écriture d'une tâche porte sa révision lue (`If-Match`) : une tâche
 * modifiée entre-temps renvoie 412 « stale_revision ». Tout est revérifié par le serveur
 * (règle n° 2) ; l'export du budget demande une réauthentification récente, que
 * l'intercepteur ouvre avant de rejouer la requête.
 */
@Injectable({ providedIn: 'root' })
export class OrganisationApi {
  private readonly api = inject(Api);

  // --- Tâches (N3) -------------------------------------------------------------------------

  tasks(editionId: number, filters: TaskFilters = {}): Promise<Task[]> {
    return this.api.invoke(manageTasksList, { edition_id: editionId, ...filters });
  }

  members(editionId: number): Promise<TaskPerson[]> {
    return this.api.invoke(manageTasksMembers, { edition_id: editionId });
  }

  task(editionId: number, taskId: number): Promise<TaskDetail> {
    return this.api.invoke(manageTasksRetrieve, { edition_id: editionId, task_id: taskId });
  }

  createTask(editionId: number, body: TaskWriteRequest): Promise<TaskDetail> {
    return this.api.invoke(manageTasksCreate, { edition_id: editionId, body });
  }

  updateTask(
    editionId: number,
    taskId: number,
    revision: number,
    body: PatchedTaskWriteRequest,
  ): Promise<TaskDetail> {
    return this.api.invoke(manageTasksUpdate, {
      edition_id: editionId,
      task_id: taskId,
      'If-Match': revision,
      body,
    });
  }

  archiveTask(editionId: number, taskId: number, revision: number): Promise<TaskDetail> {
    return this.api.invoke(manageTasksArchive, {
      edition_id: editionId,
      task_id: taskId,
      'If-Match': revision,
    });
  }

  restoreTask(editionId: number, taskId: number, revision: number): Promise<TaskDetail> {
    return this.api.invoke(manageTasksRestore, {
      edition_id: editionId,
      task_id: taskId,
      'If-Match': revision,
    });
  }

  comment(editionId: number, taskId: number, body: string): Promise<TaskDetail> {
    return this.api.invoke(manageTasksComment, {
      edition_id: editionId,
      task_id: taskId,
      body: { body },
    });
  }

  uploadAttachment(editionId: number, taskId: number, file: Blob): Promise<TaskDetail> {
    return this.api.invoke(manageTasksAttachmentsUpload, {
      edition_id: editionId,
      task_id: taskId,
      body: { file },
    });
  }

  downloadAttachment(editionId: number, taskId: number, attachmentId: number): Promise<Blob> {
    return this.api.invoke(manageTasksAttachmentsDownload, {
      edition_id: editionId,
      task_id: taskId,
      attachment_id: attachmentId,
    });
  }

  removeAttachment(editionId: number, taskId: number, attachmentId: number): Promise<TaskDetail> {
    return this.api.invoke(manageTasksAttachmentsRemove, {
      edition_id: editionId,
      task_id: taskId,
      attachment_id: attachmentId,
    });
  }

  // --- Budget (N4) --------------------------------------------------------------------------

  budget(editionId: number): Promise<Budget> {
    return this.api.invoke(manageBudgetRetrieve, { edition_id: editionId });
  }

  createLine(editionId: number, body: BudgetLineWriteRequest): Promise<Budget> {
    return this.api.invoke(manageBudgetLinesCreate, { edition_id: editionId, body });
  }

  updateLine(
    editionId: number,
    lineId: number,
    body: PatchedBudgetLineWriteRequest,
  ): Promise<Budget> {
    return this.api.invoke(manageBudgetLinesUpdate, {
      edition_id: editionId,
      line_id: lineId,
      body,
    });
  }

  deleteLine(editionId: number, lineId: number): Promise<Budget> {
    return this.api.invoke(manageBudgetLinesDestroy, { edition_id: editionId, line_id: lineId });
  }

  uploadProof(editionId: number, lineId: number, file: Blob): Promise<Budget> {
    return this.api.invoke(manageBudgetLinesProofUpload, {
      edition_id: editionId,
      line_id: lineId,
      body: { file },
    });
  }

  downloadProof(editionId: number, lineId: number): Promise<Blob> {
    return this.api.invoke(manageBudgetLinesProofDownload, {
      edition_id: editionId,
      line_id: lineId,
    });
  }

  removeProof(editionId: number, lineId: number): Promise<Budget> {
    return this.api.invoke(manageBudgetLinesProofRemove, {
      edition_id: editionId,
      line_id: lineId,
    });
  }

  exportBudget(editionId: number, fileFormat: 'csv' | 'xlsx'): Promise<Blob> {
    return this.api.invoke(manageBudgetExport, { edition_id: editionId, file_format: fileFormat });
  }

  // --- Fil d'activité (N14) -------------------------------------------------------------------

  activity(editionId: number): Promise<ActivityEntry[]> {
    return this.api.invoke(manageActivity, { edition_id: editionId });
  }
}
