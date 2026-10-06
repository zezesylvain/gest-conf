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
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import {
  ErrorSummary,
  formatInZone,
  LanguageService,
  PageHeader,
  PaymentList,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { EditionApi } from '../../core/edition-api';
import { errorMessages } from '../../core/page-support';
import { money, PaymentFilters, RegistrationsApi, saveBlob } from '../../core/registrations-api';
import { PAYMENT_METHODS, PAYMENT_PROVIDERS, PAYMENT_STATUSES } from './registrations-support';

const PAGE_SIZE = 25;

/**
 * Paiements de l'édition (plan L6, J12) : rapprochement des encaissements (fournisseur,
 * statut, référence du fournisseur, saisie manuelle) ; export CSV journalisé, avec
 * réauthentification. Lecture `finance.read` ; aucune action ici : un paiement ne se crée
 * que sur webhook vérifié (RG-15) ou par saisie manuelle depuis l'inscription (J7).
 */
@Component({
  selector: 'gestion-payments-page',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TranslatePipe,
    MatButtonModule,
    MatFormFieldModule,
    MatSelectModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './payments-page.html',
  styleUrl: '../page.scss',
  styles: `
    .amount {
      text-align: end;
      white-space: nowrap;
    }
  `,
})
export class PaymentsPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(RegistrationsApi);
  private readonly editions = inject(EditionApi);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly statuses = PAYMENT_STATUSES;
  protected readonly providers = PAYMENT_PROVIDERS;
  protected readonly methods = PAYMENT_METHODS;
  protected readonly rows = signal<PaymentList[]>([]);
  protected readonly timezone = signal<string | undefined>(undefined);
  protected readonly count = signal(0);
  protected readonly page = signal(1);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly pages = computed(() => Math.max(1, Math.ceil(this.count() / PAGE_SIZE)));
  protected readonly form = inject(NonNullableFormBuilder).group({
    status: [''],
    provider: [''],
    method: [''],
  });

  async ngOnInit(): Promise<void> {
    try {
      this.timezone.set((await this.editions.edition(this.edition())).timezone);
    } catch {
      // Fuseau facultatif ici : dates à l'heure du navigateur.
    }
    await this.reload();
  }

  private edition(): number {
    return Number(this.editionId());
  }

  protected date(value: string | null | undefined): string {
    return value ? formatInZone(value, this.timezone(), this.language.current()) : '—';
  }

  protected amount(row: PaymentList): string {
    return money(row.amount, row.currency, this.language.current());
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

  protected async exportCsv(): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    try {
      const blob = await this.api.exportPayments(this.edition(), this.currentFilters());
      saveBlob(blob, `paiements-${this.editionId()}.csv`);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }

  private currentFilters(): PaymentFilters {
    const value = this.form.getRawValue();
    const filters: PaymentFilters = {};
    if (value.status) filters.status = value.status;
    if (value.provider) filters.provider = value.provider;
    if (value.method) filters.method = value.method;
    return filters;
  }

  private async reload(): Promise<void> {
    this.errors.set([]);
    try {
      const result = await this.api.payments(this.edition(), {
        ...this.currentFilters(),
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
