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
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import {
  Candidate,
  CandidateList,
  ConfirmDialog,
  ConfirmDialogData,
  ConfirmDialogResult,
  DecisionOutcome,
  ErrorSummary,
  formatInZone,
  LanguageService,
  MeStore,
  PageHeader,
  ReviewSubmissionDetail,
  SubmissionReviews,
  SubmissionType,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { firstValueFrom } from 'rxjs';

import { EditionApi } from '../../core/edition-api';
import { editionCapabilities, errorMessages } from '../../core/page-support';
import { OUTCOMES, ReviewsApi } from '../../core/reviews-api';

const ASSIGNABLE = ['screening', 'under_review', 'reviewed'];

/**
 * Pilotage d'une soumission (plan L4 §5) : recevabilité (H10), affectations et candidats
 * (charge, expertises, conflits, H6 à H8), conflits déclarés, évaluations nominatives et
 * divergence (H11, H12), discussion (RG-08), décision provisoire et liste d'attente (H16).
 * Chaque action est revérifiée par le serveur ; lever un conflit demande une
 * réauthentification récente, ouverte par l'intercepteur.
 */
@Component({
  selector: 'gestion-follow-up-detail-page',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TranslatePipe,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './follow-up-detail-page.html',
  styleUrl: '../page.scss',
  styles: `
    .abstract,
    .comment {
      white-space: pre-wrap;
    }
    .badge.warning {
      border-color: var(--gc-warning, #b26a00);
      color: var(--gc-warning, #b26a00);
    }
    .badge.danger {
      border-color: var(--gc-danger);
      color: var(--gc-danger);
    }
    .review,
    .message {
      padding: 0.5rem 0;
      border-bottom: 1px solid var(--gc-border);
    }
  `,
})
export class FollowUpDetailPage implements OnInit {
  readonly editionId = input.required<string>();
  readonly submissionId = input.required<string>();

  private readonly api = inject(ReviewsApi);
  private readonly editions = inject(EditionApi);
  private readonly meStore = inject(MeStore);
  private readonly dialog = inject(MatDialog);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);
  private readonly fb = inject(NonNullableFormBuilder);

  protected readonly outcomes = OUTCOMES;
  protected readonly detail = signal<ReviewSubmissionDetail | null>(null);
  protected readonly candidates = signal<CandidateList | null>(null);
  protected readonly reviews = signal<SubmissionReviews | null>(null);
  protected readonly types = signal<SubmissionType[]>([]);
  protected readonly timezone = signal<string | undefined>(undefined);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  /** Relecteur choisi pour l'affectation (formulaire sous la liste des candidats). */
  protected readonly selected = signal<Candidate | null>(null);
  /** Affectation dont on saisit le motif d'annulation, ou la nouvelle échéance. */
  protected readonly cancelling = signal<number | null>(null);
  protected readonly rescheduling = signal<number | null>(null);
  protected readonly declaringFor = signal<Candidate | null>(null);

  private readonly capabilities = computed(() =>
    editionCapabilities(this.meStore, this.editionId()),
  );
  protected readonly canManage = computed(() => this.capabilities().includes('reviews.manage'));
  protected readonly canReadAll = computed(() => this.capabilities().includes('reviews.read_all'));
  protected readonly canDecide = computed(() => this.capabilities().includes('decisions.decide'));
  protected readonly canPublish = computed(() => this.capabilities().includes('decisions.publish'));
  protected readonly assignable = computed(() => ASSIGNABLE.includes(this.detail()?.status ?? ''));
  /** Conflits du candidat choisi qui exigent un motif de levée (H8). */
  protected readonly needsOverride = computed(
    () => this.selected()?.conflicts.some((c) => c.overridable && !c.overridden) ?? false,
  );

  protected readonly screeningForm = this.fb.group({
    reason: ['', Validators.maxLength(2000)],
  });
  protected readonly assignForm = this.fb.group({
    due_local: [''],
    override_reason: ['', Validators.maxLength(2000)],
  });
  protected readonly reasonForm = this.fb.group({
    reason: ['', [Validators.required, Validators.maxLength(2000)]],
  });
  protected readonly dueForm = this.fb.group({
    due_local: ['', Validators.required],
  });
  protected readonly messageForm = this.fb.group({
    body: ['', [Validators.required, Validators.maxLength(5000)]],
  });
  protected readonly decisionForm = this.fb.group({
    outcome: this.fb.control<DecisionOutcome>('accepted'),
    assigned_type: [''],
    comment_to_authors: ['', Validators.maxLength(20000)],
  });

  async ngOnInit(): Promise<void> {
    try {
      const [edition, types] = await Promise.all([
        this.editions.edition(this.edition()),
        this.editions.submissionTypes(this.edition()),
      ]);
      this.timezone.set(edition.timezone);
      this.types.set(types);
    } catch {
      // Lecture du paramétrage facultative ici : dates en heure du navigateur, codes seuls.
    }
    await this.load();
    this.loading.set(false);
  }

  private edition(): number {
    return Number(this.editionId());
  }

  private submission(): number {
    return Number(this.submissionId());
  }

  private async load(): Promise<void> {
    try {
      const detail = await this.api.submission(this.edition(), this.submission());
      this.setDetail(detail);
      await this.refreshSide(detail);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
  }

  private setDetail(detail: ReviewSubmissionDetail): void {
    this.detail.set(detail);
    const decision = detail.decision;
    this.decisionForm.reset({
      outcome: decision?.outcome ?? 'accepted',
      assigned_type: decision?.assigned_type ?? '',
      comment_to_authors: decision?.comment_to_authors ?? '',
    });
  }

  private async refreshSide(detail: ReviewSubmissionDetail): Promise<void> {
    if (this.canManage() && ASSIGNABLE.includes(detail.status)) {
      this.candidates.set(await this.api.candidates(this.edition(), this.submission()));
    } else {
      this.candidates.set(null);
    }
    if (this.canReadAll() && detail.status !== 'screening') {
      this.reviews.set(await this.api.reviews(this.edition(), this.submission()));
    }
  }

  protected date(value: string | null | undefined): string {
    return value ? formatInZone(value, this.timezone(), this.language.current()) : '—';
  }

  protected conflictLabel(kind: string): string {
    return this.translate.instant(`gestion.followUp.conflicts.${kind}`);
  }

  protected canAssign(candidate: Candidate): boolean {
    return (
      candidate.assignment_id === null &&
      !candidate.conflicts.some((c) => c.kind === 'author') &&
      candidate.load < (this.candidates()?.max_load ?? Infinity)
    );
  }

  protected select(candidate: Candidate): void {
    this.selected.set(candidate);
    this.assignForm.reset();
  }

  // --- Actions ------------------------------------------------------------------------------

  protected async screen(admissible: boolean): Promise<void> {
    const reason = this.screeningForm.getRawValue().reason.trim();
    if (!admissible && !reason) {
      this.errors.set([this.translate.instant('gestion.followUp.screening.reasonRequired')]);
      return;
    }
    const key = admissible
      ? 'gestion.followUp.screening.admit'
      : 'gestion.followUp.screening.reject';
    if (!(await this.confirm(key))) {
      return;
    }
    await this.run(`${key}.done`, async () => {
      this.setDetail(
        await this.api.screen(
          this.edition(),
          this.submission(),
          admissible ? 'admissible' : 'reject',
          reason,
        ),
      );
      this.screeningForm.reset();
    });
  }

  protected async assign(): Promise<void> {
    const candidate = this.selected();
    if (!candidate) {
      return;
    }
    const value = this.assignForm.getRawValue();
    if (this.needsOverride() && !value.override_reason.trim()) {
      this.errors.set([this.translate.instant('gestion.followUp.assign.overrideRequired')]);
      return;
    }
    await this.run('gestion.followUp.assign.done', async () => {
      await this.api.assign(this.edition(), {
        submission: this.submission(),
        reviewer: candidate.id,
        due_local: value.due_local || null,
        override_reason: value.override_reason.trim(),
      });
      this.selected.set(null);
      this.setDetail(await this.api.submission(this.edition(), this.submission()));
    });
  }

  protected async cancel(assignmentId: number): Promise<void> {
    if (this.reasonForm.invalid) {
      this.reasonForm.markAllAsTouched();
      return;
    }
    await this.run('gestion.followUp.assignments.cancelled', async () => {
      await this.api.cancelAssignment(
        this.edition(),
        assignmentId,
        this.reasonForm.getRawValue().reason,
      );
      this.cancelling.set(null);
      this.reasonForm.reset();
      this.setDetail(await this.api.submission(this.edition(), this.submission()));
    });
  }

  protected async reschedule(assignmentId: number): Promise<void> {
    if (this.dueForm.invalid) {
      this.dueForm.markAllAsTouched();
      return;
    }
    await this.run('gestion.followUp.assignments.rescheduled', async () => {
      await this.api.changeDueDate(
        this.edition(),
        assignmentId,
        this.dueForm.getRawValue().due_local,
      );
      this.rescheduling.set(null);
      this.dueForm.reset();
      this.setDetail(await this.api.submission(this.edition(), this.submission()));
    });
  }

  protected async declareConflict(): Promise<void> {
    const candidate = this.declaringFor();
    if (!candidate || this.reasonForm.invalid) {
      this.reasonForm.markAllAsTouched();
      return;
    }
    await this.run('gestion.followUp.conflicts.declared', async () => {
      await this.api.declareConflict(
        this.edition(),
        this.submission(),
        candidate.id,
        this.reasonForm.getRawValue().reason,
      );
      this.declaringFor.set(null);
      this.reasonForm.reset();
      this.setDetail(await this.api.submission(this.edition(), this.submission()));
    });
  }

  protected async openDiscussion(): Promise<void> {
    await this.run('gestion.followUp.discussion.opened', async () => {
      this.reviews.set(await this.api.openDiscussion(this.edition(), this.submission()));
    });
  }

  protected async post(): Promise<void> {
    if (this.messageForm.invalid) {
      this.messageForm.markAllAsTouched();
      return;
    }
    await this.run('gestion.followUp.discussion.posted', async () => {
      this.reviews.set(
        await this.api.postChairMessage(
          this.edition(),
          this.submission(),
          this.messageForm.getRawValue().body,
        ),
      );
      this.messageForm.reset();
    });
  }

  protected async decide(): Promise<void> {
    const value = this.decisionForm.getRawValue();
    await this.run('gestion.followUp.decision.saved', async () => {
      this.setDetail(
        await this.api.decide(this.edition(), this.submission(), {
          outcome: value.outcome,
          assigned_type: value.assigned_type || null,
          comment_to_authors: value.comment_to_authors,
        }),
      );
    });
  }

  protected async cancelDecision(): Promise<void> {
    if (!(await this.confirm('gestion.followUp.decision.cancel'))) {
      return;
    }
    await this.run('gestion.followUp.decision.cancel.done', async () => {
      this.setDetail(await this.api.cancelDecision(this.edition(), this.submission()));
    });
  }

  protected async promote(): Promise<void> {
    if (!(await this.confirm('gestion.followUp.decision.promote'))) {
      return;
    }
    await this.run('gestion.followUp.decision.promote.done', async () => {
      this.setDetail(await this.api.promote(this.edition(), this.submission()));
    });
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
      const detail = this.detail();
      if (detail) {
        await this.refreshSide(detail);
      }
      this.status.set(this.translate.instant(done));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }
}
