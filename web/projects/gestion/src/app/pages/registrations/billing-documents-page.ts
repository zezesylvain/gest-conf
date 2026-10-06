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
  BillingDocument,
  ErrorSummary,
  formatInZone,
  LanguageService,
  PageHeader,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { EditionApi } from '../../core/edition-api';
import { errorMessages } from '../../core/page-support';
import { documentUrl, money, RegistrationsApi, saveBlob } from '../../core/registrations-api';
import { DOCUMENT_KINDS } from './registrations-support';

const PAGE_SIZE = 25;

/**
 * Factures, avoirs et pro forma de l'édition (plan L6, J8, J12) : numéros sans trou par
 * série, PDF figés (empreinte vérifiée par `check_integrity`), servis par un endpoint
 * authentifié (règle n° 8). Export CSV pour la comptabilité, journalisé, avec
 * réauthentification. Lecture `finance.read`.
 */
@Component({
  selector: 'gestion-billing-documents-page',
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
  templateUrl: './billing-documents-page.html',
  styleUrl: '../page.scss',
  styles: `
    .amount {
      text-align: end;
      white-space: nowrap;
    }
  `,
})
export class BillingDocumentsPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(RegistrationsApi);
  private readonly editions = inject(EditionApi);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly kinds = DOCUMENT_KINDS;
  protected readonly rows = signal<BillingDocument[]>([]);
  protected readonly timezone = signal<string | undefined>(undefined);
  protected readonly count = signal(0);
  protected readonly page = signal(1);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly pages = computed(() => Math.max(1, Math.ceil(this.count() / PAGE_SIZE)));
  protected readonly form = inject(NonNullableFormBuilder).group({ kind: [''] });

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

  protected date(value: string): string {
    return formatInZone(value, this.timezone(), this.language.current());
  }

  protected amount(row: BillingDocument): string {
    return money(row.amount, row.currency, this.language.current());
  }

  protected href(row: BillingDocument): string {
    return documentUrl(this.editionId(), row.registration_id, row.id);
  }

  protected async search(): Promise<void> {
    this.page.set(1);
    await this.reload();
  }

  protected async goTo(page: number): Promise<void> {
    this.page.set(page);
    await this.reload();
  }

  protected async exportCsv(): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    try {
      const kind = this.form.getRawValue().kind || undefined;
      const blob = await this.api.exportDocuments(this.edition(), kind);
      saveBlob(blob, `pieces-${this.editionId()}.csv`);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }

  private async reload(): Promise<void> {
    this.errors.set([]);
    const kind = this.form.getRawValue().kind;
    try {
      const result = await this.api.documents(this.edition(), {
        ...(kind ? { kind } : {}),
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
