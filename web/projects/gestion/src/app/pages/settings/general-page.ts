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

/**
 * Informations générales de l'édition (plan L1 §6.1), bilingues (D14 : l'anglais est exigé
 * pour publier). Lecture seule sans `edition.write` ; une édition archivée est refusée par
 * le serveur (`edition_archived`). Un changement de fuseau ne déplace pas les instants UTC
 * des dates clés : leurs heures locales affichées changent (§6.2).
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
      });
      if (!this.canWrite()) {
        this.form.disable();
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

  protected async submit(): Promise<void> {
    this.errors.set([]);
    this.saved.set(false);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      focusFirstInvalid(this.host.nativeElement);
      return;
    }
    this.saving.set(true);
    try {
      const value = this.form.getRawValue();
      const body: PatchedEditionRequest = {
        ...value,
        start_date: value.start_date || null,
        end_date: value.end_date || null,
      };
      await this.api.updateEdition(Number(this.editionId()), body);
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
