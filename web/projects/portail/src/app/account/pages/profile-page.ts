import {
  ChangeDetectionStrategy,
  Component,
  computed,
  ElementRef,
  inject,
  OnInit,
  signal,
} from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import {
  apiErrorMessage,
  applyServerErrors,
  ErrorSummary,
  fieldErrorMessage,
  focusFirstInvalid,
  GcApiError,
  LanguageService,
  MeStore,
  PageHeader,
  countryOptions,
  ProfileTitle,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { AccountService } from '../account.service';

const ORCID_PATTERN = /^\d{4}-\d{4}-\d{4}-\d{3}[\dXx]$/;
// « '' » : aucun titre (BlankEnum dans le schéma).
type TitleValue = ProfileTitle | '';
const TITLES: TitleValue[] = ['', 'dr', 'pr', 'mr', 'ms'];

type ProfileField =
  'title' | 'first_name' | 'last_name' | 'institution' | 'department' | 'country' | 'orcid' | 'bio';

/**
 * Profil (plan L1 §3.3) : nom, prénom, institution et pays forment le profil complet
 * (prérequis de la soumission en L3). La clé de contrôle de l'ORCID est vérifiée par le
 * serveur. La langue est celle de l'interface, enregistrée dans le compte.
 */
@Component({
  selector: 'portail-profile-page',
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
  templateUrl: './profile-page.html',
  styleUrl: './account-form.scss',
})
export class ProfilePage implements OnInit {
  private readonly account = inject(AccountService);
  private readonly meStore = inject(MeStore);
  private readonly translate = inject(TranslateService);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  protected readonly language = inject(LanguageService);

  protected readonly titles = TITLES;
  protected readonly countries = computed(() => countryOptions(this.language.current()));
  protected readonly form = inject(NonNullableFormBuilder).group({
    title: ['' as TitleValue],
    first_name: ['', [Validators.required, Validators.maxLength(150)]],
    last_name: ['', [Validators.required, Validators.maxLength(150)]],
    institution: ['', [Validators.required, Validators.maxLength(255)]],
    department: ['', Validators.maxLength(255)],
    country: ['', Validators.required],
    orcid: ['', Validators.pattern(ORCID_PATTERN)],
    bio: ['', Validators.maxLength(2000)],
  });
  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly saved = signal(false);
  protected readonly errors = signal<string[]>([]);

  async ngOnInit(): Promise<void> {
    try {
      const profile = await this.account.profile();
      this.form.patchValue({
        title: profile.title ?? '',
        first_name: profile.first_name ?? '',
        last_name: profile.last_name ?? '',
        institution: profile.institution ?? '',
        department: profile.department ?? '',
        country: profile.country ?? '',
        orcid: profile.orcid ?? '',
        bio: profile.bio ?? '',
      });
    } catch (error) {
      this.errors.set([apiErrorMessage(this.translate, error)]);
    } finally {
      this.loading.set(false);
    }
  }

  protected error(name: ProfileField): string {
    const control = this.form.controls[name];
    if (control.errors?.['pattern']) {
      return this.translate.instant('portail.account.profile.orcidFormat');
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
      const profile = await this.account.updateProfile(this.form.getRawValue());
      this.form.patchValue({ orcid: profile.orcid ?? '', country: profile.country ?? '' });
      this.saved.set(true);
      await this.meStore.load();
    } catch (error) {
      if (error instanceof GcApiError && Object.keys(error.fields).length) {
        this.errors.set(applyServerErrors(this.form, error));
        focusFirstInvalid(this.host.nativeElement);
      } else {
        this.errors.set([apiErrorMessage(this.translate, error)]);
      }
    } finally {
      this.saving.set(false);
    }
  }
}
