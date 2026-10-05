import {
  ChangeDetectionStrategy,
  Component,
  DOCUMENT,
  ElementRef,
  inject,
  signal,
} from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import {
  apiErrorMessage,
  applyAuthErrors,
  AuthApi,
  codeMessage,
  fallbackCode,
  ErrorSummary,
  fieldErrorMessage,
  focusFirstInvalid,
  navigateAfterLogin,
  PageHeader,
  SessionStore,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

/**
 * Connexion (plan L1 §4.3). Une adresse non vérifiée renvoie le flux `verify_email` :
 * allauth renvoie alors le lien de vérification (au plus une fois toutes les 3 min).
 * La 2FA (flux `mfa_authenticate`) arrive en L1.6.
 */
@Component({
  selector: 'portail-login-page',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TranslatePipe,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './login-page.html',
  styleUrl: './account-form.scss',
})
export class LoginPage {
  private readonly authApi = inject(AuthApi);
  private readonly translate = inject(TranslateService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly document = inject(DOCUMENT);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  protected readonly session = inject(SessionStore);

  protected readonly form = inject(NonNullableFormBuilder).group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', Validators.required],
  });
  protected readonly submitting = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly verificationPending = signal(false);

  protected error(name: 'email' | 'password'): string {
    return fieldErrorMessage(this.translate, this.form.controls[name]);
  }

  protected async submit(): Promise<void> {
    this.errors.set([]);
    this.verificationPending.set(false);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      focusFirstInvalid(this.host.nativeElement);
      return;
    }
    this.submitting.set(true);
    try {
      const { email, password } = this.form.getRawValue();
      const result = await this.authApi.login(email, password);
      if (result.authenticated) {
        navigateAfterLogin(
          this.router,
          this.document,
          this.route.snapshot.queryParamMap.get('next'),
        );
      } else if (result.pendingFlow === 'verify_email') {
        this.verificationPending.set(true);
      } else {
        const unplaced = applyAuthErrors(this.translate, this.form, result.errors);
        this.errors.set(
          unplaced.length || result.errors.length
            ? unplaced
            : [codeMessage(this.translate, fallbackCode(result.status))],
        );
        focusFirstInvalid(this.host.nativeElement);
      }
    } catch (error) {
      this.errors.set([apiErrorMessage(this.translate, error)]);
    } finally {
      this.submitting.set(false);
    }
  }
}
