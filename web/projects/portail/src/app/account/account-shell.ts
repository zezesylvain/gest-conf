import {
  ChangeDetectionStrategy,
  Component,
  DOCUMENT,
  effect,
  inject,
  OnDestroy,
  OnInit,
  signal,
} from '@angular/core';
import { Meta } from '@angular/platform-browser';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import {
  AuthApi,
  LanguageService,
  MeStore,
  ReauthenticationDialog,
  ReauthenticationPrompt,
  SessionStore,
} from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { ensureThemeStylesheet } from './theme';

/**
 * Coque de l'espace /compte : rendu dans le navigateur seulement (RenderMode.Client),
 * `noindex`, thème Material chargé à la demande, navigation et déconnexion. Après la
 * connexion, l'interface adopte la langue du compte ; un changement de langue ensuite
 * est enregistré dans le compte (plan L1 §10.4). Fournit la fenêtre de réauthentification
 * (`ReauthenticationPrompt`) aux pages de l'espace compte.
 */
@Component({
  selector: 'portail-account-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (session.authenticated()) {
      <nav class="account-nav" [attr.aria-label]="'portail.account.nav.label' | translate">
        <a
          routerLink="/compte"
          routerLinkActive="active"
          [routerLinkActiveOptions]="{ exact: true }"
        >
          {{ 'portail.account.nav.home' | translate }}
        </a>
        <a routerLink="/compte/profil" routerLinkActive="active">
          {{ 'portail.account.nav.profile' | translate }}
        </a>
        <a routerLink="/compte/securite" routerLinkActive="active">
          {{ 'portail.account.nav.security' | translate }}
        </a>
        <button type="button" class="link-button" (click)="logout()" [disabled]="loggingOut()">
          {{ 'portail.account.nav.logout' | translate }}
        </button>
      </nav>
    }
    <router-outlet />
  `,
  styles: `
    .account-nav {
      display: flex;
      flex-wrap: wrap;
      gap: 1rem;
      align-items: center;
      margin-bottom: 1.5rem;
      padding-bottom: 0.75rem;
      border-bottom: 1px solid var(--gc-border);
    }
    a {
      color: var(--gc-primary);
    }
    a.active {
      font-weight: 700;
    }
    .link-button {
      margin-left: auto;
      font: inherit;
      color: var(--gc-primary);
      background: none;
      border: 1px solid var(--gc-primary);
      border-radius: 0.25rem;
      padding: 0.25rem 0.75rem;
      cursor: pointer;
    }
  `,
})
export class AccountShell implements OnInit, OnDestroy {
  protected readonly session = inject(SessionStore);
  private readonly authApi = inject(AuthApi);
  private readonly meStore = inject(MeStore);
  private readonly language = inject(LanguageService);
  private readonly meta = inject(Meta);
  private readonly document = inject(DOCUMENT);
  private readonly reauthenticationDialog = inject(ReauthenticationDialog);
  private readonly reauthentication = inject(ReauthenticationPrompt);
  private unregisterReauthentication: (() => void) | null = null;

  protected readonly loggingOut = signal(false);
  private languageAdopted = false;

  constructor() {
    // Langue : adoption de celle du compte au chargement de /me, puis enregistrement
    // de tout changement fait avec le sélecteur de langue.
    effect(() => {
      const me = this.meStore.me();
      const current = this.language.current();
      if (!me) {
        this.languageAdopted = false;
        return;
      }
      if (!this.languageAdopted) {
        this.languageAdopted = true;
        if (me.locale !== current) {
          void this.language.use(me.locale);
        }
      } else if (me.locale !== current) {
        void this.meStore.updateLocale(current).catch(() => undefined);
      }
    });
    // Compte chargé dès que la session est établie (connexion, retour sur /compte).
    effect(() => {
      if (this.session.authenticated() && !this.meStore.loaded()) {
        void this.meStore.load().catch(() => undefined);
      }
    });
  }

  ngOnInit(): void {
    ensureThemeStylesheet(this.document);
    this.meta.updateTag({ name: 'robots', content: 'noindex, nofollow' });
    this.unregisterReauthentication = this.reauthentication.register(() =>
      this.reauthenticationDialog.open(),
    );
  }

  ngOnDestroy(): void {
    this.meta.removeTag('name="robots"');
    this.unregisterReauthentication?.();
  }

  /** Déconnexion, puis rechargement complet pour vider l'état des applications (§4.3). */
  protected async logout(): Promise<void> {
    this.loggingOut.set(true);
    try {
      await this.authApi.logout();
    } finally {
      this.meStore.clear();
      this.document.defaultView?.location.assign('/compte/connexion');
    }
  }
}
