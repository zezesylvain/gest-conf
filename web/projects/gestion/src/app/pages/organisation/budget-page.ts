import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  OnInit,
  signal,
} from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import {
  Budget,
  BudgetCategory,
  BudgetKind,
  BudgetLine,
  ErrorSummary,
  LanguageService,
  MeStore,
  PageHeader,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { OrganisationApi } from '../../core/organisation-api';
import { editionCapabilities, errorMessages } from '../../core/page-support';
import { money, saveBlob } from '../../core/registrations-api';
import { confirmAction } from '../events/events-support';
import { ATTACHMENT_ACCEPT, ATTACHMENT_MAX_BYTES, BUDGET_CATEGORIES } from './organisation-support';

const KINDS: readonly BudgetKind[] = ['expense', 'income'];

/**
 * Budget prévisionnel et réalisé (plan L8, N4) : lignes par nature et par poste, réalisé
 * saisi ou **calculé** (inscriptions encaissées, partenariats reçus : lignes non
 * supprimables), écarts, solde, justificatifs privés (PDF, PNG, JPEG). Lecture
 * `budget.read`, écriture `budget.write` ; l'export (CSV ou XLSX) demande une
 * réauthentification récente.
 */
@Component({
  selector: 'gestion-budget-page',
  imports: [
    ReactiveFormsModule,
    TranslatePipe,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './budget-page.html',
  styleUrl: '../page.scss',
  styles: `
    .figures {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
      gap: 0.75rem;
      margin: 0;
    }
    .figures div {
      border: 1px solid var(--gc-border);
      border-radius: 0.5rem;
      padding: 0.75rem;
    }
    .figures dd {
      margin: 0.25rem 0 0;
      font-size: 1.2rem;
      font-weight: 600;
    }
    .amount {
      text-align: end;
      white-space: nowrap;
    }
    .negative {
      color: var(--gc-danger);
    }
  `,
})
export class BudgetPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(OrganisationApi);
  private readonly dialog = inject(MatDialog);
  private readonly meStore = inject(MeStore);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly kinds = KINDS;
  protected readonly accept = ATTACHMENT_ACCEPT;
  protected readonly budget = signal<Budget | null>(null);
  protected readonly editing = signal<BudgetLine | null>(null);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  protected readonly canWrite = computed(() =>
    editionCapabilities(this.meStore, this.editionId()).includes('budget.write'),
  );
  protected readonly linesByKind = computed(() => {
    const lines = this.budget()?.lines ?? [];
    return KINDS.map((kind) => ({ kind, lines: lines.filter((line) => line.kind === kind) }));
  });

  protected readonly form = inject(NonNullableFormBuilder).group({
    kind: ['expense' as BudgetKind],
    category: ['venue' as BudgetCategory],
    label: ['', [Validators.required, Validators.maxLength(200)]],
    planned: ['0', Validators.required],
    actual: [''],
    note: ['', Validators.maxLength(2000)],
  });
  protected readonly categories = signal<readonly BudgetCategory[]>(BUDGET_CATEGORIES.expense);

  async ngOnInit(): Promise<void> {
    this.form.controls.kind.valueChanges.subscribe((kind) => {
      const options = BUDGET_CATEGORIES[kind];
      this.categories.set(options);
      if (!options.includes(this.form.controls.category.value)) {
        this.form.controls.category.setValue(options[0]);
      }
    });
    await this.reload();
    this.loading.set(false);
  }

  private edition(): number {
    return Number(this.editionId());
  }

  protected amount(value: string | null | undefined): string {
    return money(value, this.budget()?.currency ?? 'XOF', this.language.current());
  }

  protected isNegative(value: string | null | undefined): boolean {
    return value !== null && value !== undefined && Number(value) < 0;
  }

  protected edit(line: BudgetLine): void {
    this.editing.set(line);
    this.form.reset({
      kind: line.kind,
      category: line.category,
      label: line.label,
      planned: line.planned,
      actual: line.actual ?? '',
      note: line.note,
    });
    if (line.computed) {
      this.form.controls.kind.disable();
      this.form.controls.category.disable();
      this.form.controls.actual.disable();
    }
  }

  protected cancelEdit(): void {
    this.editing.set(null);
    this.form.enable();
    this.form.reset({ kind: 'expense', category: 'venue', planned: '0' });
  }

  protected async submit(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const value = this.form.getRawValue();
    const line = this.editing();
    const body = line?.computed
      ? { label: value.label.trim(), planned: value.planned, note: value.note }
      : {
          kind: value.kind,
          category: value.category,
          label: value.label.trim(),
          planned: value.planned,
          actual: value.actual === '' ? null : value.actual,
          note: value.note,
        };
    await this.run(line ? 'gestion.budget.updated' : 'gestion.budget.created', async () => {
      const budget = line
        ? await this.api.updateLine(this.edition(), line.id, body)
        : await this.api.createLine(this.edition(), body);
      this.cancelEdit();
      return budget;
    });
  }

  protected async remove(line: BudgetLine): Promise<void> {
    const answer = await confirmAction(this.dialog, this.translate, 'gestion.budget.delete', {
      label: line.label,
    });
    if (!answer) return;
    await this.run('gestion.budget.deleted', () => this.api.deleteLine(this.edition(), line.id));
  }

  protected async uploadProof(line: BudgetLine, event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    if (file.size > ATTACHMENT_MAX_BYTES) {
      this.errors.set([this.translate.instant('gestion.tasks.detail.tooLarge')]);
      return;
    }
    await this.run('gestion.budget.proofUploaded', () =>
      this.api.uploadProof(this.edition(), line.id, file),
    );
  }

  protected async downloadProof(line: BudgetLine): Promise<void> {
    try {
      saveBlob(
        await this.api.downloadProof(this.edition(), line.id),
        line.proof?.name || 'justificatif',
      );
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
  }

  protected async removeProof(line: BudgetLine): Promise<void> {
    await this.run('gestion.budget.proofRemoved', () =>
      this.api.removeProof(this.edition(), line.id),
    );
  }

  protected async export(fileFormat: 'csv' | 'xlsx'): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    try {
      saveBlob(await this.api.exportBudget(this.edition(), fileFormat), `budget.${fileFormat}`);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }

  private async run(message: string, action: () => Promise<Budget>): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    this.status.set('');
    try {
      this.budget.set(await action());
      this.status.set(this.translate.instant(message));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error, this.form));
    } finally {
      this.busy.set(false);
    }
  }

  private async reload(): Promise<void> {
    try {
      this.budget.set(await this.api.budget(this.edition()));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
  }
}
