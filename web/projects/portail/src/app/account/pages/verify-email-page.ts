import {
  ChangeDetectionStrategy,
  Component,
  DOCUMENT,
  inject,
  OnInit,
  signal,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { Router, RouterLink } from '@angular/router';
import { apiErrorMessage, AuthApi, codeMessage, PageHeader } from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { takeFragmentKey } from '../fragment-key';

type VerifyState = 'sent' | 'verifying' | 'verified' | 'failed';

/**
 * Vérification de l'adresse (plan L1 §4.3) :
 * - avec une clé dans le fragment (lien reçu par e-mail) : vérification, puis invitation à
 *   se connecter (allauth ne connecte pas automatiquement) ;
 * - sans clé : écran « consultez vos e-mails ». Le renvoi du lien passe par une nouvelle
 *   connexion (en mode lien, allauth n'offre pas d'autre renvoi).
 */
@Component({
  selector: 'portail-verify-email-page',
  imports: [RouterLink, TranslatePipe, MatButtonModule, MatProgressSpinnerModule, PageHeader],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './verify-email-page.html',
  styleUrl: './account-form.scss',
})
export class VerifyEmailPage implements OnInit {
  private readonly authApi = inject(AuthApi);
  private readonly translate = inject(TranslateService);
  private readonly document = inject(DOCUMENT);
  private readonly router = inject(Router);

  protected readonly state = signal<VerifyState>('sent');
  protected readonly message = signal('');
  protected readonly email = signal<string>('');

  ngOnInit(): void {
    const navigationState = this.router.lastSuccessfulNavigation()?.extras.state as
      { email?: string } | undefined;
    this.email.set(navigationState?.email ?? '');
    const key = takeFragmentKey(this.document);
    if (key) {
      void this.verify(key);
    }
  }

  private async verify(key: string): Promise<void> {
    this.state.set('verifying');
    try {
      const result = await this.authApi.verifyEmail(key);
      if (result.errors.length) {
        this.state.set('failed');
        this.message.set(
          codeMessage(this.translate, result.errors[0].code, result.errors[0].message),
        );
      } else {
        this.state.set('verified');
      }
    } catch (error) {
      this.state.set('failed');
      this.message.set(apiErrorMessage(this.translate, error));
    }
  }
}
