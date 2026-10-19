import {
  afterNextRender,
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  PendingTasks,
  signal,
  viewChild,
  ViewContainerRef,
} from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';
import {
  AuthApi,
  LanguageService,
  LanguageSwitcher,
  PublicEdition,
  SessionStore,
} from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { brandName } from './site/brand';
import { PortalData } from './site/portal-data';
import { PageContext } from './site/public-portal';
import { LanguageLinks, SiteNav } from './site/site-nav';
import { localized, SiteLanguage } from './site/site-pages';

@Component({
  selector: 'portail-root',
  imports: [RouterOutlet, RouterLink, TranslatePipe, LanguageSwitcher, LanguageLinks, SiteNav],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  protected readonly session = inject(SessionStore);
  protected readonly context = inject(PageContext);
  private readonly language = inject(LanguageService);
  /** Langue de la page (portail public) ou de l'interface (espace compte). */
  private readonly lang = computed<SiteLanguage>(
    () => this.context.language() ?? (this.language.current() === 'en' ? 'en' : 'fr'),
  );
  /** Accueil dans la langue de la page (portail public) ou de l'interface (espace compte). */
  protected readonly homeLink = computed(() => `/${this.lang()}/`);
  /** Édition courante, pour la marque et le pied de page (T4, V6) ; nulle si injoignable. */
  private readonly edition = signal<PublicEdition | null>(null);
  protected readonly brand = computed(() => {
    const edition = this.edition();
    return edition ? brandName(edition.code, edition.year) : '';
  });
  protected readonly city = computed(() => this.edition()?.city ?? '');
  protected readonly editionTitle = computed(() => {
    const edition = this.edition();
    return edition ? localized(edition, 'title', this.lang()) : '';
  });
  private readonly authApi = inject(AuthApi);
  private readonly portal = inject(PortalData);
  private readonly bannerHost = viewChild.required('banner', { read: ViewContainerRef });

  constructor() {
    // Lue au pré-rendu (la marque est dans la page) et partagée avec les pages du portail.
    void inject(PendingTasks).run(async () => {
      try {
        this.edition.set((await this.portal.site()).edition);
      } catch {
        // Aucune édition publiée ou API injoignable : nom de l'application.
      }
    });
    // État de session lu dans le navigateur seulement, jamais au pré-rendu (plan L1 §10.4).
    afterNextRender(() => {
      if (this.session.state() === 'unknown') {
        void this.authApi.loadSession().catch(() => this.session.clear());
      }
      void this.showBanner();
    });
  }

  /**
   * Bandeau de dernière minute (plan L8, N10) : module chargé à la demande après le premier
   * rendu, dans le navigateur seulement. Ni `@defer` (son moteur alourdirait le bundle
   * initial) ni pré-rendu : le bandeau se lit à chaque visite.
   */
  private async showBanner(): Promise<void> {
    try {
      const { SiteBanner } = await import('./site/banner/site-banner');
      this.bannerHost().createComponent(SiteBanner);
    } catch {
      // Module introuvable (déploiement en cours) : la page reste utilisable sans bandeau.
    }
  }
}
