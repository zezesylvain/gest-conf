import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  OnInit,
  signal,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import {
  apiErrorMessage,
  ConsentRecord,
  ConsentState,
  ErrorSummary,
  formatInZone,
  LanguageService,
  PageHeader,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { AccountService } from '../account.service';
import { PrivacyNotice } from '../ui/privacy-notice';

/**
 * Confidentialité (plan L1 §4.8, D15) : notice d'information, consentements facultatifs
 * (désactivés par défaut, retirables à tout moment ; chaque choix ajoute une ligne à
 * l'historique) et historique de ses choix.
 */
@Component({
  selector: 'portail-privacy-page',
  imports: [TranslatePipe, MatButtonModule, ErrorSummary, PageHeader, PrivacyNotice],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <gc-page-header [heading]="'portail.account.privacy.title' | translate" />
    <portail-privacy-notice [open]="true" />
    <div aria-live="polite">
      @if (status()) {
        <p class="notice" role="status">{{ status() }}</p>
      }
    </div>
    <gc-error-summary [messages]="errors()" />

    @if (directory(); as state) {
      <section class="card" aria-labelledby="directory-title">
        <h2 id="directory-title">{{ 'portail.account.privacy.directoryTitle' | translate }}</h2>
        <p>{{ 'portail.account.privacy.directoryLead' | translate }}</p>
        <p>
          {{
            (state.granted
              ? 'portail.account.privacy.granted'
              : 'portail.account.privacy.notGranted'
            ) | translate
          }}
        </p>
        <button mat-stroked-button type="button" (click)="toggle(state)" [disabled]="busy()">
          {{
            (state.granted ? 'portail.account.privacy.withdraw' : 'portail.account.privacy.grant')
              | translate
          }}
        </button>
      </section>
    }

    @if (history().length) {
      <section class="card" aria-labelledby="history-title">
        <h2 id="history-title">{{ 'portail.account.privacy.historyTitle' | translate }}</h2>
        <ul>
          @for (item of history(); track $index) {
            <li>
              {{ date(item.recorded_at) }} —
              {{ 'portail.account.privacy.kinds.' + item.kind | translate }} :
              {{
                (item.granted ? 'portail.account.privacy.yes' : 'portail.account.privacy.no')
                  | translate
              }}
              <span class="hint">({{ item.text_version }})</span>
            </li>
          }
        </ul>
      </section>
    }
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
    h2 {
      margin: 0 0 0.5rem;
      font-size: 1.2rem;
    }
  `,
})
export class PrivacyPage implements OnInit {
  private readonly account = inject(AccountService);
  private readonly translate = inject(TranslateService);
  private readonly language = inject(LanguageService);

  protected readonly states = signal<ConsentState[]>([]);
  protected readonly history = signal<ConsentRecord[]>([]);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  protected readonly directory = computed(() =>
    this.states().find((state) => state.kind === 'directory_listing'),
  );

  async ngOnInit(): Promise<void> {
    await this.load();
  }

  protected date(value: string): string {
    return formatInZone(value, undefined, this.language.current());
  }

  protected async toggle(state: ConsentState): Promise<void> {
    this.errors.set([]);
    this.status.set('');
    this.busy.set(true);
    try {
      await this.account.setConsent(state.kind, !state.granted);
      this.status.set(this.translate.instant('portail.account.privacy.saved'));
      await this.load();
    } catch (error) {
      this.errors.set([apiErrorMessage(this.translate, error)]);
    } finally {
      this.busy.set(false);
    }
  }

  private async load(): Promise<void> {
    try {
      const consents = await this.account.consents();
      this.states.set(consents.states);
      this.history.set(consents.history);
    } catch (error) {
      this.errors.set([apiErrorMessage(this.translate, error)]);
    }
  }
}
