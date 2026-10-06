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
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import {
  CheckinListItem,
  CheckinSummary,
  ErrorSummary,
  formatInZone,
  LanguageService,
  PageHeader,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { CheckinFilters, EventsApi } from '../../core/events-api';
import { errorMessages } from '../../core/page-support';
import { saveBlob } from '../../core/registrations-api';
import { confirmAction } from './events-support';

const PAGE_SIZE = 25;

/**
 * Présences à l'accueil (plan L7, K4) : pointages par nom ou référence, annulation d'un
 * pointage erroné (motif, journal : rien n'est supprimé, la personne peut être pointée de
 * nouveau), export CSV journalisé avec réauthentification. `checkin.manage`.
 */
@Component({
  selector: 'gestion-attendance-page',
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
  templateUrl: './attendance-page.html',
  styleUrl: '../page.scss',
})
export class AttendancePage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(EventsApi);
  private readonly dialog = inject(MatDialog);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly rows = signal<CheckinListItem[]>([]);
  protected readonly summary = signal<CheckinSummary | null>(null);
  protected readonly count = signal(0);
  protected readonly page = signal(1);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  protected readonly pages = computed(() => Math.max(1, Math.ceil(this.count() / PAGE_SIZE)));
  protected readonly form = inject(NonNullableFormBuilder).group({
    q: [''],
    cancelled: [''],
  });

  async ngOnInit(): Promise<void> {
    await Promise.all([this.reload(), this.loadSummary()]);
  }

  private edition(): number {
    return Number(this.editionId());
  }

  protected date(value: string | null): string {
    return value ? formatInZone(value, undefined, this.language.current()) : '—';
  }

  protected category(row: CheckinListItem): string {
    const person = row.registration;
    return (
      (this.language.current() === 'en' && person.category_label_en) || person.category_label_fr
    );
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

  protected async cancel(row: CheckinListItem): Promise<void> {
    const answer = await confirmAction(
      this.dialog,
      this.translate,
      'gestion.attendance.cancel',
      { name: row.registration.name },
      true,
    );
    if (!answer) {
      return;
    }
    await this.run(async () => {
      await this.api.cancelCheckin(this.edition(), row.id, answer.reason.trim());
      this.status.set(
        this.translate.instant('gestion.attendance.cancel.done', { name: row.registration.name }),
      );
      await Promise.all([this.reload(), this.loadSummary()]);
    });
  }

  protected async exportCsv(): Promise<void> {
    await this.run(async () => {
      saveBlob(await this.api.exportCheckins(this.edition()), `presences-${this.editionId()}.csv`);
    });
  }

  private filters(): CheckinFilters {
    const value = this.form.getRawValue();
    const filters: CheckinFilters = { page: this.page(), page_size: PAGE_SIZE };
    if (value.q.trim()) filters.q = value.q.trim();
    if (value.cancelled) filters.cancelled = value.cancelled === 'true';
    return filters;
  }

  private async loadSummary(): Promise<void> {
    try {
      this.summary.set(await this.api.summary(this.edition()));
    } catch {
      // Compteurs facultatifs : la liste suffit.
    }
  }

  private async reload(): Promise<void> {
    this.errors.set([]);
    try {
      const result = await this.api.checkins(this.edition(), this.filters());
      this.rows.set(result.results);
      this.count.set(result.count);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }

  private async run(action: () => Promise<void>): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    this.status.set('');
    try {
      await action();
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }
}
