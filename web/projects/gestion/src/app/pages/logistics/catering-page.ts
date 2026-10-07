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
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import {
  DietarySummary,
  ErrorSummary,
  LanguageService,
  Meal,
  MealKind,
  MeStore,
  Option,
  PageHeader,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { LogisticsApi } from '../../core/logistics-api';
import { editionCapabilities, errorMessages } from '../../core/page-support';
import { RegistrationsApi, saveBlob } from '../../core/registrations-api';
import { confirmAction } from '../events/events-support';
import { formatDay } from '../organisation/organisation-support';
import { DIETS, MEAL_KINDS } from './logistics-support';

/**
 * Restauration (plan L8, N7, N8 ; `logistics.read`, écriture `logistics.write`) : repas et
 * effectifs **estimés** (personnes comptées une fois, marge, régimes agrégés, sans nom),
 * commande au traiteur en CSV, XLSX ou PDF ; régimes déclarés en effectifs, liste nominative
 * par un export journalisé avec réauthentification (RG-23).
 */
@Component({
  selector: 'gestion-catering-page',
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
  templateUrl: './catering-page.html',
  styleUrl: '../page.scss',
  styles: `
    .checks {
      display: flex;
      flex-wrap: wrap;
      gap: 0.25rem 1rem;
    }
    .number {
      text-align: end;
    }
  `,
})
export class CateringPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(LogisticsApi);
  private readonly registrations = inject(RegistrationsApi);
  private readonly dialog = inject(MatDialog);
  private readonly meStore = inject(MeStore);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly kinds = MEAL_KINDS;
  protected readonly diets = DIETS;
  protected readonly meals = signal<Meal[]>([]);
  protected readonly dietary = signal<DietarySummary | null>(null);
  protected readonly options = signal<Option[]>([]);
  protected readonly editing = signal<Meal | null>(null);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  protected readonly canWrite = computed(() =>
    editionCapabilities(this.meStore, this.editionId()).includes('logistics.write'),
  );

  protected readonly form = inject(NonNullableFormBuilder).group({
    day: ['', Validators.required],
    kind: ['lunch' as MealKind],
    label_fr: ['', Validators.maxLength(150)],
    label_en: ['', Validators.maxLength(150)],
    include_registered: [true],
    option_code: [''],
    include_speakers: [false],
    include_committees: [false],
    include_volunteers: [false],
    margin_percent: [5, [Validators.min(0), Validators.max(50)]],
  });

  async ngOnInit(): Promise<void> {
    const edition = this.edition();
    try {
      const [meals, dietary] = await Promise.all([
        this.api.meals(edition),
        this.api.dietary(edition),
      ]);
      this.meals.set(meals);
      this.dietary.set(dietary);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
    try {
      // Options de L6 (dîner de gala…) : lues si le compte lit les inscriptions.
      this.options.set(await this.registrations.options(edition));
    } catch {
      this.options.set([]);
    }
    this.loading.set(false);
  }

  private edition(): number {
    return Number(this.editionId());
  }

  protected day(value: string): string {
    return formatDay(value, this.language.current());
  }

  protected mealLabel(meal: Meal): string {
    const label = (this.language.current() === 'en' && meal.label_en) || meal.label_fr;
    const kind = this.translate.instant(`gestion.catering.kind.${meal.kind}`);
    return label ? `${kind} — ${label}` : kind;
  }

  protected optionLabel(option: Option): string {
    return (this.language.current() === 'en' && option.label_en) || option.label_fr;
  }

  protected audience(meal: Meal): string {
    const parts: string[] = [];
    if (meal.include_registered) {
      parts.push(
        meal.option_code
          ? this.translate.instant('gestion.catering.audience.option', { code: meal.option_code })
          : this.translate.instant('gestion.catering.audience.registered'),
      );
    }
    if (meal.include_speakers)
      parts.push(this.translate.instant('gestion.catering.audience.speakers'));
    if (meal.include_committees)
      parts.push(this.translate.instant('gestion.catering.audience.committees'));
    if (meal.include_volunteers)
      parts.push(this.translate.instant('gestion.catering.audience.volunteers'));
    return parts.join(', ') || '—';
  }

  protected diet(meal: Meal, diet: string): number {
    return meal.estimate.by_diet[diet] ?? 0;
  }

  protected edit(meal: Meal): void {
    this.editing.set(meal);
    this.form.reset({
      day: meal.day,
      kind: meal.kind,
      label_fr: meal.label_fr,
      label_en: meal.label_en,
      include_registered: meal.include_registered,
      option_code: meal.option_code,
      include_speakers: meal.include_speakers,
      include_committees: meal.include_committees,
      include_volunteers: meal.include_volunteers,
      margin_percent: meal.margin_percent,
    });
  }

  protected cancelEdit(): void {
    this.editing.set(null);
    this.form.reset();
  }

  protected async submit(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const body = {
      ...this.form.getRawValue(),
      margin_percent: Number(this.form.getRawValue().margin_percent),
    };
    const meal = this.editing();
    await this.run(meal ? 'gestion.catering.updated' : 'gestion.catering.created', async () => {
      const meals = meal
        ? await this.api.updateMeal(this.edition(), meal.id, body)
        : await this.api.createMeal(this.edition(), body);
      this.cancelEdit();
      return meals;
    });
  }

  protected async remove(meal: Meal): Promise<void> {
    const answer = await confirmAction(this.dialog, this.translate, 'gestion.catering.delete', {
      label: this.mealLabel(meal),
    });
    if (!answer) return;
    await this.run('gestion.catering.deleted', () => this.api.deleteMeal(this.edition(), meal.id));
  }

  protected async exportMeals(fileFormat: 'csv' | 'xlsx' | 'pdf'): Promise<void> {
    await this.download(
      () => this.api.exportMeals(this.edition(), fileFormat),
      `repas.${fileFormat}`,
    );
  }

  protected async exportDietary(fileFormat: 'csv' | 'xlsx'): Promise<void> {
    await this.download(
      () => this.api.exportDietary(this.edition(), fileFormat),
      `regimes.${fileFormat}`,
    );
  }

  private async download(action: () => Promise<Blob>, name: string): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    try {
      saveBlob(await action(), name);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }

  private async run(message: string, action: () => Promise<Meal[]>): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    this.status.set('');
    try {
      this.meals.set(await action());
      this.status.set(this.translate.instant(message));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error, this.form));
    } finally {
      this.busy.set(false);
    }
  }
}
