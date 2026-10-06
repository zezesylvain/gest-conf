import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  OnInit,
  signal,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { RouterLink } from '@angular/router';
import {
  CertificateOverview,
  CheckinSummary,
  ConfirmDialog,
  ConfirmDialogData,
  ConfirmDialogResult,
  Edition,
  EditionStatus,
  ErrorSummary,
  FinanceDashboard,
  formatInZone,
  KeyDate,
  LanguageService,
  MeStore,
  PageHeader,
  ProgramBoard,
  ReviewProgress,
  SubmissionStats,
  SubmissionStatus,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { firstValueFrom } from 'rxjs';

import { EditionApi } from '../../core/edition-api';
import { EventsApi } from '../../core/events-api';
import { editionTitle } from '../../core/managed-editions';
import { editionCapabilities, errorMessages } from '../../core/page-support';
import { ProgramApi } from '../../core/program-api';
import { money, RegistrationsApi } from '../../core/registrations-api';
import { ReviewsApi } from '../../core/reviews-api';
import { SubmissionsApi } from '../../core/submissions-api';

interface CheckItem {
  label: string;
  done: boolean;
  link: string;
}

/**
 * Tableau de bord de l'édition (squelette US-12, plan L1 §10.3) : statut et publication,
 * paramétrage à compléter, dates clés, invitations en attente, état de la 2FA ; compteurs
 * de soumissions par statut avec `submissions.read` (plan L3) ; avancement de l'évaluation
 * avec `reviews.manage` (plan L4 : divergences, retards) ; programme avec `program.read`
 * (plan L5 : à programmer, conflits, modifications non publiées) ; inscriptions avec
 * `registrations.read` et finances avec `finance.read` (plan L6, J12) ; jour J avec
 * `checkin.scan`, attestations avec `certificates.manage`, lettres à instruire avec
 * `letters.manage` (plan L7, K15). La liste de contrôle est
 * indicative : le serveur revérifie les préconditions à la publication (`edition_incomplete`).
 */
@Component({
  selector: 'gestion-dashboard-page',
  imports: [RouterLink, TranslatePipe, MatButtonModule, PageHeader, ErrorSummary],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './dashboard-page.html',
  styleUrl: '../page.scss',
})
export class DashboardPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(EditionApi);
  private readonly submissions = inject(SubmissionsApi);
  private readonly reviewsApi = inject(ReviewsApi);
  private readonly programApi = inject(ProgramApi);
  private readonly registrationsApi = inject(RegistrationsApi);
  private readonly eventsApi = inject(EventsApi);
  private readonly meStore = inject(MeStore);
  private readonly dialog = inject(MatDialog);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly edition = signal<Edition | null>(null);
  protected readonly keyDates = signal<KeyDate[]>([]);
  protected readonly checklist = signal<CheckItem[]>([]);
  protected readonly pendingInvitations = signal<number | null>(null);
  protected readonly submissionStats = signal<SubmissionStats | null>(null);
  protected readonly reviewProgress = signal<ReviewProgress | null>(null);
  protected readonly program = signal<ProgramBoard | null>(null);
  /** Inscriptions confirmées et en attente (`registrations.read`). */
  protected readonly registrations = signal<{ confirmed: number; pending: number } | null>(null);
  protected readonly finance = signal<FinanceDashboard | null>(null);
  /** Jour J (plan L7) : pointages, attestations par nature, lettres à instruire. */
  protected readonly checkin = signal<CheckinSummary | null>(null);
  protected readonly certificates = signal<CertificateOverview[] | null>(null);
  protected readonly lettersToReview = signal<number | null>(null);
  protected readonly certificatesIssued = computed(() =>
    (this.certificates() ?? []).reduce((sum, row) => sum + row.issued, 0),
  );
  /** Évaluations en retard, tous relecteurs confondus. */
  protected readonly lateReviews = computed(() =>
    (this.reviewProgress()?.reviewers ?? []).reduce((sum, reviewer) => sum + reviewer.late, 0),
  );
  /** Soumissions de l'évaluation, par statut (compteurs des soumissions). */
  protected readonly reviewCounts = computed(() => {
    const byStatus = this.submissionStats()?.by_status ?? {};
    return {
      screening: byStatus['screening'] ?? 0,
      underReview: byStatus['under_review'] ?? 0,
      reviewed: byStatus['reviewed'] ?? 0,
    };
  });
  /** Statuts non nuls, dans l'ordre du serveur (celui du workflow). */
  protected readonly statusCounts = computed(() =>
    Object.entries(this.submissionStats()?.by_status ?? {})
      .filter(([, count]) => count > 0)
      .map(([status, count]) => ({ status: status as SubmissionStatus, count })),
  );
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  protected readonly busy = signal(false);
  protected readonly capabilities = computed(() =>
    editionCapabilities(this.meStore, this.editionId()),
  );
  protected readonly mfaEnabled = computed(() => this.meStore.me()?.mfa_enabled === true);

  async ngOnInit(): Promise<void> {
    await this.load();
  }

  protected title(edition: Edition): string {
    return editionTitle(edition, this.language.current());
  }

  protected at(keyDate: KeyDate, edition: Edition): string {
    return formatInZone(keyDate.at, edition.timezone, this.language.current());
  }

  protected amount(value: string, currency: string): string {
    return money(value, currency, this.language.current());
  }

  protected can(capability: string): boolean {
    return this.capabilities().includes(capability as never);
  }

  protected async changeStatus(target: EditionStatus): Promise<void> {
    const data: ConfirmDialogData = {
      title: this.translate.instant(`gestion.dashboard.${target}.title`),
      message: this.translate.instant(`gestion.dashboard.${target}.message`),
      confirmLabel: this.translate.instant(`gestion.dashboard.${target}.confirm`),
    };
    const ref = this.dialog.open<ConfirmDialog, ConfirmDialogData, ConfirmDialogResult>(
      ConfirmDialog,
      { data, width: '30rem' },
    );
    const result = await firstValueFrom(ref.afterClosed());
    if (!result) {
      return;
    }
    this.errors.set([]);
    this.busy.set(true);
    try {
      this.edition.set(await this.api.changeStatus(Number(this.editionId()), target));
      this.status.set(this.translate.instant(`gestion.dashboard.${target}.done`));
      await this.meStore.load().catch(() => undefined);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }

  private async load(): Promise<void> {
    const id = Number(this.editionId());
    try {
      const [edition, keyDates, tracks, types] = await Promise.all([
        this.api.edition(id),
        this.api.keyDates(id),
        this.api.tracks(id),
        this.api.submissionTypes(id),
      ]);
      this.edition.set(edition);
      this.keyDates.set(keyDates);
      const codes = new Set(keyDates.map((item) => item.code));
      const base = `/editions/${id}/parametrage`;
      this.checklist.set([
        {
          label: 'gestion.dashboard.check.titles',
          done: !!edition.title_fr && !!edition.title_en,
          link: `${base}/general`,
        },
        {
          label: 'gestion.dashboard.check.dates',
          done: !!edition.start_date && !!edition.end_date,
          link: `${base}/general`,
        },
        {
          label: 'gestion.dashboard.check.tracks',
          done: tracks.some((item) => item.is_active !== false),
          link: `${base}/thematiques`,
        },
        {
          label: 'gestion.dashboard.check.types',
          done: types.some((item) => item.is_active !== false),
          link: `${base}/types`,
        },
        {
          label: 'gestion.dashboard.check.call',
          done: codes.has('call_open') && codes.has('call_close'),
          link: `${base}/calendrier`,
        },
      ]);
      if (this.can('members.read')) {
        const page = await this.api.invitations({
          edition_id: id,
          status: 'pending',
          page_size: 1,
        });
        this.pendingInvitations.set(page.count ?? 0);
      }
      if (this.can('submissions.read')) {
        this.submissionStats.set(await this.submissions.stats(id));
      }
      if (this.can('reviews.manage')) {
        this.reviewProgress.set(await this.reviewsApi.progress(id));
      }
      if (this.can('program.read')) {
        this.program.set(await this.programApi.board(id));
      }
      if (this.can('finance.read')) {
        const finance = await this.registrationsApi.dashboard(id);
        this.finance.set(finance);
        this.registrations.set(finance.registrations);
      } else if (this.can('registrations.read')) {
        const [confirmed, pending] = await Promise.all(
          (['confirmed', 'pending'] as const).map((status) =>
            this.registrationsApi.list(id, { status, page_size: 1 }),
          ),
        );
        this.registrations.set({ confirmed: confirmed.count, pending: pending.count });
      }
      if (this.can('checkin.scan')) {
        this.checkin.set(await this.eventsApi.summary(id));
      }
      if (this.can('certificates.manage')) {
        this.certificates.set(await this.eventsApi.overview(id));
      }
      if (this.can('letters.manage')) {
        const letters = await this.eventsApi.letters(id, { status: 'requested', page_size: 1 });
        this.lettersToReview.set(letters.count);
      }
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
  }
}
