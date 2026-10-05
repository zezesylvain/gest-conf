import { ChangeDetectionStrategy, Component, ElementRef, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { Router, RouterLink } from '@angular/router';
import {
  apiErrorMessage,
  applyAuthErrors,
  AuthApi,
  codeMessage,
  ErrorSummary,
  fallbackCode,
  fieldErrorMessage,
  focusFirstInvalid,
  PageHeader,
  passwordsMatch,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { PrivacyNotice } from '../ui/privacy-notice';

/** Longueur minimale imposée par le serveur (AUTH_PASSWORD_VALIDATORS). */
export const PASSWORD_MIN_LENGTH = 12;

/**
 * Inscription (plan L1 §4.3). La réponse est identique que l'adresse soit nouvelle ou déjà
 * connue (anti-énumération) : dans les deux cas, on invite à consulter ses e-mails. La
 * langue courante, transmise par `Accept-Language`, devient celle du compte.
 */
@Component({
  selector: 'portail-signup-page',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TranslatePipe,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    ErrorSummary,
    PageHeader,
    PrivacyNotice,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './signup-page.html',
  styleUrl: './account-form.scss',
})
export class SignupPage {
  private readonly authApi = inject(AuthApi);
  private readonly translate = inject(TranslateService);
  private readonly router = inject(Router);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  protected readonly minLength = PASSWORD_MIN_LENGTH;
  protected readonly form = inject(NonNullableFormBuilder).group(
    {
      email: ['', [Validators.required, Validators.email]],
      password: ['', [Validators.required, Validators.minLength(PASSWORD_MIN_LENGTH)]],
      confirm: ['', Validators.required],
    },
    { validators: passwordsMatch },
  );
  protected readonly submitting = signal(false);
  protected readonly errors = signal<string[]>([]);

  protected error(name: 'email' | 'password' | 'confirm'): string {
    return fieldErrorMessage(this.translate, this.form.controls[name]);
  }

  protected async submit(): Promise<void> {
    this.errors.set([]);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      focusFirstInvalid(this.host.nativeElement);
      return;
    }
    this.submitting.set(true);
    try {
      const { email, password } = this.form.getRawValue();
      const result = await this.authApi.signup(email, password);
      if (result.pendingFlow === 'verify_email' || result.authenticated) {
        await this.router.navigate(['/compte/verifier-email'], { state: { email } });
        return;
      }
      const unplaced = applyAuthErrors(this.translate, this.form, result.errors);
      this.errors.set(
        unplaced.length || result.errors.length
          ? unplaced
          : [codeMessage(this.translate, fallbackCode(result.status))],
      );
      focusFirstInvalid(this.host.nativeElement);
    } catch (error) {
      this.errors.set([apiErrorMessage(this.translate, error)]);
    } finally {
      this.submitting.set(false);
    }
  }
}
