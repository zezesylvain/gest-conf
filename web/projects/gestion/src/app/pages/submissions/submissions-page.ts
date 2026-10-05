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
  formatInZone,
  LanguageService,
  MeStore,
  PageHeader,
  SubmissionManage,
  SubmissionStatus,
  SubmissionType,
  Track,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { EditionApi } from '../../core/edition-api';
import { editionCapabilities, errorMessages } from '../../core/page-support';
import { exportUrl, SubmissionFilters, SubmissionsApi } from '../../core/submissions-api';

const PAGE_SIZE = 25;

/** Statuts de l'étude (M6), dans l'ordre du workflow. */
export const STATUSES: readonly SubmissionStatus[] = [
  'draft',
  'submitted',
  'screening',
  'under_review',
  'reviewed',
  'accepted',
  'accepted_minor',
  'waitlist',
  'rejected',
  'revision_requested',
  'camera_ready_received',
  'confirmed',
  'scheduled',
  'presented',
  'published',
  'withdrawn',
];

type Ordering = NonNullable<SubmissionFilters['ordering']>;
export const ORDERINGS: readonly Ordering[] = [
  'reference',
  '-submitted_at',
  '-updated_at',
  'title',
];

/**
 * Soumissions de l'édition (plan L3 §5, F10) : liste filtrée (statuts, thématique, type,
 * langue, recherche, doublons possibles F15), triée, paginée ; export CSV des mêmes filtres
 * (`submissions.export`, journalisé). Identité des auteurs visible : rôles de `submissions.read` seulement (le
 * serveur en décide ; un relecteur n'aura jamais cette vue, RG-04).
 */
@Component({
  selector: 'gestion-submissions-page',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TranslatePipe,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatCheckboxModule,
    MatButtonModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './submissions-page.html',
  styleUrl: '../page.scss',
  styles: `
    .title {
      max-width: 28rem;
    }
    .extension {
      white-space: nowrap;
    }
    .badge.warning {
      border-color: var(--gc-warning, #b26a00);
      color: var(--gc-warning, #b26a00);
    }
  `,
})
export class SubmissionsPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(SubmissionsApi);
  private readonly editions = inject(EditionApi);
  private readonly meStore = inject(MeStore);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly statuses = STATUSES;
  protected readonly orderings = ORDERINGS;
  protected readonly rows = signal<SubmissionManage[]>([]);
  protected readonly tracks = signal<Track[]>([]);
  protected readonly types = signal<SubmissionType[]>([]);
  protected readonly timezone = signal<string | undefined>(undefined);
  protected readonly count = signal(0);
  protected readonly page = signal(1);
  protected readonly loading = signal(true);
  protected readonly errors = signal<string[]>([]);
  protected readonly filters = signal<SubmissionFilters>({});
  protected readonly pages = computed(() => Math.max(1, Math.ceil(this.count() / PAGE_SIZE)));
  protected readonly canExport = computed(() =>
    editionCapabilities(this.meStore, this.editionId()).includes('submissions.export'),
  );
  protected readonly exportHref = computed(() => exportUrl(this.editionId(), this.filters()));
  protected readonly form = inject(NonNullableFormBuilder).group({
    q: [''],
    status: [[] as SubmissionStatus[]],
    track: [''],
    submission_type: [''],
    language: [''],
    duplicates: [false],
    ordering: ['reference' as Ordering],
  });

  async ngOnInit(): Promise<void> {
    const id = Number(this.editionId());
    try {
      const [edition, tracks, types] = await Promise.all([
        this.editions.edition(id),
        this.editions.tracks(id),
        this.editions.submissionTypes(id),
      ]);
      this.timezone.set(edition.timezone);
      this.tracks.set(tracks);
      this.types.set(types);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
    await this.reload();
  }

  protected date(value: string | null | undefined): string {
    return value ? formatInZone(value, this.timezone(), this.language.current()) : '—';
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

  /** Filtres non vides du formulaire, tels que les attend l'API (et l'export). */
  private currentFilters(): SubmissionFilters {
    const value = this.form.getRawValue();
    const filters: SubmissionFilters = { ordering: value.ordering };
    if (value.q.trim()) filters.q = value.q.trim();
    if (value.status.length) filters.status = value.status;
    if (value.track) filters.track = value.track;
    if (value.submission_type) filters.submission_type = value.submission_type;
    if (value.language) filters.language = value.language;
    if (value.duplicates) filters.duplicates = true;
    return filters;
  }

  private async reload(): Promise<void> {
    this.errors.set([]);
    const filters = this.currentFilters();
    this.filters.set(filters);
    try {
      const result = await this.api.list(Number(this.editionId()), {
        ...filters,
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
