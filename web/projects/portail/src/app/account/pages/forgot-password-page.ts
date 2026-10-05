import { ChangeDetectionStrategy, Component, ElementRef, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { RouterLink } from '@angular/router';
import {
  apiErrorMessage,
  applyAuthErrors,
  AuthApi,
  ErrorSummary,
  fieldErrorMessage,
  focusFirstInvalid,
  PageHeader,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

/**
 * Mot de passe oublié (plan L1 §4.3). Réponse identique que le compte existe ou non ;
 * l'e-mail n'est jamais envoyé pendant la requête (anti-énumération par le temps, §8.3) :
 * il part au passage suivant de la tâche planifiée, ce que l'écran annonce.
 */
@Component({
  selector: 'portail-forgot-password-page',
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
  template: `
    <gc-page-header
      [heading]="'portail.account.forgot.title' | translate"
      [lead]="'portail.account.forgot.lead' | translate"
    />
    @if (sent()) {
      <div class="notice" role="status">
        <p>{{ 'portail.account.forgot.sent' | translate }}</p>
      </div>
    } @else {
      <gc-error-summary [messages]="errors()" />
      <form [formGroup]="form" (ngSubmit)="submit()" novalidate>
        <mat-form-field appearance="outline">
          <mat-label>{{ 'portail.account.fields.email' | translate }}</mat-label>
          <input matInput type="email" formControlName="email" autocomplete="email" required />
          <mat-error>{{ emailError() }}</mat-error>
        </mat-form-field>
        <div class="actions">
          <button mat-flat-button type="submit" [disabled]="submitting()">
            {{ 'portail.account.forgot.submit' | translate }}
          </button>
        </div>
      </form>
    }
    <ul class="links">
      <li>
        <a routerLink="/compte/connexion">{{ 'portail.account.forgot.login' | translate }}</a>
      </li>
    </ul>
  `,
  styleUrl: './account-form.scss',
})
export class ForgotPasswordPage {
  private readonly authApi = inject(AuthApi);
  private readonly translate = inject(TranslateService);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  protected readonly form = inject(NonNullableFormBuilder).group({
    email: ['', [Validators.required, Validators.email]],
  });
  protected readonly submitting = signal(false);
  protected readonly sent = signal(false);
  protected readonly errors = signal<string[]>([]);

  protected emailError(): string {
    return fieldErrorMessage(this.translate, this.form.controls.email);
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
      const result = await this.authApi.requestPasswordReset(this.form.getRawValue().email);
      if (result.errors.length) {
        this.errors.set(applyAuthErrors(this.translate, this.form, result.errors));
        focusFirstInvalid(this.host.nativeElement);
      } else {
        this.sent.set(true);
      }
    } catch (error) {
      this.errors.set([apiErrorMessage(this.translate, error)]);
    } finally {
      this.submitting.set(false);
    }
  }
}
