import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  OnInit,
  signal,
} from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import {
  FormControl,
  FormRecord,
  NonNullableFormBuilder,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { Router, RouterLink } from '@angular/router';
import {
  ConfirmDialog,
  ConfirmDialogData,
  ConfirmDialogResult,
  ErrorSummary,
  formatInZone,
  LanguageService,
  OpenReviewAuthor,
  PageHeader,
  Recommendation,
  ReviewerAssignmentDetail,
  ReviewerCriterion,
  ReviewerDiscussion,
  ReviewWriteRequest,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { firstValueFrom, map, startWith } from 'rxjs';

import { errorMessages } from '../../core/page-support';
import { weightedScore } from '../../core/review-score';
import { reviewerFileUrl, ReviewsApi } from '../../core/reviews-api';

export const RECOMMENDATIONS: readonly Recommendation[] = [
  'accept',
  'accept_minor',
  'reject',
  'discuss',
];

/**
 * Formulaire d'évaluation (plan L4 §5, H1, H4, H5) : soumission anonymisée (RG-04) et PDF,
 * grille pondérée avec la note **indicative** calculée pendant la saisie (le serveur la
 * recalcule et fait foi), recommandation, confiance, commentaires. Brouillon, envoi, renvoi
 * après envoi jusqu'à la décision (RG-06) ; refus motivé, avec conflit d'intérêts (H8) ;
 * discussion une fois son évaluation envoyée et la discussion ouverte (RG-08), sous
 * pseudonymes (H11).
 */
@Component({
  selector: 'gestion-review-form-page',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TranslatePipe,
    MatButtonModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    PageHeader,
    ErrorSummary,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './review-form-page.html',
  styleUrl: '../page.scss',
  styles: `
    .abstract,
    .comment {
      white-space: pre-wrap;
    }
    .criterion {
      display: grid;
      gap: 0.25rem;
      padding: 0.5rem 0;
      border-bottom: 1px solid var(--gc-border);
    }
    .criterion-label {
      font-weight: 600;
      overflow-wrap: anywhere;
    }
    mat-form-field[subscriptsizing='dynamic'] {
      margin-bottom: 0.75rem;
    }
    .score {
      font-size: 1.4rem;
      font-weight: 700;
    }
    .peer,
    .message {
      padding: 0.5rem 0;
      border-bottom: 1px solid var(--gc-border);
    }
  `,
})
export class ReviewFormPage implements OnInit {
  readonly editionId = input.required<string>();
  readonly assignmentId = input.required<string>();

  private readonly api = inject(ReviewsApi);
  private readonly router = inject(Router);
  private readonly dialog = inject(MatDialog);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);
  private readonly fb = inject(NonNullableFormBuilder);

  protected readonly recommendations = RECOMMENDATIONS;
  protected readonly confidences = [1, 2, 3, 4, 5];
  protected readonly assignment = signal<ReviewerAssignmentDetail | null>(null);
  protected readonly authors = signal<OpenReviewAuthor[]>([]);
  protected readonly discussion = signal<ReviewerDiscussion | null>(null);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  protected readonly declining = signal(false);

  protected readonly scores = new FormRecord<FormControl<string>>({});
  protected readonly form = this.fb.group({
    scores: this.scores,
    recommendation: this.fb.control<Recommendation | ''>(''),
    confidence: this.fb.control<number | null>(null),
    comment_to_authors: ['', Validators.maxLength(20000)],
    comment_to_committee: ['', Validators.maxLength(20000)],
    ethics_flag: [false],
    plagiarism_flag: [false],
  });
  protected readonly declineForm = this.fb.group({
    reason: ['', [Validators.required, Validators.maxLength(2000)]],
    conflict: [false],
  });
  protected readonly messageForm = this.fb.group({
    body: ['', [Validators.required, Validators.maxLength(5000)]],
  });

  private readonly values = toSignal(
    this.scores.valueChanges.pipe(
      startWith(null),
      map(() => this.scores.getRawValue()),
    ),
    { initialValue: {} as Record<string, string> },
  );
  /** Note indicative, recalculée à chaque frappe (le serveur fait foi). */
  protected readonly liveScore = computed(() => {
    const grid = this.assignment()?.grid;
    if (!grid) {
      return null;
    }
    return weightedScore(grid.criteria, this.values(), grid.scale_min ?? 0, grid.scale_max ?? 5);
  });
  protected readonly submitted = computed(() => this.assignment()?.review?.status === 'submitted');
  protected readonly editable = computed(() => this.assignment()?.can_edit ?? false);

  async ngOnInit(): Promise<void> {
    await this.load();
  }

  private ids(): [number, number] {
    return [Number(this.editionId()), Number(this.assignmentId())];
  }

  private async load(): Promise<void> {
    const [edition, assignment] = this.ids();
    try {
      const detail = await this.api.assignment(edition, assignment);
      this.fill(detail);
      if (!detail.double_blind) {
        this.authors.set(await this.api.authors(edition, assignment));
      }
      if (detail.discussion_open) {
        this.discussion.set(await this.api.discussion(edition, assignment));
      }
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }

  private fill(detail: ReviewerAssignmentDetail): void {
    this.assignment.set(detail);
    const review = detail.review;
    for (const criterion of detail.grid?.criteria ?? []) {
      if (!this.scores.contains(criterion.code)) {
        this.scores.addControl(criterion.code, this.fb.control(''));
      }
    }
    for (const [code, value] of Object.entries(review?.scores ?? {})) {
      this.scores.get(code)?.setValue(String(Number(value)));
    }
    this.form.patchValue({
      recommendation: review?.recommendation || '',
      confidence: review?.confidence ?? null,
      comment_to_authors: review?.comment_to_authors ?? '',
      comment_to_committee: review?.comment_to_committee ?? '',
      ethics_flag: review?.ethics_flag ?? false,
      plagiarism_flag: review?.plagiarism_flag ?? false,
    });
    if (detail.can_edit) {
      this.form.enable();
    } else {
      this.form.disable();
    }
  }

  protected label(criterion: ReviewerCriterion): string {
    return this.language.current() === 'en' && criterion.label_en
      ? criterion.label_en
      : criterion.label_fr;
  }

  protected helpText(criterion: ReviewerCriterion): string {
    return (this.language.current() === 'en' && criterion.help_en) || criterion.help_fr || '';
  }

  protected date(value: string | null | undefined): string {
    return value ? formatInZone(value, undefined, this.language.current()) : '—';
  }

  protected fileHref(): string {
    return reviewerFileUrl(this.editionId(), Number(this.assignmentId()));
  }

  protected score(value: number | null): string {
    return value === null ? '—' : value.toFixed(2);
  }

  private body(): ReviewWriteRequest {
    const value = this.form.getRawValue();
    const scores: Record<string, string | null> = {};
    for (const [code, raw] of Object.entries(value.scores)) {
      scores[code] = raw === '' || raw === null ? null : String(raw);
    }
    return {
      scores,
      recommendation: value.recommendation,
      confidence: value.confidence,
      comment_to_authors: value.comment_to_authors,
      comment_to_committee: value.comment_to_committee,
      ethics_flag: value.ethics_flag,
      plagiarism_flag: value.plagiarism_flag,
    };
  }

  protected async save(): Promise<void> {
    await this.run('gestion.reviews.form.saved', async () => {
      const [edition, assignment] = this.ids();
      await this.api.saveReview(edition, assignment, this.body());
    });
  }

  protected async submit(): Promise<void> {
    const confirmed = await this.confirm(
      this.submitted()
        ? 'gestion.reviews.form.resubmitConfirm'
        : 'gestion.reviews.form.submitConfirm',
    );
    if (!confirmed) {
      return;
    }
    await this.run('gestion.reviews.form.submitted', async () => {
      const [edition, assignment] = this.ids();
      await this.api.submitReview(edition, assignment, this.body());
    });
  }

  protected async decline(): Promise<void> {
    if (this.declineForm.invalid) {
      this.declineForm.markAllAsTouched();
      return;
    }
    if (!(await this.confirm('gestion.reviews.decline.confirm'))) {
      return;
    }
    this.busy.set(true);
    this.errors.set([]);
    try {
      const [edition, assignment] = this.ids();
      await this.api.decline(edition, assignment, this.declineForm.getRawValue());
      await this.router.navigate(['/editions', this.editionId(), 'evaluations']);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }

  protected async post(): Promise<void> {
    if (this.messageForm.invalid) {
      this.messageForm.markAllAsTouched();
      return;
    }
    this.busy.set(true);
    this.errors.set([]);
    try {
      const [edition, assignment] = this.ids();
      this.discussion.set(
        await this.api.postReviewerMessage(
          edition,
          assignment,
          this.messageForm.getRawValue().body,
        ),
      );
      this.messageForm.reset();
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }

  /** Pseudonyme (H11) : « Relecteur N », « vous », ou le président du comité. */
  protected who(rank: number | null | undefined, mine: boolean): string {
    if (mine) {
      return this.translate.instant('gestion.reviews.discussion.you');
    }
    return rank
      ? this.translate.instant('gestion.reviews.discussion.reviewer', { rank })
      : this.translate.instant('gestion.reviews.discussion.chair');
  }

  private async confirm(key: string): Promise<boolean> {
    const data: ConfirmDialogData = {
      title: this.translate.instant(`${key}.title`),
      message: this.translate.instant(`${key}.message`),
      confirmLabel: this.translate.instant(`${key}.confirm`),
    };
    const ref = this.dialog.open<ConfirmDialog, ConfirmDialogData, ConfirmDialogResult>(
      ConfirmDialog,
      { data, width: '30rem' },
    );
    return !!(await firstValueFrom(ref.afterClosed()));
  }

  private async run(done: string, action: () => Promise<void>): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    this.status.set('');
    try {
      await action();
      const [edition, assignment] = this.ids();
      const detail = await this.api.assignment(edition, assignment);
      this.fill(detail);
      if (detail.discussion_open) {
        this.discussion.set(await this.api.discussion(edition, assignment));
      }
      this.status.set(this.translate.instant(done));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }
}
