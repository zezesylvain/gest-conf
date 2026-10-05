import { ChangeDetectionStrategy, Component, inject, OnInit, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import {
  apiErrorMessage,
  applyAuthErrors,
  AuthApi,
  AuthResult,
  codeMessage,
  EmailAddressInfo,
  ErrorSummary,
  fallbackCode,
  fieldErrorMessage,
  MeStore,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

/**
 * Adresses e-mail du compte (plan L1 §4.2, §4.3) : ajout, retrait, adresse principale et
 * renvoi du lien de vérification. Toute modification exige une réauthentification
 * récente (fenêtre ouverte d'elle-même). Un compte protégé par la 2FA ne peut pas ajouter
 * d'adresse ici (`add_email_blocked`) : une adresse invitée se rattache par le lien de
 * l'invitation (RG-20).
 */
@Component({
  selector: 'portail-emails-section',
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
    <section class="card" aria-labelledby="emails-title">
      <h2 id="emails-title">{{ 'portail.account.security.emailsTitle' | translate }}</h2>
      <div aria-live="polite">
        @if (status()) {
          <p class="notice" role="status">{{ status() }}</p>
        }
      </div>
      <gc-error-summary [messages]="errors()" />
      <ul class="addresses">
        @for (address of addresses(); track address.email) {
          <li>
            <span>{{ address.email }}</span>
            @if (address.primary) {
              <span class="badge">{{ 'portail.account.security.primary' | translate }}</span>
            }
            <span class="badge">
              {{
                (address.verified
                  ? 'portail.account.security.verified'
                  : 'portail.account.security.unverified'
                ) | translate
              }}
            </span>
            @if (!address.primary) {
              @if (address.verified) {
                <button mat-button type="button" (click)="makePrimary(address)" [disabled]="busy()">
                  {{ 'portail.account.security.makePrimary' | translate }}
                </button>
              } @else {
                <button mat-button type="button" (click)="resend(address)" [disabled]="busy()">
                  {{ 'portail.account.security.resend' | translate }}
                </button>
              }
              <button mat-button type="button" (click)="remove(address)" [disabled]="busy()">
                {{ 'portail.account.security.remove' | translate }}
                <span class="visually-hidden">{{ address.email }}</span>
              </button>
            }
          </li>
        }
      </ul>
      <form [formGroup]="form" (ngSubmit)="add()" novalidate>
        <mat-form-field appearance="outline">
          <mat-label>{{ 'portail.account.security.newEmail' | translate }}</mat-label>
          <input matInput type="email" formControlName="email" autocomplete="email" required />
          <mat-error>{{ error() }}</mat-error>
        </mat-form-field>
        <div class="actions">
          <button mat-stroked-button type="submit" [disabled]="busy()">
            {{ 'portail.account.security.addEmail' | translate }}
          </button>
        </div>
      </form>
    </section>
  `,
  styleUrl: './security.scss',
  styles: `
    .visually-hidden {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip: rect(0 0 0 0);
      white-space: nowrap;
    }
  `,
})
export class EmailsSection implements OnInit {
  private readonly authApi = inject(AuthApi);
  private readonly meStore = inject(MeStore);
  private readonly translate = inject(TranslateService);

  protected readonly addresses = signal<EmailAddressInfo[]>([]);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  protected readonly form = inject(NonNullableFormBuilder).group({
    email: ['', [Validators.required, Validators.email]],
  });

  async ngOnInit(): Promise<void> {
    await this.run(async () => this.addresses.set(await this.authApi.emailAddresses()));
  }

  protected error(): string {
    return fieldErrorMessage(this.translate, this.form.controls.email);
  }

  protected async add(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    await this.run(async () => {
      const result = await this.authApi.addEmail(this.form.controls.email.value.trim());
      if (this.applyResult(result, 'portail.account.security.added', true)) {
        this.form.reset();
      }
    });
  }

  protected async remove(address: EmailAddressInfo): Promise<void> {
    await this.run(async () => {
      this.applyResult(
        await this.authApi.removeEmail(address.email),
        'portail.account.security.removed',
      );
    });
  }

  protected async makePrimary(address: EmailAddressInfo): Promise<void> {
    await this.run(async () => {
      const result = await this.authApi.makePrimaryEmail(address.email);
      if (this.applyResult(result, 'portail.account.security.primaryChanged')) {
        await this.meStore.load().catch(() => undefined);
      }
    });
  }

  protected async resend(address: EmailAddressInfo): Promise<void> {
    await this.run(async () => {
      const result = await this.authApi.resendEmailVerification(address.email);
      if (result.status === 403 || result.status === 429) {
        // Un lien est parti il y a moins de 3 minutes (limite d'allauth).
        this.errors.set([this.translate.instant('portail.account.security.resendTooSoon')]);
        return;
      }
      this.applyResult(result, 'portail.account.security.resent');
    });
  }

  /** Succès : liste à jour et message ; échec : erreurs. Renvoie vrai en cas de succès. */
  private applyResult(result: AuthResult, successKey: string, onForm = false): boolean {
    if (result.status === 200) {
      if (Array.isArray(result.data)) {
        this.addresses.set(result.data as EmailAddressInfo[]);
      }
      this.status.set(this.translate.instant(successKey));
      return true;
    }
    // Seul l'ajout se rapporte au champ du formulaire ; les autres erreurs vont au résumé.
    const errors = onForm
      ? result.errors
      : result.errors.map(({ code, message }) => ({ code, message }));
    const unplaced = applyAuthErrors(this.translate, this.form, errors);
    this.errors.set(
      unplaced.length || errors.length
        ? unplaced
        : [codeMessage(this.translate, fallbackCode(result.status))],
    );
    return false;
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
