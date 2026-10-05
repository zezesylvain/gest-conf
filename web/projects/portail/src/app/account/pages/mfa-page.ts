import {
  ChangeDetectionStrategy,
  Component,
  computed,
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
  ErrorSummary,
  fallbackCode,
  fieldErrorMessage,
  focusFirstInvalid,
  MeStore,
  navigateAfterLogin,
  PageHeader,
  SessionStore,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

/**
 * Saisie d'un code de double authentification (plan L1 §10.2) : code TOTP ou code de
 * secours, pour l'étape 2FA de la connexion (flux `mfa_authenticate`) ou pour valider
 * une session déjà ouverte avant la gestion (*step-up*, `mfa_required`). Suite vers
 * `next` (validé).
 */
@Component({
  selector: 'portail-mfa-page',
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
    <gc-page-header [heading]="'portail.account.mfa.title' | translate" />
    <p>
      {{ (stepUp() ? 'portail.account.mfa.stepUpLead' : 'portail.account.mfa.lead') | translate }}
    </p>
    <gc-error-summary [messages]="errors()" />
    <form [formGroup]="form" (ngSubmit)="submit()" novalidate>
      <mat-form-field appearance="outline">
        <mat-label>{{ 'portail.account.mfa.code' | translate }}</mat-label>
        <input
          matInput
          formControlName="code"
          inputmode="numeric"
          autocomplete="one-time-code"
          required
        />
        <mat-hint>{{ 'portail.account.mfa.codeHint' | translate }}</mat-hint>
        <mat-error>{{ error() }}</mat-error>
      </mat-form-field>
      <div class="actions">
        <button mat-flat-button type="submit" [disabled]="submitting()">
          {{ 'portail.account.mfa.submit' | translate }}
        </button>
      </div>
    </form>
    @if (!stepUp()) {
      <ul class="links">
        <li>
          <a routerLink="/compte/connexion">{{ 'portail.account.mfa.backToLogin' | translate }}</a>
        </li>
      </ul>
    }
  `,
  styleUrl: './account-form.scss',
})
export class MfaPage {
  private readonly authApi = inject(AuthApi);
  private readonly meStore = inject(MeStore);
  private readonly session = inject(SessionStore);
  private readonly translate = inject(TranslateService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly document = inject(DOCUMENT);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  /** Session déjà ouverte : réauthentification 2FA ; sinon, étape 2FA de la connexion. */
  protected readonly stepUp = computed(() => this.session.authenticated());
  protected readonly form = inject(NonNullableFormBuilder).group({
    code: ['', Validators.required],
  });
  protected readonly submitting = signal(false);
  protected readonly errors = signal<string[]>([]);

  protected error(): string {
    return fieldErrorMessage(this.translate, this.form.controls.code);
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
      const code = this.form.controls.code.value.replace(/\s+/g, '');
      const result = this.stepUp()
        ? await this.authApi.mfaReauthenticate(code)
        : await this.authApi.mfaAuthenticate(code);
      if (result.status === 200 && result.authenticated) {
        await this.meStore.load().catch(() => undefined);
        navigateAfterLogin(
          this.router,
          this.document,
          this.route.snapshot.queryParamMap.get('next'),
        );
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
