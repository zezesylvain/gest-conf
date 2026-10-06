import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DOCUMENT,
  effect,
  EnvironmentInjector,
  inject,
  OnDestroy,
  OnInit,
  signal,
} from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';
import {
  AuthApi,
  LanguageService,
  LanguageSwitcher,
  MeStore,
  ReauthenticationDialog,
  ReauthenticationPrompt,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { OfflineCheckinStore } from './core/checkin-offline';
import { NavigationStore } from './core/navigation-store';
import { ContextHelp } from './help/context-help';
import { ScreenSearch } from './layout/screen-search';

/**
 * Coque de la gestion : en-tête (recherche d'écran, compte, langue, déconnexion), lien
 * d'évitement, aide contextuelle « ? » (montée une fois, plan L2 §2.3). La langue
 * du compte est adoptée au démarrage ; un changement est enregistré dans le compte. Fournit
 * la fenêtre de réauthentification (rejouée une fois, plan L1 §10.1).
 */
@Component({
  selector: 'gestion-root',
  imports: [RouterOutlet, RouterLink, TranslatePipe, LanguageSwitcher, ScreenSearch, ContextHelp],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App implements OnInit, OnDestroy {
  private readonly authApi = inject(AuthApi);
  private readonly language = inject(LanguageService);
  private readonly document = inject(DOCUMENT);
  private readonly reauthentication = inject(ReauthenticationPrompt);
  private readonly reauthenticationDialog = inject(ReauthenticationDialog);
  private readonly offline = inject(OfflineCheckinStore);
  private readonly injector = inject(EnvironmentInjector);
  private readonly translate = inject(TranslateService);
  private unregister: (() => void) | null = null;
  protected readonly meStore = inject(MeStore);
  protected readonly navigation = inject(NavigationStore);
  protected readonly loggingOut = signal(false);
  protected readonly email = computed(() => this.meStore.me()?.email ?? '');

  private languageAdopted = false;

  constructor() {
    // Langue du compte adoptée au chargement de /me, puis tout changement fait avec le
    // sélecteur est enregistré dans le compte (même logique que l'espace compte du portail).
    effect(() => {
      const me = this.meStore.me();
      const current = this.language.current();
      if (!me) {
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
  }

  ngOnInit(): void {
    this.unregister = this.reauthentication.register(() => this.reauthenticationDialog.open());
  }

  ngOnDestroy(): void {
    this.unregister?.();
  }

  /**
   * Déconnexion, puis connexion du portail (page entière : état des applications vidé). La
   * liste de pointage et la file de l'accueil sont effacées (plan L7, K5 : le jeton du badge
   * est un titre d'accès), après avertissement s'il reste des pointages non synchronisés.
   */
  protected async logout(): Promise<void> {
    const pending = await this.offline.pending();
    if (pending > 0) {
      const { confirmLogout } = await import('./core/logout-warning');
      const confirmed = await confirmLogout(this.injector, {
        title: this.translate.instant('gestion.logoutPending.title'),
        message: this.translate.instant('gestion.logoutPending.message', { count: pending }),
        confirmLabel: this.translate.instant('gestion.logoutPending.confirm'),
      });
      if (!confirmed) {
        return;
      }
    }
    this.loggingOut.set(true);
    try {
      await this.offline.clear();
      await this.authApi.logout();
    } finally {
      this.document.defaultView?.location.assign('/compte/connexion');
    }
  }
}
