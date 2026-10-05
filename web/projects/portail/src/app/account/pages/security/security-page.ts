import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { PageHeader } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { EmailsSection } from './emails-section';
import { MfaSection } from './mfa-section';
import { PasswordSection } from './password-section';

/**
 * Sécurité du compte (plan L1 §10.2) : double authentification, mot de passe, adresses
 * e-mail. Cible de `mfa_enrollment_required` (avec `next`) : la gestion exige la 2FA.
 */
@Component({
  selector: 'portail-security-page',
  imports: [TranslatePipe, PageHeader, MfaSection, PasswordSection, EmailsSection],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <gc-page-header [heading]="'portail.account.security.title' | translate" />
    @if (fromManagement) {
      <p class="notice" role="status">
        {{ 'shared.errors.mfa_enrollment_required' | translate }}
      </p>
    }
    <portail-mfa-section />
    <portail-password-section />
    <portail-emails-section />
  `,
  styleUrl: './security.scss',
})
export class SecurityPage {
  /** Arrivée depuis la gestion (`next`) : rappel de l'obligation de 2FA. */
  protected readonly fromManagement = inject(ActivatedRoute).snapshot.queryParamMap.has('next');
}
