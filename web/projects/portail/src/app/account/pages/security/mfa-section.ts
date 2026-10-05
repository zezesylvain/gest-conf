import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DOCUMENT,
  inject,
  OnInit,
  signal,
} from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { ActivatedRoute, Router } from '@angular/router';
import {
  apiErrorMessage,
  applyAuthErrors,
  AuthApi,
  AuthenticatorInfo,
  AuthResult,
  codeMessage,
  ErrorSummary,
  fallbackCode,
  fieldErrorMessage,
  MeStore,
  RecoveryCodesInfo,
  TotpSetup,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { AccountService } from '../../account.service';

type MfaStep = 'loading' | 'disabled' | 'setup' | 'enabled';

/**
 * Double authentification (plan L1 §4.3, §10.2) : activation par QR code (ou clé en
 * texte), codes de secours, désactivation. allauth exige une réauthentification récente
 * pour activer, désactiver ou voir les codes : la fenêtre s'ouvre alors d'elle-même.
 * Après l'activation, la session doit encore être validée par un code (*step-up*) : la
 * page renvoie vers `/compte/double-authentification`, qui reprend `next` s'il y en a un.
 */
@Component({
  selector: 'portail-mfa-section',
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
    <section class="card" aria-labelledby="mfa-title">
      <h2 id="mfa-title">{{ 'portail.account.security.mfaTitle' | translate }}</h2>
      <div aria-live="polite">
        @if (status()) {
          <p class="notice" role="status">{{ status() }}</p>
        }
      </div>
      <gc-error-summary [messages]="errors()" />

      @switch (step()) {
        @case ('loading') {
          <p role="status">{{ 'portail.account.home.loading' | translate }}</p>
        }
        @case ('disabled') {
          <p>{{ 'portail.account.security.mfaDisabled' | translate }}</p>
          <p class="hint">{{ 'portail.account.security.mfaRequiredHint' | translate }}</p>
          <button mat-flat-button type="button" (click)="startSetup()" [disabled]="busy()">
            {{ 'portail.account.security.enable' | translate }}
          </button>
        }
        @case ('setup') {
          @if (setup(); as pending) {
            <p>{{ 'portail.account.security.scanLead' | translate }}</p>
            @if (qrCode()) {
              <img
                class="qr"
                [src]="qrCode()"
                width="200"
                height="200"
                [alt]="'portail.account.security.qrAlt' | translate"
              />
            }
            <p>
              {{ 'portail.account.security.manualKey' | translate }}
              <code class="secret">{{ pending.secret }}</code>
              <button mat-button type="button" (click)="copySecret(pending.secret)">
                {{ 'portail.account.security.copy' | translate }}
              </button>
            </p>
            <form [formGroup]="form" (ngSubmit)="activate()" novalidate>
              <mat-form-field appearance="outline">
                <mat-label>{{ 'portail.account.mfa.code' | translate }}</mat-label>
                <input
                  matInput
                  formControlName="code"
                  inputmode="numeric"
                  autocomplete="one-time-code"
                  required
                />
                <mat-error>{{ codeError() }}</mat-error>
              </mat-form-field>
              <div class="actions">
                <button mat-flat-button type="submit" [disabled]="busy()">
                  {{ 'portail.account.security.activate' | translate }}
                </button>
              </div>
            </form>
          }
        }
        @case ('enabled') {
          <p>{{ 'portail.account.security.mfaEnabled' | translate }}</p>
          @if (needsStepUp()) {
            <div class="notice">
              <p>{{ 'portail.account.security.stepUpNeeded' | translate }}</p>
              <button mat-stroked-button type="button" (click)="goToStepUp()">
                {{ 'portail.account.security.stepUp' | translate }}
              </button>
            </div>
          }

          <h3>{{ 'portail.account.security.recoveryTitle' | translate }}</h3>
          <p>{{ 'portail.account.security.recoveryLead' | translate }}</p>
          @if (remaining() !== null) {
            <p>
              {{ 'portail.account.security.recoveryRemaining' | translate: { count: remaining() } }}
            </p>
          }
          @if (codes(); as list) {
            <ul
              class="codes"
              [attr.aria-label]="'portail.account.security.recoveryTitle' | translate"
            >
              @for (code of list; track code) {
                <li>
                  <code>{{ code }}</code>
                </li>
              }
            </ul>
          }
          <div class="actions">
            <button mat-stroked-button type="button" (click)="showCodes()" [disabled]="busy()">
              {{ 'portail.account.security.showCodes' | translate }}
            </button>
            <button mat-stroked-button type="button" (click)="regenerate()" [disabled]="busy()">
              {{ 'portail.account.security.regenerate' | translate }}
            </button>
          </div>

          <h3>{{ 'portail.account.security.disableTitle' | translate }}</h3>
          <p class="hint">{{ 'portail.account.security.disableWarning' | translate }}</p>
          @if (confirmingDisable()) {
            <div class="actions">
              <button mat-flat-button type="button" (click)="disable()" [disabled]="busy()">
                {{ 'portail.account.security.disableConfirm' | translate }}
              </button>
              <button mat-button type="button" (click)="confirmingDisable.set(false)">
                {{ 'portail.account.reauth.cancel' | translate }}
              </button>
            </div>
          } @else {
            <button mat-stroked-button type="button" (click)="confirmingDisable.set(true)">
              {{ 'portail.account.security.disable' | translate }}
            </button>
          }
        }
      }
    </section>
  `,
  styleUrl: './security.scss',
})
export class MfaSection implements OnInit {
  private readonly authApi = inject(AuthApi);
  private readonly account = inject(AccountService);
  private readonly meStore = inject(MeStore);
  private readonly translate = inject(TranslateService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly document = inject(DOCUMENT);

  protected readonly step = signal<MfaStep>('loading');
  protected readonly setup = signal<TotpSetup | null>(null);
  protected readonly qrCode = signal<string | null>(null);
  protected readonly authenticators = signal<AuthenticatorInfo[]>([]);
  protected readonly codes = signal<string[] | null>(null);
  protected readonly busy = signal(false);
  protected readonly confirmingDisable = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  protected readonly form = inject(NonNullableFormBuilder).group({
    code: ['', Validators.required],
  });

  protected readonly remaining = computed(() => {
    const recovery = this.authenticators().find((item) => item.type === 'recovery_codes');
    return recovery?.unused_code_count ?? null;
  });
  /** 2FA active mais session pas encore validée par un code (gestion refusée). */
  protected readonly needsStepUp = computed(() => this.meStore.me()?.mfa_verified === false);

  async ngOnInit(): Promise<void> {
    await this.refresh();
  }

  protected codeError(): string {
    return fieldErrorMessage(this.translate, this.form.controls.code);
  }

  protected async startSetup(): Promise<void> {
    await this.run(async () => {
      const { setup, result } = await this.authApi.totpSetup();
      if (!setup) {
        this.showResultErrors(result);
        return;
      }
      this.setup.set(setup);
      this.step.set('setup');
      this.qrCode.set(await this.account.totpQrCode().catch(() => null));
    });
  }

  protected async activate(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    await this.run(async () => {
      const code = this.form.controls.code.value.replace(/\s+/g, '');
      const result = await this.authApi.activateTotp(code);
      if (result.status !== 200) {
        this.showResultErrors(result);
        return;
      }
      this.form.reset();
      this.setup.set(null);
      this.qrCode.set(null);
      this.status.set(this.translate.instant('portail.account.security.activated'));
      await this.refresh();
      this.codes.set((await this.authApi.recoveryCodes())?.unused_codes ?? null);
    });
  }

  protected async showCodes(): Promise<void> {
    await this.run(async () => {
      const recovery = await this.authApi.recoveryCodes();
      this.codes.set(recovery?.unused_codes ?? null);
    });
  }

  protected async regenerate(): Promise<void> {
    await this.run(async () => {
      const recovery: RecoveryCodesInfo | null = await this.authApi.regenerateRecoveryCodes();
      if (recovery) {
        this.codes.set(recovery.unused_codes);
        this.status.set(this.translate.instant('portail.account.security.regenerated'));
        await this.refresh();
      }
    });
  }

  protected async disable(): Promise<void> {
    await this.run(async () => {
      const result = await this.authApi.deactivateTotp();
      if (result.status !== 200) {
        this.showResultErrors(result);
        return;
      }
      this.confirmingDisable.set(false);
      this.codes.set(null);
      this.status.set(this.translate.instant('portail.account.security.disabled'));
      await this.refresh();
    });
  }

  protected copySecret(secret: string): void {
    void this.document.defaultView?.navigator.clipboard?.writeText(secret).then(
      () => this.status.set(this.translate.instant('portail.account.security.copied')),
      () => undefined,
    );
  }

  protected goToStepUp(): void {
    const next = this.route.snapshot.queryParamMap.get('next');
    void this.router.navigate(['/compte/double-authentification'], {
      queryParams: next ? { next } : {},
    });
  }

  private async refresh(): Promise<void> {
    const authenticators = await this.authApi.authenticators();
    this.authenticators.set(authenticators);
    if (this.step() !== 'setup' || authenticators.some((item) => item.type === 'totp')) {
      this.step.set(authenticators.some((item) => item.type === 'totp') ? 'enabled' : 'disabled');
    }
    await this.meStore.load().catch(() => undefined);
  }

  private showResultErrors(result: AuthResult): void {
    const unplaced = applyAuthErrors(this.translate, this.form, result.errors);
    this.errors.set(
      unplaced.length || result.errors.length
        ? unplaced
        : [codeMessage(this.translate, fallbackCode(result.status))],
    );
  }

  private async run(action: () => Promise<void>): Promise<void> {
    this.errors.set([]);
    this.status.set('');
    this.busy.set(true);
    try {
      await action();
    } catch (error) {
      this.errors.set([apiErrorMessage(this.translate, error)]);
    } finally {
      this.busy.set(false);
    }
  }
}
