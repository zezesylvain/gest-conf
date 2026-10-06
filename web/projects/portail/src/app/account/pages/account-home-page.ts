import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { RouterLink } from '@angular/router';
import { apiErrorMessage, LanguageService, MeStore, PageHeader } from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { AccountService } from '../account.service';
import { PrivacyNotice } from '../ui/privacy-notice';

/**
 * Accueil du compte et première connexion (plan L1 §4.3) : prise de connaissance de la
 * notice d'information et invitation à compléter le profil. Pas de blocage global côté
 * serveur : chaque lot vérifie ses propres prérequis (L3 : profil complet pour soumettre).
 * Éditions et rôles (accès à la gestion), invitations en attente, état de la double
 * authentification (obligatoire pour la gestion).
 */
@Component({
  selector: 'portail-account-home-page',
  imports: [RouterLink, TranslatePipe, MatButtonModule, PageHeader, PrivacyNotice],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <gc-page-header [heading]="'portail.account.home.title' | translate" />

    @if (meStore.me(); as me) {
      <p>{{ 'portail.account.home.signedInAs' | translate: { email: me.email } }}</p>

      @if (me.privacy_notice_pending) {
        <section class="card" aria-labelledby="notice-title">
          <h2 id="notice-title">{{ 'portail.account.home.noticeTitle' | translate }}</h2>
          <p>{{ 'portail.account.home.noticeLead' | translate }}</p>
          <portail-privacy-notice [open]="true" />
          @if (error()) {
            <p class="error" role="alert">{{ error() }}</p>
          }
          <button mat-flat-button type="button" (click)="acknowledge()" [disabled]="saving()">
            {{ 'portail.account.home.acknowledge' | translate }}
          </button>
        </section>
      }

      @if (!me.profile_complete) {
        <section class="card" aria-labelledby="profile-title">
          <h2 id="profile-title">{{ 'portail.account.home.profileTitle' | translate }}</h2>
          <p>{{ 'portail.account.home.profileLead' | translate }}</p>
          <a mat-stroked-button routerLink="/compte/profil">
            {{ 'portail.account.home.completeProfile' | translate }}
          </a>
        </section>
      } @else {
        <p>
          <a routerLink="/compte/profil">{{ 'portail.account.home.editProfile' | translate }}</a>
        </p>
      }

      <p>
        <a routerLink="/compte/soumissions">{{ 'portail.account.nav.submissions' | translate }}</a>
      </p>

      @if (me.pending_invitations.length) {
        <section class="card" aria-labelledby="pending-title">
          <h2 id="pending-title">{{ 'portail.account.home.pendingTitle' | translate }}</h2>
          <ul>
            @for (item of me.pending_invitations; track $index) {
              <li>
                {{ item.edition_code }} —
                {{
                  language.current() === 'en' && item.edition_title_en
                    ? item.edition_title_en
                    : item.edition_title_fr
                }}
                : {{ 'portail.account.invitation.roles.' + item.role | translate }}
              </li>
            }
          </ul>
          <p>{{ 'portail.account.home.pendingHint' | translate }}</p>
        </section>
      }

      @if (me.editions.length) {
        <section class="card" aria-labelledby="editions-title">
          <h2 id="editions-title">{{ 'portail.account.home.editionsTitle' | translate }}</h2>
          <ul>
            @for (edition of me.editions; track edition.id) {
              <li>
                <strong>{{ edition.code }}</strong> —
                @for (item of edition.roles; track $index) {
                  <span class="role">{{
                    'portail.account.invitation.roles.' + item.role | translate
                  }}</span>
                }
                @if (edition.capabilities.length) {
                  <a [href]="'/gestion/editions/' + edition.id">{{
                    'portail.account.home.open' | translate
                  }}</a>
                }
              </li>
            }
          </ul>
        </section>
      }

      <p>
        {{
          (me.mfa_enabled ? 'portail.account.home.mfaEnabled' : 'portail.account.home.mfaDisabled')
            | translate
        }}
        <a routerLink="/compte/securite">{{ 'portail.account.home.security' | translate }}</a>
      </p>

      <p>
        <a href="/gestion/">{{ 'portail.account.home.management' | translate }}</a>
      </p>
    } @else {
      <p role="status">{{ 'portail.account.home.loading' | translate }}</p>
    }
  `,
  styles: `
    .card {
      margin: 0 0 1.5rem;
      padding: 1rem 1.25rem;
      border: 1px solid var(--gc-border);
      border-radius: 0.5rem;
    }
    h2 {
      margin: 0 0 0.5rem;
      font-size: 1.25rem;
    }
    .error {
      color: var(--gc-danger);
    }
    a {
      color: var(--gc-primary);
    }
    .role {
      margin-right: 0.5rem;
    }
  `,
})
export class AccountHomePage {
  protected readonly meStore = inject(MeStore);
  protected readonly language = inject(LanguageService);
  private readonly account = inject(AccountService);
  private readonly translate = inject(TranslateService);

  protected readonly saving = signal(false);
  protected readonly error = signal('');

  protected async acknowledge(): Promise<void> {
    this.saving.set(true);
    this.error.set('');
    try {
      await this.account.acknowledgePrivacyNotice();
      await this.meStore.load();
    } catch (error) {
      this.error.set(apiErrorMessage(this.translate, error));
    } finally {
      this.saving.set(false);
    }
  }
}
