import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  OnInit,
  signal,
} from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import {
  ErrorSummary,
  PageHeader,
  ReviewProgress,
  ReviewSubmission,
  SubmissionStatus,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { errorMessages } from '../../core/page-support';
import { FollowUpFilters, ReviewsApi } from '../../core/reviews-api';

const PAGE_SIZE = 25;

/** Statuts du suivi de l'évaluation, de la recevabilité à la décision. */
export const FOLLOW_UP_STATUSES: readonly SubmissionStatus[] = [
  'screening',
  'under_review',
  'reviewed',
  'accepted',
  'accepted_minor',
  'waitlist',
  'rejected',
  'camera_ready_received',
  'withdrawn',
];

/**
 * Pilotage de l'évaluation (plan L4 §5, H6, H10, H12) : soumissions de la recevabilité à la
 * décision, avec relecteurs affectés, évaluations envoyées et retards ; filtres « relecteurs
 * manquants » et « en retard » ; avancement par relecteur et par thématique, divergences.
 */
@Component({
  selector: 'gestion-follow-up-page',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TranslatePipe,
    MatButtonModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './follow-up-page.html',
  styleUrl: '../page.scss',
  styles: `
    .badge.warning {
      border-color: var(--gc-warning, #b26a00);
      color: var(--gc-warning, #b26a00);
    }
  `,
})
export class FollowUpPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(ReviewsApi);
  private readonly translate = inject(TranslateService);

  protected readonly statuses = FOLLOW_UP_STATUSES;
  protected readonly rows = signal<ReviewSubmission[]>([]);
  protected readonly progress = signal<ReviewProgress | null>(null);
  protected readonly count = signal(0);
  protected readonly page = signal(1);
  protected readonly loading = signal(true);
  protected readonly errors = signal<string[]>([]);
  protected readonly pages = computed(() => Math.max(1, Math.ceil(this.count() / PAGE_SIZE)));
  protected readonly form = inject(NonNullableFormBuilder).group({
    q: [''],
    status: [[] as SubmissionStatus[]],
    missing: [false],
    late: [false],
  });

  async ngOnInit(): Promise<void> {
    try {
      this.progress.set(await this.api.progress(Number(this.editionId())));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
    await this.reload();
  }

  protected async search(): Promise<void> {
    this.page.set(1);
    await this.reload();
  }

  protected async reset(): Promise<void> {
    this.form.reset();
    await this.search();
  }

  protected async goTo(page: number): Promise<void> {
    this.page.set(page);
    await this.reload();
  }

  private filters(): FollowUpFilters {
    const value = this.form.getRawValue();
    const filters: FollowUpFilters = {};
    if (value.q.trim()) filters.q = value.q.trim();
    if (value.status.length) {
      filters.status = value.status as NonNullable<FollowUpFilters['status']>;
    }
    if (value.missing) filters.missing = true;
    if (value.late) filters.late = true;
    return filters;
  }

  private async reload(): Promise<void> {
    this.errors.set([]);
    try {
      const result = await this.api.followUp(Number(this.editionId()), {
        ...this.filters(),
        page: this.page(),
        page_size: PAGE_SIZE,
      });
      this.rows.set(result.results);
      this.count.set(result.count);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }
}
