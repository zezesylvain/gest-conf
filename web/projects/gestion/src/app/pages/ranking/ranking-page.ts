import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  OnInit,
  signal,
} from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import {
  ConfirmDialog,
  ConfirmDialogData,
  ConfirmDialogResult,
  DecisionOutcome,
  ErrorSummary,
  MeStore,
  PageHeader,
  Ranking,
  RankingRow,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { firstValueFrom } from 'rxjs';

import { editionCapabilities, errorMessages } from '../../core/page-support';
import { OUTCOMES, RankingFilters, ReviewsApi, saveText } from '../../core/reviews-api';

/**
 * Classement et décisions (plan L4 §5, US-06, H16, RG-09) : soumissions par note finale,
 * divergence et recommandations ; simulation d'un seuil ; décisions provisoires en lot (tout
 * ou rien) ; publication des résultats (réauthentification, irréversible) ; export CSV
 * nominatif des évaluations (réauthentification, journalisé).
 */
@Component({
  selector: 'gestion-ranking-page',
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
  templateUrl: './ranking-page.html',
  styleUrl: '../page.scss',
  styles: `
    .badge.danger {
      margin-left: 0.25rem;
      border-color: var(--gc-danger);
      color: var(--gc-danger);
    }
    tr.below td {
      color: var(--gc-muted);
    }
  `,
})
export class RankingPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(ReviewsApi);
  private readonly meStore = inject(MeStore);
  private readonly dialog = inject(MatDialog);
  private readonly translate = inject(TranslateService);
  private readonly fb = inject(NonNullableFormBuilder);

  protected readonly outcomes = OUTCOMES;
  protected readonly ranking = signal<Ranking | null>(null);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  /** Décisions préparées pour le lot : soumission → issue. */
  protected readonly batch = signal<Record<number, DecisionOutcome>>({});

  private readonly capabilities = computed(() =>
    editionCapabilities(this.meStore, this.editionId()),
  );
  protected readonly canDecide = computed(() => this.capabilities().includes('decisions.decide'));
  protected readonly canPublish = computed(() => this.capabilities().includes('decisions.publish'));
  /** Décisions provisoires en attente de publication (RG-09). */
  protected readonly pending = computed(
    () =>
      (this.ranking()?.rows ?? []).filter((row) => row.decision && !row.decision.published_at)
        .length,
  );
  protected readonly batchCount = computed(() => Object.keys(this.batch()).length);
  protected readonly form = this.fb.group({
    threshold: ['', [Validators.min(0), Validators.max(100)]],
  });

  async ngOnInit(): Promise<void> {
    await this.reload();
  }

  private edition(): number {
    return Number(this.editionId());
  }

  protected threshold(): number | null {
    const raw = this.form.getRawValue().threshold;
    return raw === '' || raw === null ? null : Number(raw);
  }

  protected below(row: RankingRow): boolean {
    const threshold = this.threshold();
    const score = row.final_score === null ? null : Number(row.final_score);
    return threshold !== null && (score === null || score < threshold);
  }

  protected recommendations(row: RankingRow): string {
    return Object.entries(row.recommendations)
      .map(
        ([key, count]) =>
          `${this.translate.instant('gestion.reviews.recommendations.' + key)} ${count}`,
      )
      .join(', ');
  }

  protected decidable(row: RankingRow): boolean {
    return row.status === 'reviewed' && !row.decision?.published_at;
  }

  protected choose(row: RankingRow, outcome: DecisionOutcome | ''): void {
    this.batch.update((current) => {
      const next = { ...current };
      if (outcome) {
        next[row.id] = outcome;
      } else {
        delete next[row.id];
      }
      return next;
    });
  }

  /** Préremplit le lot : au-dessus du seuil acceptées, en dessous rejetées. */
  protected prefill(): void {
    const threshold = this.threshold();
    if (threshold === null) {
      return;
    }
    const next: Record<number, DecisionOutcome> = {};
    for (const row of this.ranking()?.rows ?? []) {
      if (this.decidable(row)) {
        next[row.id] = this.below(row) ? 'rejected' : 'accepted';
      }
    }
    this.batch.set(next);
  }

  protected async simulate(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    await this.reload();
  }

  protected async saveBatch(): Promise<void> {
    const items = Object.entries(this.batch()).map(([submission, outcome]) => ({
      submission: Number(submission),
      outcome,
    }));
    if (!items.length) {
      return;
    }
    await this.run('gestion.ranking.batch.done', async () => {
      const result = await this.api.decideBatch(this.edition(), items);
      this.batch.set({});
      return { count: result.recorded };
    });
  }

  protected async publish(): Promise<void> {
    if (!(await this.confirm('gestion.ranking.publish', { count: this.pending() }))) {
      return;
    }
    await this.run('gestion.ranking.publish.done', async () => {
      const result = await this.api.publish(this.edition());
      return { count: result.published };
    });
  }

  protected async exportCsv(): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    try {
      const content = await this.api.exportCsv(this.edition());
      saveText(content, `evaluations-${this.editionId()}.csv`);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }

  private async reload(): Promise<void> {
    const filters: RankingFilters = {};
    const threshold = this.threshold();
    if (threshold !== null) {
      filters.threshold = threshold;
    }
    try {
      this.ranking.set(await this.api.ranking(this.edition(), filters));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }

  private async confirm(key: string, params: Record<string, unknown> = {}): Promise<boolean> {
    const data: ConfirmDialogData = {
      title: this.translate.instant(`${key}.title`),
      message: this.translate.instant(`${key}.message`, params),
      confirmLabel: this.translate.instant(`${key}.confirm`),
    };
    const ref = this.dialog.open<ConfirmDialog, ConfirmDialogData, ConfirmDialogResult>(
      ConfirmDialog,
      { data, width: '30rem' },
    );
    return !!(await firstValueFrom(ref.afterClosed()));
  }

  private async run(done: string, action: () => Promise<Record<string, unknown>>): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    this.status.set('');
    try {
      const params = await action();
      await this.reload();
      this.status.set(this.translate.instant(done, params));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }
}
