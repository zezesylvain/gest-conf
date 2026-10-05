import {
  afterNextRender,
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
} from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';
import { AuthApi, LanguageService, LanguageSwitcher, SessionStore } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { PageContext } from './site/public-portal';
import { LanguageLinks, SiteNav } from './site/site-nav';

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
  /** Accueil dans la langue de la page (portail public) ou de l'interface (espace compte). */
  protected readonly homeLink = computed(
    () => `/${this.context.language() ?? this.language.current()}/`,
  );
  private readonly authApi = inject(AuthApi);

  constructor() {
    // État de session lu dans le navigateur seulement, jamais au pré-rendu (plan L1 §10.4).
    afterNextRender(() => {
      if (this.session.state() === 'unknown') {
        void this.authApi.loadSession().catch(() => this.session.clear());
      }
    });
  }
}
