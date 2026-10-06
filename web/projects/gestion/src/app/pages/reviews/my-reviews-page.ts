import { ChangeDetectionStrategy, Component, inject, input, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import {
  ErrorSummary,
  formatInZone,
  LanguageService,
  PageHeader,
  ReviewerAssignment,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { errorMessages } from '../../core/page-support';
import { ReviewsApi } from '../../core/reviews-api';

/**
 * « Mes évaluations » (plan L4 §5, H1) : affectations du relecteur, échéances et état de son
 * évaluation. Soumissions désignées par leur référence et leur titre seulement (RG-04).
 */
@Component({
  selector: 'gestion-my-reviews-page',
  imports: [RouterLink, TranslatePipe, PageHeader, ErrorSummary],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: '../page.scss',
  template: `
    <gc-page-header
      [heading]="'gestion.reviews.title' | translate"
      [lead]="'gestion.reviews.lead' | translate"
    />
    <gc-error-summary [messages]="errors()" />
    @if (loading()) {
      <p role="status">{{ 'gestion.reviews.loading' | translate }}</p>
    } @else if (items().length) {
      <div class="table-wrap">
        <table>
          <caption class="visually-hidden">
            {{
              'gestion.reviews.title' | translate
            }}
          </caption>
          <thead>
            <tr>
              <th scope="col">{{ 'gestion.reviews.fields.submission' | translate }}</th>
              <th scope="col">{{ 'gestion.reviews.fields.track' | translate }}</th>
              <th scope="col">{{ 'gestion.reviews.fields.due' | translate }}</th>
              <th scope="col">{{ 'gestion.reviews.fields.state' | translate }}</th>
            </tr>
          </thead>
          <tbody>
            @for (item of items(); track item.id) {
              <tr>
                <td>
                  <a [routerLink]="[item.id]">
                    <strong>{{ item.submission.reference }}</strong> — {{ item.submission.title }}
                  </a>
                </td>
                <td>{{ item.submission.track?.code ?? '—' }}</td>
                <td>{{ date(item.due_at) }}</td>
                <td>
                  <span class="badge">{{ state(item) | translate }}</span>
                </td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    } @else {
      <p class="muted">{{ 'gestion.reviews.empty' | translate }}</p>
    }
  `,
})
export class MyReviewsPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(ReviewsApi);
  private readonly translate = inject(TranslateService);
  private readonly language = inject(LanguageService);

  protected readonly items = signal<ReviewerAssignment[]>([]);
  protected readonly loading = signal(true);
  protected readonly errors = signal<string[]>([]);

  async ngOnInit(): Promise<void> {
    try {
      this.items.set(await this.api.myAssignments(Number(this.editionId())));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }

  protected date(value: string | null | undefined): string {
    return value ? formatInZone(value, undefined, this.language.current()) : '—';
  }

  /** État lisible : à faire, brouillon, envoyée, ou lecture seule après la décision. */
  protected state(item: ReviewerAssignment): string {
    if (item.review_status === 'submitted') {
      return 'gestion.reviews.states.submitted';
    }
    if (!item.can_edit) {
      return 'gestion.reviews.states.closed';
    }
    return item.review_status === 'draft'
      ? 'gestion.reviews.states.draft'
      : 'gestion.reviews.states.todo';
  }
}
