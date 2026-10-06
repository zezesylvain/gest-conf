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
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import {
  ErrorSummary,
  formatInZone,
  LanguageService,
  ManageLetter,
  PageHeader,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { EventsApi, LetterFilters } from '../../core/events-api';
import { errorMessages } from '../../core/page-support';
import { LETTER_STATUSES } from './events-support';

const PAGE_SIZE = 25;

/**
 * Lettres d'invitation (plan L7, K12) : demandes des participants, à instruire (émettre ou
 * refuser avec motif) ; lettres émises, révocables. Le numéro de passeport n'apparaît que
 * masqué dans la liste, en clair dans la fiche seulement (effacé 30 jours après
 * l'édition). `letters.manage`.
 */
@Component({
  selector: 'gestion-letters-page',
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
  templateUrl: './letters-page.html',
  styleUrl: '../page.scss',
})
export class LettersPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(EventsApi);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly statuses = LETTER_STATUSES;
  protected readonly rows = signal<ManageLetter[]>([]);
  protected readonly count = signal(0);
  protected readonly page = signal(1);
  protected readonly loading = signal(true);
  protected readonly errors = signal<string[]>([]);
  protected readonly pages = computed(() => Math.max(1, Math.ceil(this.count() / PAGE_SIZE)));
  // Par défaut, les demandes à instruire.
  protected readonly form = inject(NonNullableFormBuilder).group({
    q: [''],
    status: ['requested'],
  });

  async ngOnInit(): Promise<void> {
    await this.reload();
  }

  protected date(value: string | null): string {
    return value ? formatInZone(value, undefined, this.language.current()) : '—';
  }

  protected async search(): Promise<void> {
    this.page.set(1);
    await this.reload();
  }

  protected async reset(): Promise<void> {
    this.form.reset({ q: '', status: '' });
    await this.search();
  }

  protected async goTo(page: number): Promise<void> {
    this.page.set(page);
    await this.reload();
  }

  private filters(): LetterFilters {
    const value = this.form.getRawValue();
    const filters: LetterFilters = { page: this.page(), page_size: PAGE_SIZE };
    if (value.q.trim()) filters.q = value.q.trim();
    if (value.status) filters.status = value.status;
    return filters;
  }

  private async reload(): Promise<void> {
    this.errors.set([]);
    try {
      const result = await this.api.letters(Number(this.editionId()), this.filters());
      this.rows.set(result.results);
      this.count.set(result.count);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }
}
