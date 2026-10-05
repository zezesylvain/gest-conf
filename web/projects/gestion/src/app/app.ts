import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DOCUMENT,
  effect,
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
import { TranslatePipe } from '@ngx-translate/core';

/**
 * Coque de la gestion : en-tête (compte, langue, déconnexion), lien d'évitement. La langue
 * du compte est adoptée au démarrage ; un changement est enregistré dans le compte. Fournit
 * la fenêtre de réauthentification (rejouée une fois, plan L1 §10.1).
 */
@Component({
  selector: 'gestion-root',
  imports: [RouterOutlet, RouterLink, TranslatePipe, LanguageSwitcher],
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
  private unregister: (() => void) | null = null;
  protected readonly meStore = inject(MeStore);
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

  /** Déconnexion, puis connexion du portail (page entière : état des applications vidé). */
  protected async logout(): Promise<void> {
    this.loggingOut.set(true);
    try {
      await this.authApi.logout();
    } finally {
      this.document.defaultView?.location.assign('/compte/connexion');
    }
  }
}
