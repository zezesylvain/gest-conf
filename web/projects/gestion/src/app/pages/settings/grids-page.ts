import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  OnInit,
  signal,
} from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import {
  FormArray,
  FormControl,
  FormGroup,
  NonNullableFormBuilder,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import {
  ConfirmDialog,
  ConfirmDialogData,
  ConfirmDialogResult,
  CriterionWriteRequest,
  ErrorSummary,
  Grid,
  MeStore,
  PageHeader,
  SubmissionType,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { firstValueFrom, map, startWith } from 'rxjs';

import { EditionApi } from '../../core/edition-api';
import { editionCapabilities, errorMessages } from '../../core/page-support';
import { ReviewsApi } from '../../core/reviews-api';

type CriterionForm = FormGroup<{
  code: FormControl<string>;
  label_fr: FormControl<string>;
  label_en: FormControl<string>;
  weight: FormControl<string>;
  is_required: FormControl<boolean>;
}>;

/**
 * Grilles d'évaluation (RG-05 ; plan L4, H3) : par édition, et facultativement par type de
 * communication. Critères bilingues pondérés dont la somme vaut **exactement** 100 (affichée
 * pendant la saisie, revérifiée par le serveur). Une grille utilisée par une évaluation est
 * verrouillée : on la duplique en nouvelle version.
 */
@Component({
  selector: 'gestion-grids-page',
  imports: [
    ReactiveFormsModule,
    TranslatePipe,
    MatButtonModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './grids-page.html',
  styleUrl: '../page.scss',
  styles: `
    .criterion {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
      gap: 0 0.75rem;
      align-items: center;
      border-bottom: 1px solid var(--gc-border);
      padding-top: 0.5rem;
    }
  `,
})
export class GridsPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(ReviewsApi);
  private readonly editions = inject(EditionApi);
  private readonly meStore = inject(MeStore);
  private readonly dialog = inject(MatDialog);
  private readonly translate = inject(TranslateService);
  private readonly fb = inject(NonNullableFormBuilder);

  protected readonly grids = signal<Grid[]>([]);
  protected readonly types = signal<SubmissionType[]>([]);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  /** Grille en cours de modification (null : aucune). */
  protected readonly editing = signal<Grid | null>(null);
  protected readonly canWrite = computed(() =>
    editionCapabilities(this.meStore, this.editionId()).includes('grids.write'),
  );

  protected readonly createForm = this.fb.group({
    name: ['', [Validators.required, Validators.maxLength(150)]],
    submission_type: [''],
  });
  protected readonly criteria = new FormArray<CriterionForm>([]);
  protected readonly editForm = this.fb.group({
    name: ['', [Validators.required, Validators.maxLength(150)]],
    scale_min: [0, [Validators.required, Validators.min(0)]],
    scale_max: [5, [Validators.required, Validators.max(100)]],
    criteria: this.criteria,
  });
  private readonly weights = toSignal(
    this.criteria.valueChanges.pipe(
      startWith(null),
      map(() => this.criteria.getRawValue().map((item) => Number(item.weight) || 0)),
    ),
    { initialValue: [] as number[] },
  );
  /** RG-05 : somme des poids pendant la saisie (le serveur exige exactement 100). */
  protected readonly total = computed(
    () => Math.round(this.weights().reduce((sum, weight) => sum + weight, 0) * 100) / 100,
  );

  async ngOnInit(): Promise<void> {
    try {
      const [grids, types] = await Promise.all([
        this.api.grids(this.edition()),
        this.editions.submissionTypes(this.edition()),
      ]);
      this.grids.set(grids);
      this.types.set(types);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }

  private edition(): number {
    return Number(this.editionId());
  }

  protected typeLabel(code: string | null): string {
    return code ?? this.translate.instant('gestion.grids.allTypes');
  }

  protected edit(grid: Grid): void {
    this.editing.set(grid);
    this.criteria.clear();
    for (const criterion of grid.criteria) {
      this.criteria.push(this.criterionForm(criterion));
    }
    this.editForm.patchValue({
      name: grid.name,
      scale_min: grid.scale_min,
      scale_max: grid.scale_max,
    });
  }

  private criterionForm(value: Partial<CriterionWriteRequest> = {}): CriterionForm {
    return this.fb.group({
      code: [value.code ?? '', [Validators.required, Validators.pattern(/^[-a-zA-Z0-9_]+$/)]],
      label_fr: [value.label_fr ?? '', [Validators.required, Validators.maxLength(255)]],
      label_en: [value.label_en ?? '', Validators.maxLength(255)],
      weight: [value.weight ?? '', [Validators.required, Validators.min(0.01)]],
      is_required: [value.is_required ?? true],
    });
  }

  protected addCriterion(): void {
    this.criteria.push(this.criterionForm());
  }

  protected removeCriterion(index: number): void {
    this.criteria.removeAt(index);
  }

  protected async create(): Promise<void> {
    if (this.createForm.invalid) {
      this.createForm.markAllAsTouched();
      return;
    }
    const value = this.createForm.getRawValue();
    await this.run('gestion.grids.created', async () => {
      await this.api.createGrid(this.edition(), {
        name: value.name,
        submission_type: value.submission_type || null,
      });
      this.createForm.reset();
    });
  }

  protected async save(): Promise<void> {
    const grid = this.editing();
    if (!grid || this.editForm.invalid) {
      this.editForm.markAllAsTouched();
      return;
    }
    const value = this.editForm.getRawValue();
    await this.run('gestion.grids.saved', async () => {
      await this.api.updateGrid(this.edition(), grid.id, {
        name: value.name,
        scale_min: Number(value.scale_min),
        scale_max: Number(value.scale_max),
        criteria: value.criteria.map((item) => ({
          code: item.code,
          label_fr: item.label_fr,
          label_en: item.label_en,
          weight: String(item.weight),
          is_required: item.is_required,
        })),
      });
      this.editing.set(null);
    });
  }

  protected async duplicate(grid: Grid): Promise<void> {
    await this.run('gestion.grids.duplicated', async () => {
      await this.api.duplicateGrid(this.edition(), grid.id);
    });
  }

  protected async remove(grid: Grid): Promise<void> {
    const data: ConfirmDialogData = {
      title: this.translate.instant('gestion.grids.delete.title'),
      message: this.translate.instant('gestion.grids.delete.message', { name: grid.name }),
      confirmLabel: this.translate.instant('gestion.grids.delete.confirm'),
    };
    const ref = this.dialog.open<ConfirmDialog, ConfirmDialogData, ConfirmDialogResult>(
      ConfirmDialog,
      { data, width: '30rem' },
    );
    if (!(await firstValueFrom(ref.afterClosed()))) {
      return;
    }
    await this.run('gestion.grids.deleted', async () => {
      await this.api.deleteGrid(this.edition(), grid.id);
    });
  }

  private async run(done: string, action: () => Promise<void>): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    this.status.set('');
    try {
      await action();
      this.grids.set(await this.api.grids(this.edition()));
      this.status.set(this.translate.instant(done));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }
}
