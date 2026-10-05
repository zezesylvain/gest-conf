import {
  ChangeDetectionStrategy,
  Component,
  computed,
  ElementRef,
  inject,
  input,
  OnInit,
  signal,
} from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import {
  countryOptions,
  ErrorSummary,
  fieldErrorMessage,
  focusFirstInvalid,
  LanguageService,
  MeStore,
  PageHeader,
  PatchedEditionRequest,
  SubmissionLanguage,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { EditionApi } from '../../core/edition-api';
import { editionCapabilities, errorMessages } from '../../core/page-support';

/** Fuseaux proposés : ceux du navigateur (liste IANA), sinon saisie libre vérifiée par le serveur. */
function timeZones(): string[] {
  const intl = Intl as unknown as { supportedValuesOf?: (key: string) => string[] };
  try {
    return intl.supportedValuesOf?.('timeZone') ?? [];
  } catch {
    return [];
  }
}

/** Langues des soumissions proposées (plan L3, F11). */
export const SUBMISSION_LANGUAGES: readonly SubmissionLanguage[] = ['fr', 'en'];

/**
 * Informations générales de l'édition (plan L1 §6.1), bilingues (D14 : l'anglais est exigé
 * pour publier). Lecture seule sans `edition.write` ; une édition archivée est refusée par
 * le serveur (`edition_archived`). Un changement de fuseau ne déplace pas les instants UTC
 * des dates clés : leurs heures locales affichées changent (§6.2).
 *
 * RG-19 : après la première soumission, le code est gelé. Seul un administrateur de
 * l'édition le change, avec un motif ; l'interface le montre, le serveur le décide
 * (`setting_frozen`).
 */
@Component({
  selector: 'gestion-general-page',
  imports: [
    ReactiveFormsModule,
    TranslatePipe,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './general-page.html',
  styleUrl: '../page.scss',
})
export class GeneralPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(EditionApi);
  private readonly meStore = inject(MeStore);
  private readonly translate = inject(TranslateService);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  protected readonly language = inject(LanguageService);

  protected readonly countries = computed(() => countryOptions(this.language.current()));
  protected readonly timeZones = timeZones();
  protected readonly canWrite = computed(() =>
    editionCapabilities(this.meStore, this.editionId()).includes('edition.write'),
  );
  /** Indice d'ergonomie : `edition.archive` n'appartient qu'à l'administrateur (§5.2). */
  protected readonly isAdmin = computed(() =>
    editionCapabilities(this.meStore, this.editionId()).includes('edition.archive'),
  );
  protected readonly frozen = signal<string[]>([]);
  protected readonly languages = SUBMISSION_LANGUAGES;
  private initialCode = '';
  protected readonly form = inject(NonNullableFormBuilder).group({
    code: ['', [Validators.required, Validators.pattern(/^[A-Z][A-Z0-9]{1,11}$/)]],
    slug: ['', [Validators.required, Validators.maxLength(64)]],
    year: [2027, [Validators.required, Validators.min(2000), Validators.max(2100)]],
    title_fr: ['', [Validators.required, Validators.maxLength(255)]],
    title_en: ['', Validators.maxLength(255)],
    theme_fr: [''],
    theme_en: [''],
    start_date: [''],
    end_date: [''],
    venue: ['', Validators.maxLength(255)],
    city: ['', Validators.maxLength(255)],
    country: [''],
    timezone: ['', Validators.required],
    submission_languages: [[] as SubmissionLanguage[], Validators.required],
    reason: ['', Validators.maxLength(2000)],
  });
  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly saved = signal(false);
  protected readonly errors = signal<string[]>([]);

  async ngOnInit(): Promise<void> {
    try {
      const edition = await this.api.edition(Number(this.editionId()));
      this.form.reset({
        code: edition.code,
        slug: edition.slug,
        year: edition.year,
        title_fr: edition.title_fr,
        title_en: edition.title_en ?? '',
        theme_fr: edition.theme_fr ?? '',
        theme_en: edition.theme_en ?? '',
        start_date: edition.start_date ?? '',
        end_date: edition.end_date ?? '',
        venue: edition.venue ?? '',
        city: edition.city ?? '',
        country: edition.country ?? '',
        timezone: edition.timezone ?? '',
        submission_languages: edition.submission_languages ?? ['fr', 'en'],
        reason: '',
      });
      this.initialCode = edition.code;
      this.frozen.set(edition.frozen_fields);
      if (!this.canWrite()) {
        this.form.disable();
      } else if (edition.frozen_fields.includes('code') && !this.isAdmin()) {
        this.form.controls.code.disable();
      }
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }

  protected error(name: keyof typeof this.form.controls): string {
    const control = this.form.controls[name];
    if (control.errors?.['pattern']) {
      return this.translate.instant('gestion.settings.general.codeFormat');
    }
    return fieldErrorMessage(this.translate, control);
  }

  /** Changement d'un réglage gelé (RG-19) : un motif est exigé. */
  protected frozenChange(): boolean {
    return this.frozen().includes('code') && this.form.controls.code.value !== this.initialCode;
  }

  protected async submit(): Promise<void> {
    this.errors.set([]);
    this.saved.set(false);
    if (this.frozenChange() && !this.form.controls.reason.value.trim()) {
      this.form.controls.reason.setErrors({ required: true });
    }
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      focusFirstInvalid(this.host.nativeElement);
      return;
    }
    this.saving.set(true);
    try {
      const { reason, ...value } = this.form.getRawValue();
      const body: PatchedEditionRequest = {
        ...value,
        start_date: value.start_date || null,
        end_date: value.end_date || null,
        ...(this.frozenChange() ? { reason: reason.trim() } : {}),
      };
      const saved = await this.api.updateEdition(Number(this.editionId()), body);
      this.initialCode = saved.code;
      this.form.controls.reason.reset('');
      this.form.markAsPristine();
      this.saved.set(true);
      await this.meStore.load().catch(() => undefined);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error, this.form));
      focusFirstInvalid(this.host.nativeElement);
    } finally {
      this.saving.set(false);
    }
  }
}
