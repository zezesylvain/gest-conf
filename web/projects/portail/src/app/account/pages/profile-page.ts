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
  Profile,
  ProfileTitle,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { AccountService } from '../account.service';

const ORCID_PATTERN = /^\d{4}-\d{4}-\d{4}-\d{3}[\dXx]$/;
// « '' » : aucun titre (BlankEnum dans le schéma).
type TitleValue = ProfileTitle | '';
const TITLES: TitleValue[] = ['', 'dr', 'pr', 'mr', 'ms'];

type ProfileField =
  | 'title'
  | 'first_name'
  | 'last_name'
  | 'institution'
  | 'department'
  | 'country'
  | 'orcid'
  | 'bio'
  | 'website'
  | 'scholar_url'
  | 'linkedin_url';

/** Lien public : adresse https:// complète (le serveur revérifie). */
const HTTPS_LINK = /^https:\/\/\S+$/;
/** Aperçu de sa propre photo (authentifié, même sans consentement de publication). */
const OWN_PHOTO_URL = '/api/v1/me/photo';

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
  styles: `
    .photo {
      display: grid;
      gap: 0.5rem;
      margin-bottom: 1.5rem;
    }
    .photo h2,
    .profile-links legend {
      margin: 0;
      font-size: 1.1rem;
      font-weight: 600;
    }
    .photo img {
      width: 10rem;
      height: 10rem;
      object-fit: cover;
      border-radius: 50%;
      border: 1px solid var(--gc-border);
    }
    .file {
      display: grid;
      gap: 0.25rem;
    }
    .profile-links {
      margin: 1rem 0 0;
      padding: 0;
      border: 0;
    }
  `,
})
export class ProfilePage implements OnInit {
  private readonly account = inject(AccountService);
  private readonly meStore = inject(MeStore);
  private readonly translate = inject(TranslateService);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  protected readonly language = inject(LanguageService);

  protected readonly titles = TITLES;
  protected readonly linkFields = ['website', 'scholar_url', 'linkedin_url'] as const;
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
    website: ['', [Validators.maxLength(300), Validators.pattern(HTTPS_LINK)]],
    scholar_url: ['', [Validators.maxLength(300), Validators.pattern(HTTPS_LINK)]],
    linkedin_url: ['', [Validators.maxLength(300), Validators.pattern(HTTPS_LINK)]],
  });
  /** Adresse d'aperçu de la photo (paramètre de version : contourne le cache après un envoi). */
  protected readonly photo = signal<string | null>(null);
  protected readonly photoBusy = signal(false);
  protected readonly photoStatus = signal('');
  private photoVersion = 0;
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
        website: profile.website ?? '',
        scholar_url: profile.scholar_url ?? '',
        linkedin_url: profile.linkedin_url ?? '',
      });
      this.showPhoto(profile);
    } catch (error) {
      this.errors.set([apiErrorMessage(this.translate, error)]);
    } finally {
      this.loading.set(false);
    }
  }

  protected error(name: ProfileField): string {
    const control = this.form.controls[name];
    if (control.errors?.['pattern']) {
      return this.translate.instant(
        name === 'orcid'
          ? 'portail.account.profile.orcidFormat'
          : 'portail.account.profile.linkFormat',
      );
    }
    return fieldErrorMessage(this.translate, control);
  }

  protected async uploadPhoto(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) {
      return;
    }
    await this.photoAction(
      () => this.account.uploadPhoto(file),
      'portail.account.profile.photoSaved',
    );
    input.value = '';
  }

  protected async removePhoto(): Promise<void> {
    await this.photoAction(
      () => this.account.deletePhoto(),
      'portail.account.profile.photoRemoved',
    );
  }

  private async photoAction(action: () => Promise<Profile>, successKey: string): Promise<void> {
    this.errors.set([]);
    this.photoStatus.set('');
    this.photoBusy.set(true);
    try {
      this.showPhoto(await action());
      this.photoStatus.set(this.translate.instant(successKey));
    } catch (error) {
      this.errors.set([
        apiErrorMessage(this.translate, error),
        ...(error instanceof GcApiError ? Object.values(error.fields).flat() : []),
      ]);
    } finally {
      this.photoBusy.set(false);
    }
  }

  private showPhoto(profile: Profile): void {
    this.photoVersion += 1;
    this.photo.set(profile.photo_url ? `${OWN_PHOTO_URL}?v=${this.photoVersion}` : null);
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
