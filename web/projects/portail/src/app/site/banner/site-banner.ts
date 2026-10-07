import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  OnInit,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { LanguageService, PublicBannerItem } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { CommunityData } from '../community/community-data';
import { newsAnchor } from '../community/community-support';
import { PageContext } from '../public-portal';
import { localized, sitePagePath, SiteLanguage } from '../site-pages';

const DISMISSED = 'gc-banner-dismissed';

/**
 * Bandeau de dernière minute (plan L8, N10) : lu **dans le navigateur** à chaque visite
 * (`GET /v1/public/portal/banner`, cache de 60 s), jamais au pré-rendu ; chargé à la demande
 * (`import()` de la coque) pour ne pas alourdir le bundle initial. Annoncé aux lecteurs
 * d'écran (`role="status"`), refermable pour la visite (stockage de session, protégé :
 * navigation privée).
 */
@Component({
  selector: 'portail-site-banner',
  imports: [RouterLink, TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (banner(); as item) {
      <div class="site-banner" role="status">
        <p>
          <strong>{{ text(item, 'title') }}</strong>
          @if (text(item, 'message')) {
            — {{ text(item, 'message') }}
          }
          @if (item.news) {
            <a [routerLink]="newsPath()" [fragment]="anchor(item)">{{
              'portail.community.readMore' | translate
            }}</a>
          }
        </p>
        <button type="button" (click)="dismiss(item)">
          {{ 'portail.community.dismiss' | translate }}
        </button>
      </div>
    }
  `,
  styles: `
    .site-banner {
      display: flex;
      gap: 1rem;
      align-items: center;
      justify-content: space-between;
      padding: 0.5rem 1rem;
      background: var(--gc-warning);
      color: var(--gc-text);
    }
    .site-banner p {
      margin: 0;
    }
    button {
      font: inherit;
      flex: none;
    }
  `,
})
export class SiteBanner implements OnInit {
  private readonly community = inject(CommunityData);
  private readonly context = inject(PageContext);
  private readonly languages = inject(LanguageService);

  protected readonly banner = signal<PublicBannerItem | null>(null);
  private readonly language = computed<SiteLanguage>(
    () => (this.context.language() ?? this.languages.current()) as SiteLanguage,
  );
  protected readonly newsPath = computed(() => sitePagePath('news', this.language()));

  async ngOnInit(): Promise<void> {
    try {
      const { banner } = await this.community.banner();
      if (banner && !this.dismissed(banner.id)) {
        this.banner.set(banner);
      }
    } catch {
      // Le bandeau est un complément : une erreur ne gêne pas la page.
      this.banner.set(null);
    }
  }

  protected text(item: PublicBannerItem, field: string): string {
    return localized(item, field, this.language());
  }

  protected anchor(item: PublicBannerItem): string {
    return newsAnchor(item.id);
  }

  protected dismiss(item: PublicBannerItem): void {
    this.banner.set(null);
    try {
      sessionStorage.setItem(DISMISSED, String(item.id));
    } catch {
      // Stockage indisponible : refermé pour cette page seulement.
    }
  }

  private dismissed(id: number): boolean {
    try {
      return sessionStorage.getItem(DISMISSED) === String(id);
    } catch {
      return false;
    }
  }
}
