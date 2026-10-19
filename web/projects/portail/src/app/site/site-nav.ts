import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { MenuLocation, PublicMenuItem } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { PageContext, PublicMenus } from './public-portal';
import { SITE_LANGUAGES, SITE_PAGES, sitePagePath, SiteLanguage } from './site-pages';

/** Navigation codée : repli tant que le menu géré est vide ou injoignable (pas de vide). */
const FALLBACK_HEADER = ['call', 'dates', 'tracks', 'committees', 'program', 'registration'];

interface NavLink {
  label: string;
  href: string;
  internal: boolean;
  newTab: boolean;
}

/**
 * Menu géré (en-tête ou pied de page, plan L2 §2.2) dans la langue de l'adresse, avec
 * repli sur la navigation codée tant que le menu est vide.
 */
@Component({
  selector: 'portail-site-nav',
  imports: [RouterLink, TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (links().length) {
      <nav [attr.aria-label]="'portail.site.nav.' + location() | translate">
        <ul>
          @for (link of links(); track link.href) {
            <li>
              @if (link.internal) {
                <a
                  [routerLink]="link.href"
                  [attr.aria-current]="
                    link.href === context.paths()?.[context.language()!] ? 'page' : null
                  "
                  >{{ link.label }}</a
                >
              } @else {
                <a
                  [href]="link.href"
                  [attr.target]="link.newTab ? '_blank' : null"
                  [attr.rel]="link.newTab ? 'noopener' : null"
                  >{{ link.label }}</a
                >
              }
            </li>
          }
        </ul>
      </nav>
    }
  `,
  styles: `
    ul {
      display: flex;
      flex-wrap: wrap;
      gap: 0.25rem 1.375rem;
      margin: 0;
      padding: 0;
      list-style: none;
    }
    a {
      display: inline-block;
      padding-block: 0.375rem;
      color: inherit;
      text-decoration: none;
    }
    a:hover {
      text-decoration: underline;
    }
    /* Page courante : soulignée d'or (T4, V5). */
    a[aria-current='page'] {
      font-weight: 600;
      box-shadow: inset 0 -2px var(--pt-gold);
    }
    :host([location='footer']) ul {
      flex-direction: column;
      gap: 0;
    }
  `,
})
export class SiteNav {
  readonly location = input.required<MenuLocation>();

  private readonly portal = inject(PublicMenus);
  protected readonly context = inject(PageContext);
  private readonly items = signal<PublicMenuItem[] | null>(null);

  protected readonly links = computed<NavLink[]>(() => {
    const language = this.context.language();
    const items = this.items();
    if (!language || items === null) return [];
    if (items.length) {
      return items.map((item) => {
        const href = language === 'fr' ? item.href_fr : item.href_en;
        return {
          label: (language === 'fr' ? item.label_fr : item.label_en) || item.label_fr,
          href,
          internal: href.startsWith('/') && !href.startsWith('/api/'),
          newTab: item.new_tab,
        };
      });
    }
    if (this.location() !== 'header') return [];
    return SITE_PAGES.filter((page) => FALLBACK_HEADER.includes(page.slug)).map((page) => ({
      label: language === 'fr' ? page.title_fr : page.title_en,
      href: sitePagePath(page.slug, language),
      internal: true,
      newTab: false,
    }));
  });

  constructor() {
    effect(() => {
      if (this.context.language() && this.items() === null) {
        void this.portal.menu(this.location()).then((items) => this.items.set(items));
      }
    });
  }
}

/** Sélecteur de langue du portail public : liens vers la même page dans l'autre langue. */
@Component({
  selector: 'portail-language-links',
  imports: [RouterLink, TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (context.paths(); as paths) {
      <div class="languages" role="group" [attr.aria-label]="'shared.language.label' | translate">
        @for (lang of languages; track lang) {
          <a
            [routerLink]="paths[lang]"
            [attr.lang]="lang"
            [attr.hreflang]="lang"
            [attr.aria-current]="lang === context.language() ? 'page' : null"
            >{{ 'shared.language.' + lang | translate }}</a
          >
        }
      </div>
    }
  `,
  styles: `
    .languages {
      display: flex;
      gap: 0.5rem;
    }
    a {
      color: inherit;
      padding: 0.125rem 0.5rem;
      border: 1px solid currentColor;
      border-radius: 0.25rem;
      text-decoration: none;
    }
    a[aria-current='page'] {
      font-weight: 700;
      text-decoration: underline;
    }
  `,
})
export class LanguageLinks {
  protected readonly context = inject(PageContext);
  protected readonly languages: readonly SiteLanguage[] = SITE_LANGUAGES;
}
