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
import { RouterLink } from '@angular/router';
import {
  ErrorSummary,
  FinanceDashboard,
  LanguageService,
  MeStore,
  PageHeader,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { editionCapabilities, errorMessages } from '../../core/page-support';
import { money, RegistrationsApi } from '../../core/registrations-api';
import { label } from './registrations-support';

/**
 * Tableau de bord financier (plan L6, J12) : encaissé, remboursé, net, impayés (commandes
 * en attente), remboursements restant dus, répartitions par catégorie et par moyen, pièces
 * émises, points à traiter (paiements sans inscription active, factures en attente des
 * mentions de facturation). Lecture `finance.read` ; émission des factures en attente :
 * `registrations.manage`, avec réauthentification.
 */
@Component({
  selector: 'gestion-finance-page',
  imports: [RouterLink, TranslatePipe, MatButtonModule, ErrorSummary, PageHeader],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './finance-page.html',
  styleUrl: '../page.scss',
  styles: `
    .figures {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
      gap: 0.75rem;
      margin: 0;
    }
    .figures div {
      border: 1px solid var(--gc-border);
      border-radius: 0.5rem;
      padding: 0.75rem;
    }
    .figures dt {
      font-size: 0.875rem;
    }
    .figures dd {
      margin: 0.25rem 0 0;
      font-size: 1.25rem;
      font-weight: 600;
    }
    .amount {
      text-align: end;
      white-space: nowrap;
    }
  `,
})
export class FinancePage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(RegistrationsApi);
  private readonly meStore = inject(MeStore);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly dashboard = signal<FinanceDashboard | null>(null);
  /** Mentions de facturation complètes (sans elles, aucune facture ne s'émet, Q8). */
  protected readonly profileComplete = signal(true);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  protected readonly canManage = computed(() =>
    editionCapabilities(this.meStore, this.editionId()).includes('registrations.manage'),
  );

  async ngOnInit(): Promise<void> {
    await this.reload();
    this.loading.set(false);
  }

  private edition(): number {
    return Number(this.editionId());
  }

  protected amount(value: string | number): string {
    return money(value, this.dashboard()?.currency ?? 'XOF', this.language.current());
  }

  protected itemLabel(item: { label_fr: string; label_en?: string }): string {
    return label(item, this.language.current());
  }

  protected async issuePending(): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    this.status.set('');
    try {
      const result = await this.api.issuePendingInvoices(this.edition());
      this.status.set(this.translate.instant('gestion.finance.issued', { count: result.issued }));
      await this.reload();
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }

  private async reload(): Promise<void> {
    try {
      const [dashboard, profile] = await Promise.all([
        this.api.dashboard(this.edition()),
        this.api.billingProfile(this.edition()),
      ]);
      this.dashboard.set(dashboard);
      this.profileComplete.set(profile.is_complete);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
  }
}
