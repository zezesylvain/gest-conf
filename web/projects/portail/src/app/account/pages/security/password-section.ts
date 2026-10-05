import { ChangeDetectionStrategy, Component, ElementRef, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import {
  apiErrorMessage,
  applyAuthErrors,
  AuthApi,
  codeMessage,
  ErrorSummary,
  fallbackCode,
  fieldErrorMessage,
  focusFirstInvalid,
  passwordsMatch,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { PASSWORD_MIN_LENGTH } from '../signup-page';

/**
 * Changement de mot de passe (plan L1 §4.3) : l'ancien mot de passe est exigé (pas de
 * réauthentification). allauth notifie l'adresse principale ; les autres sessions sont
 * fermées (le hachage de session change).
 */
@Component({
  selector: 'portail-password-section',
  imports: [
    ReactiveFormsModule,
    TranslatePipe,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    ErrorSummary,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="card" aria-labelledby="password-title">
      <h2 id="password-title">{{ 'portail.account.security.passwordTitle' | translate }}</h2>
      <div aria-live="polite">
        @if (saved()) {
          <p class="notice" role="status">
            {{ 'portail.account.security.passwordChanged' | translate }}
          </p>
        }
      </div>
      <gc-error-summary [messages]="errors()" />
      <form [formGroup]="form" (ngSubmit)="submit()" novalidate>
        <mat-form-field appearance="outline">
          <mat-label>{{ 'portail.account.security.currentPassword' | translate }}</mat-label>
          <input
            matInput
            type="password"
            formControlName="current_password"
            autocomplete="current-password"
            required
          />
          <mat-error>{{ error('current_password') }}</mat-error>
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>{{ 'portail.account.fields.newPassword' | translate }}</mat-label>
          <input
            matInput
            type="password"
            formControlName="password"
            autocomplete="new-password"
            required
          />
          <mat-hint>{{
            'portail.account.fields.passwordHint' | translate: { min: minLength }
          }}</mat-hint>
          <mat-error>{{ error('password') }}</mat-error>
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>{{ 'portail.account.fields.passwordConfirm' | translate }}</mat-label>
          <input
            matInput
            type="password"
            formControlName="confirm"
            autocomplete="new-password"
            required
          />
          <mat-error>{{ error('confirm') }}</mat-error>
        </mat-form-field>
        <div class="actions">
          <button mat-flat-button type="submit" [disabled]="saving()">
            {{ 'portail.account.security.changePassword' | translate }}
          </button>
        </div>
      </form>
    </section>
  `,
  styleUrl: './security.scss',
})
export class PasswordSection {
  private readonly authApi = inject(AuthApi);
  private readonly translate = inject(TranslateService);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  protected readonly minLength = PASSWORD_MIN_LENGTH;
  protected readonly form = inject(NonNullableFormBuilder).group(
    {
      current_password: ['', Validators.required],
      password: ['', [Validators.required, Validators.minLength(PASSWORD_MIN_LENGTH)]],
      confirm: ['', Validators.required],
    },
    { validators: passwordsMatch },
  );
  protected readonly saving = signal(false);
  protected readonly saved = signal(false);
  protected readonly errors = signal<string[]>([]);

  protected error(name: 'current_password' | 'password' | 'confirm'): string {
    return fieldErrorMessage(this.translate, this.form.controls[name]);
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
      const { current_password, password } = this.form.getRawValue();
      const result = await this.authApi.changePassword(current_password, password);
      if (result.status === 200) {
        this.form.reset();
        this.saved.set(true);
        return;
      }
      // allauth nomme le champ « new_password » : rapproché du champ « password ».
      const errors = result.errors.map((item) =>
        item.param === 'new_password' ? { ...item, param: 'password' } : item,
      );
      const unplaced = applyAuthErrors(this.translate, this.form, errors);
      this.errors.set(
        unplaced.length || errors.length
          ? unplaced
          : [codeMessage(this.translate, fallbackCode(result.status))],
      );
      focusFirstInvalid(this.host.nativeElement);
    } catch (error) {
      this.errors.set([apiErrorMessage(this.translate, error)]);
    } finally {
      this.saving.set(false);
    }
  }
}
