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
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import {
  apiErrorMessage,
  ErrorSummary,
  fieldErrorMessage,
  focusFirstInvalid,
  GcApiError,
  MeStore,
  PageHeader,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { AccountService } from '../account.service';

/**
 * Mes données (plan L1 §4.9, RG-18) : export JSON de toutes ses données (sans secret) et
 * anonymisation immédiate et définitive. Les deux exigent une réauthentification récente
 * (la fenêtre s'ouvre d'elle-même) ; l'anonymisation demande en plus de saisir l'adresse
 * du compte, et elle est refusée tant que des rôles de gestion sont actifs.
 */
@Component({
  selector: 'portail-my-data-page',
  imports: [
    ReactiveFormsModule,
    TranslatePipe,
    MatButtonModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <gc-page-header [heading]="'portail.account.myData.title' | translate" />
    <div aria-live="polite">
      @if (status()) {
        <p class="notice" role="status">{{ status() }}</p>
      }
    </div>
    <gc-error-summary [messages]="errors()" />

    <section class="card" aria-labelledby="export-title">
      <h2 id="export-title">{{ 'portail.account.myData.exportTitle' | translate }}</h2>
      <p>{{ 'portail.account.myData.exportLead' | translate }}</p>
      <button mat-flat-button type="button" (click)="download()" [disabled]="busy()">
        {{ 'portail.account.myData.download' | translate }}
      </button>
    </section>

    <section class="card danger" aria-labelledby="anonymize-title">
      <h2 id="anonymize-title">{{ 'portail.account.myData.anonymizeTitle' | translate }}</h2>
      <p>{{ 'portail.account.myData.anonymizeLead' | translate }}</p>
      <p>{{ 'portail.account.myData.anonymizeKept' | translate }}</p>
      <form [formGroup]="form" (ngSubmit)="anonymize()" novalidate>
        <mat-form-field appearance="outline">
          <mat-label>{{ 'portail.account.myData.confirmation' | translate }}</mat-label>
          <input matInput type="email" formControlName="confirmation" autocomplete="off" required />
          <mat-hint>{{
            'portail.account.myData.confirmationHint' | translate: { email: email() }
          }}</mat-hint>
          <mat-error>{{ error() }}</mat-error>
        </mat-form-field>
        <mat-checkbox formControlName="understood" required>
          {{ 'portail.account.myData.understood' | translate }}
        </mat-checkbox>
        <div class="actions">
          <button mat-flat-button type="submit" [disabled]="busy()">
            {{ 'portail.account.myData.anonymize' | translate }}
          </button>
        </div>
      </form>
    </section>
  `,
  styleUrl: './account-form.scss',
  styles: `
    :host {
      max-width: 44rem;
    }
    .card {
      margin: 0 0 1.5rem;
      padding: 1rem 1.25rem;
      border: 1px solid var(--gc-border);
      border-radius: 0.5rem;
    }
    .danger {
      border-color: var(--gc-danger);
    }
    h2 {
      margin: 0 0 0.5rem;
      font-size: 1.2rem;
    }
  `,
})
export class MyDataPage {
  private readonly account = inject(AccountService);
  private readonly meStore = inject(MeStore);
  private readonly translate = inject(TranslateService);
  private readonly document = inject(DOCUMENT);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  protected readonly email = () => this.meStore.me()?.email ?? '';
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  protected readonly form = inject(NonNullableFormBuilder).group({
    confirmation: ['', [Validators.required, Validators.email]],
    understood: [false, Validators.requiredTrue],
  });

  protected error(): string {
    return fieldErrorMessage(this.translate, this.form.controls.confirmation);
  }

  protected async download(): Promise<void> {
    this.errors.set([]);
    this.status.set('');
    this.busy.set(true);
    try {
      const data = await this.account.exportData();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const view = this.document.defaultView;
      const url = view?.URL.createObjectURL(blob);
      if (url) {
        const link = this.document.createElement('a');
        link.href = url;
        link.download = 'gestconf-mes-donnees.json';
        link.click();
        view?.URL.revokeObjectURL(url);
      }
      this.status.set(this.translate.instant('portail.account.myData.downloaded'));
    } catch (error) {
      this.errors.set([apiErrorMessage(this.translate, error)]);
    } finally {
      this.busy.set(false);
    }
  }

  protected async anonymize(): Promise<void> {
    this.errors.set([]);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      focusFirstInvalid(this.host.nativeElement);
      return;
    }
    this.busy.set(true);
    try {
      await this.account.anonymize(this.form.controls.confirmation.value.trim());
      // Session fermée par le serveur : rechargement complet, états vidés.
      this.document.defaultView?.location.assign('/');
    } catch (error) {
      const messages = [apiErrorMessage(this.translate, error)];
      if (error instanceof GcApiError && error.code === 'account_has_active_duties') {
        messages.push(...(error.fields['roles'] ?? []));
      }
      this.errors.set(messages);
      this.busy.set(false);
    }
  }
}
