import {
  ChangeDetectionStrategy,
  Component,
  DOCUMENT,
  ElementRef,
  inject,
  OnInit,
  signal,
} from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { RouterLink } from '@angular/router';
import {
  apiErrorMessage,
  applyAuthErrors,
  AuthApi,
  codeMessage,
  ErrorSummary,
  fieldErrorMessage,
  focusFirstInvalid,
  PageHeader,
  passwordsMatch,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { takeFragmentKey } from '../fragment-key';
import { PASSWORD_MIN_LENGTH } from './signup-page';

type ResetState = 'checking' | 'form' | 'invalid' | 'done';

/**
 * Réinitialisation (plan L1 §4.3) : la clé du lien (fragment) est vérifiée par
 * `GET auth/password/reset` avec l'en-tête `X-Password-Reset-Key`, jamais dans l'URL.
 * Lien valable 2 h et utilisable une seule fois.
 */
@Component({
  selector: 'portail-reset-password-page',
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
  templateUrl: './reset-password-page.html',
  styleUrl: './account-form.scss',
})
export class ResetPasswordPage implements OnInit {
  private readonly authApi = inject(AuthApi);
  private readonly translate = inject(TranslateService);
  private readonly document = inject(DOCUMENT);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  protected readonly minLength = PASSWORD_MIN_LENGTH;
  protected readonly form = inject(NonNullableFormBuilder).group(
    {
      password: ['', [Validators.required, Validators.minLength(PASSWORD_MIN_LENGTH)]],
      confirm: ['', Validators.required],
    },
    { validators: passwordsMatch },
  );
  protected readonly state = signal<ResetState>('checking');
  protected readonly submitting = signal(false);
  protected readonly errors = signal<string[]>([]);
  private key: string | null = null;

  ngOnInit(): void {
    this.key = takeFragmentKey(this.document);
    if (!this.key) {
      this.state.set('invalid');
      return;
    }
    void this.check(this.key);
  }

  protected error(name: 'password' | 'confirm'): string {
    return fieldErrorMessage(this.translate, this.form.controls[name]);
  }

  private async check(key: string): Promise<void> {
    try {
      const result = await this.authApi.checkPasswordResetKey(key);
      this.state.set(result.errors.length ? 'invalid' : 'form');
    } catch {
      this.state.set('invalid');
    }
  }

  protected async submit(): Promise<void> {
    this.errors.set([]);
    if (this.form.invalid || !this.key) {
      this.form.markAllAsTouched();
      focusFirstInvalid(this.host.nativeElement);
      return;
    }
    this.submitting.set(true);
    try {
      const result = await this.authApi.resetPassword(this.key, this.form.getRawValue().password);
      if (!result.errors.length) {
        this.state.set('done');
        return;
      }
      if (result.errors.some((item) => item.param === 'key')) {
        this.state.set('invalid');
        return;
      }
      const unplaced = applyAuthErrors(this.translate, this.form, result.errors);
      this.errors.set(unplaced.length ? unplaced : []);
      focusFirstInvalid(this.host.nativeElement);
    } catch (error) {
      this.errors.set([apiErrorMessage(this.translate, error)]);
    } finally {
      this.submitting.set(false);
    }
  }

  protected invalidMessage(): string {
    return codeMessage(this.translate, 'invalid_password_reset');
  }
}
