import { inject, Injectable } from '@angular/core';
import {
  Api,
  ReportSection,
  SectionSummary,
  manageReportsExport,
  manageReportsList,
  manageReportsRetrieve,
} from '@gestconf/shared';

/**
 * Rapports de l'édition (plan L8, N13 ; client généré) : les sections ouvertes au compte
 * (chacune revérifiée par le serveur contre sa capacité), leurs tableaux agrégés, sans
 * donnée nominative, et leurs exports CSV, XLSX ou PDF, journalisés.
 */
@Injectable({ providedIn: 'root' })
export class ReportsApi {
  private readonly api = inject(Api);

  sections(editionId: number): Promise<SectionSummary[]> {
    return this.api.invoke(manageReportsList, { edition_id: editionId });
  }

  section(editionId: number, section: string): Promise<ReportSection> {
    return this.api.invoke(manageReportsRetrieve, { edition_id: editionId, section });
  }

  exportSection(
    editionId: number,
    section: string,
    fileFormat: 'csv' | 'xlsx' | 'pdf',
  ): Promise<Blob> {
    return this.api.invoke(manageReportsExport, {
      edition_id: editionId,
      section,
      file_format: fileFormat,
    });
  }
}
