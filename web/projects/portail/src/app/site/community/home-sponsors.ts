import {
  ChangeDetectionStrategy,
  Component,
  inject,
  input,
  OnInit,
  PendingTasks,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { PublicSponsors } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { localized, sitePagePath, SiteLanguage } from '../site-pages';
import { CommunityData } from './community-data';

/**
 * Bande des partenaires en bas de l'accueil (décision T4, V10) : logos par niveau, lus dans
 * la liste blanche publique de la page « Partenaires » (pré-rendue). Rien sans partenaire
 * publié ou en cas d'erreur : l'accueil reste complet sans elle.
 */
@Component({
  selector: 'portail-home-sponsors',
  imports: [RouterLink, TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (data(); as current) {
      @if (current.levels.length) {
        <section class="strip" aria-labelledby="home-sponsors">
          <div class="wrap">
            <h2 id="home-sponsors">
              <a [routerLink]="link()">{{ 'portail.community.sponsorsTitle' | translate }}</a>
            </h2>
            <div class="levels">
              @for (level of current.levels; track $index) {
                @if (level.sponsors.length) {
                  <div class="level">
                    <h3>{{ text(level, 'name') }}</h3>
                    <ul [class.large]="level.logo_size === 'large'">
                      @for (sponsor of level.sponsors; track $index) {
                        <li>
                          @if (sponsor.logo_url) {
                            <img
                              [src]="sponsor.logo_url"
                              [attr.width]="sponsor.logo_width"
                              [attr.height]="sponsor.logo_height"
                              [alt]="sponsor.name"
                              loading="lazy"
                            />
                          } @else {
                            {{ sponsor.name }}
                          }
                        </li>
                      }
                    </ul>
                  </div>
                }
              }
            </div>
          </div>
        </section>
      }
    }
  `,
  styles: `
    .strip {
      padding-block: 3.5rem;
      border-top: 1px solid var(--pt-line);
    }
    .wrap {
      max-width: var(--pt-wrap);
      margin-inline: auto;
      padding-inline: var(--pt-gutter);
    }
    h2 {
      margin: 0 0 1.5rem;
      font-size: 1.625rem;
    }
    h2 a {
      color: inherit;
      text-decoration: none;
    }
    h3 {
      margin: 0 0 1rem;
      font-family: var(--gc-font);
      font-size: 0.8125rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--gc-muted);
    }
    .levels {
      display: flex;
      flex-wrap: wrap;
      gap: 2.5rem 4rem;
    }
    ul {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 1.5rem 2rem;
      margin: 0;
      padding: 0;
      list-style: none;
    }
    img {
      display: block;
      width: auto;
      height: 3.5rem;
      max-width: 10rem;
      object-fit: contain;
    }
    .large img {
      height: 4.5rem;
    }
  `,
})
export class HomeSponsors implements OnInit {
  readonly language = input.required<SiteLanguage>();

  private readonly community = inject(CommunityData);
  private readonly pendingTasks = inject(PendingTasks);
  protected readonly data = signal<PublicSponsors | null>(null);

  async ngOnInit(): Promise<void> {
    await this.pendingTasks.run(async () => {
      try {
        this.data.set(await this.community.sponsors());
      } catch {
        // Bande facultative : rien à afficher.
      }
    });
  }

  protected link(): string {
    return sitePagePath('sponsors', this.language());
  }

  protected text(item: object, field: string): string {
    return localized(item, field, this.language());
  }
}
