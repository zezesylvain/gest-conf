import { NgTemplateOutlet } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  inject,
  input,
  OnInit,
  PendingTasks,
  signal,
} from '@angular/core';
import { GcApiError, PublicSponsorCard, PublicSponsors } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { safeHref } from '../sanitize';
import { localized, SiteLanguage } from '../site-pages';
import { CommunityData } from './community-data';

/**
 * Page publique « Partenaires » (plan L8, N5) : niveaux dans l'ordre, partenaires publiés
 * avec logo, site et présentation ; ceux sans niveau à la fin. Pré-rendue : une
 * modification n'apparaît qu'à la publication du portail.
 */
@Component({
  selector: 'portail-sponsors-overview',
  imports: [NgTemplateOutlet, TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <ng-template #card let-sponsor>
      <li class="card">
        @if (sponsor.logo_url) {
          <img
            class="logo"
            [src]="sponsor.logo_url"
            [attr.width]="sponsor.logo_width"
            [attr.height]="sponsor.logo_height"
            [alt]="'portail.community.logoAlt' | translate: { name: sponsor.name }"
            loading="lazy"
          />
        }
        <h3>{{ sponsor.name }}</h3>
        @if (text(sponsor, 'description')) {
          <p>{{ text(sponsor, 'description') }}</p>
        }
        @if (href(sponsor); as link) {
          <p>
            <a [href]="link" rel="noopener" target="_blank">{{
              'portail.community.website' | translate: { name: sponsor.name }
            }}</a>
          </p>
        }
      </li>
    </ng-template>
    @switch (state()) {
      @case ('loading') {
        <p role="status" class="muted">{{ 'portail.site.loading' | translate }}</p>
      }
      @case ('error') {
        <p>{{ 'portail.site.errorLead' | translate }}</p>
      }
      @case ('ready') {
        @let current = data()!;
        @if (!current.levels.length && !current.others.length) {
          <p class="soon">{{ 'portail.community.noSponsor' | translate }}</p>
        }
        @for (level of current.levels; track $index) {
          <section class="level" [attr.aria-labelledby]="'level-' + $index">
            <h2 [id]="'level-' + $index">{{ text(level, 'name') }}</h2>
            <ul
              class="cards"
              [class.large]="level.logo_size === 'large'"
              [class.small]="level.logo_size === 'small'"
            >
              @for (sponsor of level.sponsors; track $index) {
                <ng-container *ngTemplateOutlet="card; context: { $implicit: sponsor }" />
              }
            </ul>
          </section>
        }
        @if (current.others.length) {
          <section class="level" aria-labelledby="level-others">
            <h2 id="level-others">{{ 'portail.community.otherSponsors' | translate }}</h2>
            <ul class="cards">
              @for (sponsor of current.others; track $index) {
                <ng-container *ngTemplateOutlet="card; context: { $implicit: sponsor }" />
              }
            </ul>
          </section>
        }
      }
    }
  `,
  styleUrls: ['../site.scss', './community.scss'],
})
export class SponsorsOverview implements OnInit {
  readonly language = input.required<SiteLanguage>();

  private readonly community = inject(CommunityData);
  private readonly pendingTasks = inject(PendingTasks);

  protected readonly data = signal<PublicSponsors | null>(null);
  protected readonly state = signal<'loading' | 'ready' | 'error'>('loading');

  async ngOnInit(): Promise<void> {
    await this.pendingTasks.run(async () => {
      try {
        this.data.set(await this.community.sponsors());
        this.state.set('ready');
      } catch (error) {
        // Sans édition publique : aucune liste, la page le dit.
        if (error instanceof GcApiError && error.status === 404) {
          this.data.set({ levels: [], others: [] });
          this.state.set('ready');
        } else {
          this.state.set('error');
        }
      }
    });
  }

  protected text(item: object, field: string): string {
    return localized(item, field, this.language());
  }

  protected href(sponsor: PublicSponsorCard): string | null {
    return sponsor.website ? safeHref(sponsor.website) : null;
  }
}
