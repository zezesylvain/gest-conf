import { ChangeDetectionStrategy, Component, inject, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import {
  ErrorSummary,
  formatInZone,
  LanguageService,
  MySurvey,
  PageHeader,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { CommunityService } from './community.service';
import { messagesOf } from './community-support';

/**
 * « Questionnaires » (plan L8, N12) : questionnaires de satisfaction auxquels la personne
 * est invitée (sa présence a été enregistrée), ouverts ou non, répondus ou non.
 */
@Component({
  selector: 'portail-surveys-page',
  imports: [RouterLink, TranslatePipe, ErrorSummary, PageHeader],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <gc-page-header
      [heading]="'portail.community.surveys.title' | translate"
      [lead]="'portail.community.surveys.lead' | translate"
    />
    <gc-error-summary [messages]="errors()" />
    @if (loading()) {
      <p role="status">{{ 'portail.account.home.loading' | translate }}</p>
    } @else {
      <ul class="list">
        @for (item of surveys(); track item.id) {
          <li>
            <strong>{{ title(item) }}</strong>
            @if (item.session_title) {
              — {{ item.session_title }}
            }
            <br />
            @if (item.answered) {
              <span>{{ 'portail.community.surveys.answered' | translate }}</span>
            } @else if (item.is_open) {
              <a [routerLink]="['/compte/questionnaires', item.id]">{{
                'portail.community.surveys.answer' | translate
              }}</a>
              <span class="muted">
                ·
                {{ 'portail.community.surveys.closes' | translate: { date: when(item.closes_at) } }}
              </span>
            } @else {
              <span class="muted">{{ 'portail.community.surveys.closed' | translate }}</span>
            }
          </li>
        } @empty {
          <li>{{ 'portail.community.surveys.none' | translate }}</li>
        }
      </ul>
    }
  `,
  styleUrl: './community.scss',
})
export class SurveysPage implements OnInit {
  private readonly service = inject(CommunityService);
  private readonly translate = inject(TranslateService);
  private readonly language = inject(LanguageService);

  protected readonly surveys = signal<MySurvey[]>([]);
  protected readonly loading = signal(true);
  protected readonly errors = signal<string[]>([]);

  async ngOnInit(): Promise<void> {
    try {
      this.surveys.set(await this.service.surveys());
    } catch (error) {
      this.errors.set(messagesOf(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }

  protected title(item: MySurvey): string {
    return (this.language.current() === 'en' && item.title_en) || item.title_fr;
  }

  protected when(iso: string): string {
    return formatInZone(iso, undefined, this.language.current());
  }
}
