import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialogModule, MatDialogRef } from '@angular/material/dialog';
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
  MeStore,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

/**
 * Fenêtre de réauthentification (plan L1 §4.3, D12) : mot de passe, ou code de double
 * authentification si elle est activée. Se ferme sur `true` quand la réauthentification
 * aboutit ; l'appel interrompu est alors rejoué une seule fois.
 */
@Component({
  selector: 'portail-reauth-dialog',
  imports: [
    ReactiveFormsModule,
    TranslatePipe,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    ErrorSummary,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h2 mat-dialog-title>{{ 'portail.account.reauth.title' | translate }}</h2>
    <form [formGroup]="form" (ngSubmit)="submit()" novalidate>
      <mat-dialog-content>
        <p>{{ 'portail.account.reauth.lead' | translate }}</p>
        <gc-error-summary [messages]="errors()" />
        @if (useCode()) {
          <mat-form-field appearance="outline">
            <mat-label>{{ 'portail.account.mfa.code' | translate }}</mat-label>
            <input
              matInput
              formControlName="code"
              inputmode="numeric"
              autocomplete="one-time-code"
              required
            />
            <mat-error>{{ error('code') }}</mat-error>
          </mat-form-field>
        } @else {
          <mat-form-field appearance="outline">
            <mat-label>{{ 'portail.account.fields.password' | translate }}</mat-label>
            <input
              matInput
              type="password"
              formControlName="password"
              autocomplete="current-password"
              required
            />
            <mat-error>{{ error('password') }}</mat-error>
          </mat-form-field>
        }
        @if (mfaEnabled()) {
          <button type="button" class="link-button" (click)="toggle()">
            {{
              (useCode() ? 'portail.account.reauth.usePassword' : 'portail.account.reauth.useCode')
                | translate
            }}
          </button>
        }
      </mat-dialog-content>
      <mat-dialog-actions align="end">
        <button mat-button type="button" (click)="dialogRef.close(false)">
          {{ 'portail.account.reauth.cancel' | translate }}
        </button>
        <button mat-flat-button type="submit" [disabled]="submitting()">
          {{ 'portail.account.reauth.submit' | translate }}
        </button>
      </mat-dialog-actions>
    </form>
  `,
  styles: `
    mat-form-field {
      width: 100%;
    }
    .link-button {
      font: inherit;
      color: var(--gc-primary);
      background: none;
      border: none;
      padding: 0;
      text-decoration: underline;
      cursor: pointer;
    }
  `,
})
export class ReauthDialog {
  protected readonly dialogRef = inject<MatDialogRef<ReauthDialog, boolean>>(MatDialogRef);
  private readonly authApi = inject(AuthApi);
  private readonly translate = inject(TranslateService);
  private readonly meStore = inject(MeStore);

  protected readonly mfaEnabled = signal(this.meStore.me()?.mfa_enabled === true);
  protected readonly useCode = signal(false);
  protected readonly submitting = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly form = inject(NonNullableFormBuilder).group({
    password: ['', Validators.required],
    code: ['', Validators.required],
  });

  protected error(name: 'password' | 'code'): string {
    return fieldErrorMessage(this.translate, this.form.controls[name]);
  }

  protected toggle(): void {
    this.useCode.update((value) => !value);
    this.errors.set([]);
  }

  protected async submit(): Promise<void> {
    this.errors.set([]);
    const control = this.useCode() ? this.form.controls.code : this.form.controls.password;
    if (control.invalid) {
      control.markAsTouched();
      return;
    }
    this.submitting.set(true);
    try {
      const result = this.useCode()
        ? await this.authApi.mfaReauthenticate(control.value.trim())
        : await this.authApi.reauthenticate(control.value);
      if (result.status === 200 && result.authenticated) {
        this.dialogRef.close(true);
        return;
      }
      const unplaced = applyAuthErrors(this.translate, this.form, result.errors);
      this.errors.set(
        unplaced.length || result.errors.length
          ? unplaced
          : [codeMessage(this.translate, fallbackCode(result.status))],
      );
    } catch (error) {
      this.errors.set([apiErrorMessage(this.translate, error)]);
    } finally {
      this.submitting.set(false);
    }
  }
}
