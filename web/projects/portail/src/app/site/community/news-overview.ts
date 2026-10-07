import {
  ChangeDetectionStrategy,
  Component,
  inject,
  input,
  OnInit,
  PendingTasks,
  signal,
} from '@angular/core';
import { GcApiError, PublicNewsItem } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { sanitizeHtml } from '../sanitize';
import { localized, SiteLanguage } from '../site-pages';
import { formatDay } from '../widgets';
import { CommunityData } from './community-data';
import { newsAnchor } from './community-support';

/**
 * Page publique « Actualités » (plan L8, N10) : annonces publiées sur ce canal, les plus
 * récentes d'abord ; texte HTML assaini par le serveur **et** au rendu (liste blanche de
 * L2). Pré-rendue : une actualité n'apparaît qu'à la publication du portail.
 */
@Component({
  selector: 'portail-news-overview',
  imports: [TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @switch (state()) {
      @case ('loading') {
        <p role="status" class="muted">{{ 'portail.site.loading' | translate }}</p>
      }
      @case ('error') {
        <p>{{ 'portail.site.errorLead' | translate }}</p>
      }
      @case ('ready') {
        @for (item of items(); track item.id) {
          <article
            class="news-item"
            [id]="anchor(item)"
            [attr.aria-labelledby]="anchor(item) + '-titre'"
          >
            <h2 [id]="anchor(item) + '-titre'">{{ text(item, 'title') }}</h2>
            <p class="muted">
              <time [attr.datetime]="item.published_at">{{ day(item.published_at) }}</time>
            </p>
            <div class="prose" [innerHTML]="body(item)"></div>
          </article>
        } @empty {
          <p class="soon">{{ 'portail.community.noNews' | translate }}</p>
        }
      }
    }
  `,
  styleUrls: ['../site.scss', './community.scss'],
})
export class NewsOverview implements OnInit {
  readonly language = input.required<SiteLanguage>();

  private readonly community = inject(CommunityData);
  private readonly pendingTasks = inject(PendingTasks);

  protected readonly items = signal<PublicNewsItem[]>([]);
  protected readonly state = signal<'loading' | 'ready' | 'error'>('loading');

  async ngOnInit(): Promise<void> {
    await this.pendingTasks.run(async () => {
      try {
        this.items.set(await this.community.news());
        this.state.set('ready');
      } catch (error) {
        if (error instanceof GcApiError && error.status === 404) {
          this.items.set([]);
          this.state.set('ready');
        } else {
          this.state.set('error');
        }
      }
    });
  }

  protected anchor(item: PublicNewsItem): string {
    return newsAnchor(item.id);
  }

  protected text(item: PublicNewsItem, field: string): string {
    return localized(item, field, this.language());
  }

  /** Texte anglais vide : le français (comme les e-mails, plan L8 §16). */
  protected body(item: PublicNewsItem): string {
    return sanitizeHtml(localized(item, 'body', this.language()));
  }

  protected day(value: string): string {
    return formatDay(value.slice(0, 10), this.language());
  }
}
