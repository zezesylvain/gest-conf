import { ChangeDetectionStrategy, Component, inject, input, OnInit, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import {
  ErrorSummary,
  PageHeader,
  ReportSection,
  ReportTable,
  SectionSummary,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { errorMessages } from '../../core/page-support';
import { saveBlob } from '../../core/registrations-api';
import { ReportsApi } from '../../core/reports-api';

/** Tableau prêt à afficher : colonne mise en barres (la première entièrement numérique). */
export interface ShownTable extends ReportTable {
  barColumn: number | null;
  max: number;
}

/**
 * Colonne mise en barres : la première, après les libellés, dont toutes les valeurs sont des
 * nombres positifs ; aucune si le tableau n'en a pas ou n'a qu'une ligne. Les barres
 * **doublent** le tableau (plan L8, §5) : les nombres restent lisibles dans les cellules.
 */
export function withBars(table: ReportTable): ShownTable {
  const numeric = (value: string | null) => value !== null && /^\d+(\.\d+)?$/.test(value);
  let barColumn: number | null = null;
  if (table.rows.length > 1) {
    for (let index = 1; index < table.columns.length; index++) {
      if (table.rows.every((row) => numeric(row[index]))) {
        barColumn = index;
        break;
      }
    }
  }
  const max =
    barColumn === null ? 0 : Math.max(...table.rows.map((row) => Number(row[barColumn!])), 0);
  return { ...table, barColumn, max };
}

/**
 * Rapports (plan L8, N13 ; lecture de l'édition, chaque section revérifiée par le serveur
 * contre sa capacité) : tableaux agrégés, sans nom ni adresse, barres doublées de leurs
 * nombres ; exports CSV, XLSX (une feuille par tableau) et PDF de synthèse, journalisés.
 */
@Component({
  selector: 'gestion-reports-page',
  imports: [TranslatePipe, MatButtonModule, ErrorSummary, PageHeader],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './reports-page.html',
  styleUrl: '../page.scss',
  styles: `
    .sections {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin-bottom: 1rem;
    }
    .number {
      text-align: end;
      white-space: nowrap;
    }
    .bar-cell {
      min-width: 8rem;
    }
    .bar {
      display: inline-block;
      height: 0.75rem;
      background: var(--gc-primary);
      border-radius: 0.25rem;
      vertical-align: middle;
    }
  `,
})
export class ReportsPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(ReportsApi);
  private readonly translate = inject(TranslateService);

  protected readonly sections = signal<SectionSummary[]>([]);
  protected readonly selected = signal<string | null>(null);
  protected readonly report = signal<{ label: string; tables: ShownTable[] } | null>(null);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);

  async ngOnInit(): Promise<void> {
    try {
      const sections = await this.api.sections(this.edition());
      this.sections.set(sections);
      if (sections.length) {
        await this.select(sections[0].code);
      }
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }

  private edition(): number {
    return Number(this.editionId());
  }

  protected width(table: ShownTable, row: (string | null)[]): number {
    if (table.barColumn === null || !table.max) return 0;
    return Math.round((Number(row[table.barColumn]) / table.max) * 100);
  }

  protected async select(code: string): Promise<void> {
    this.selected.set(code);
    this.busy.set(true);
    this.errors.set([]);
    try {
      const section: ReportSection = await this.api.section(this.edition(), code);
      this.report.set({ label: section.label, tables: section.tables.map(withBars) });
    } catch (error) {
      this.report.set(null);
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }

  protected async export(fileFormat: 'csv' | 'xlsx' | 'pdf'): Promise<void> {
    const code = this.selected();
    if (!code) return;
    this.busy.set(true);
    this.errors.set([]);
    try {
      saveBlob(
        await this.api.exportSection(this.edition(), code, fileFormat),
        `rapport-${code}.${fileFormat}`,
      );
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }
}
