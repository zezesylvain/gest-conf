import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';

/** Version du texte affiché : doit correspondre à apps/accounts/consents.py côté serveur. */
export const PRIVACY_NOTICE_VERSION = '2026-10-v0';

/**
 * Notice d'information (plan L1 §4.8, D15). Texte provisoire « v0 » : le texte définitif
 * (Q14) bloque l'ouverture de l'appel (L3), pas L1. Versionné ici, en FR et EN.
 */
@Component({
  selector: 'portail-privacy-notice',
  imports: [TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <details class="notice-box" [open]="open()">
      <summary>{{ 'portail.account.notice.summary' | translate }}</summary>
      <div class="notice-body">
        <p>{{ 'portail.account.notice.controller' | translate }}</p>
        <p>{{ 'portail.account.notice.purpose' | translate }}</p>
        <p>{{ 'portail.account.notice.retention' | translate }}</p>
        <p>{{ 'portail.account.notice.rights' | translate }}</p>
        <p class="version">
          {{ 'portail.account.notice.version' | translate: { version: version } }}
        </p>
      </div>
    </details>
  `,
  styles: `
    .notice-box {
      margin: 0 0 1rem;
      padding: 0.75rem 1rem;
      border: 1px solid var(--gc-border);
      border-radius: 0.25rem;
      background: var(--gc-surface-muted);
    }
    summary {
      cursor: pointer;
      font-weight: 600;
    }
    .notice-body p {
      margin: 0.5rem 0 0;
    }
    .version {
      color: var(--gc-muted);
      font-size: 0.875rem;
    }
  `,
})
export class PrivacyNotice {
  readonly open = input(false);
  protected readonly version = PRIVACY_NOTICE_VERSION;
}
