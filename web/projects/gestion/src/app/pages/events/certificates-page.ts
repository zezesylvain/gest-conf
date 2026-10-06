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
  Certificate,
  CertificateNature,
  CertificateOverview,
  codeMessage,
  ErrorSummary,
  formatInZone,
  LanguageService,
  PageHeader,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { CertificateFilters, EventsApi, eventsUrls } from '../../core/events-api';
import { errorMessages } from '../../core/page-support';
import { CERTIFICATE_NATURES, confirmAction } from './events-support';

const PAGE_SIZE = 25;

/**
 * Attestations (plan L7, K9 à K11) : suivi par nature (éligibles, émises, révoquées,
 * conditions manquantes), émission **par le CO** confiée à la file (`run_jobs`), émission
 * complémentaire après un pointage tardif ; liste, PDF, révocation motivée (RG-17).
 * RG-16 est vérifiée par le serveur à l'émission. `certificates.manage` ; émission et
 * révocation avec réauthentification.
 */
@Component({
  selector: 'gestion-certificates-page',
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
  templateUrl: './certificates-page.html',
  styleUrl: '../page.scss',
})
export class CertificatesPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(EventsApi);
  private readonly dialog = inject(MatDialog);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly natures = CERTIFICATE_NATURES;
  protected readonly overview = signal<CertificateOverview[]>([]);
  protected readonly rows = signal<Certificate[]>([]);
  protected readonly count = signal(0);
  protected readonly page = signal(1);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  protected readonly pages = computed(() => Math.max(1, Math.ceil(this.count() / PAGE_SIZE)));
  protected readonly form = inject(NonNullableFormBuilder).group({
    q: [''],
    nature: [''],
    revoked: [''],
  });

  async ngOnInit(): Promise<void> {
    await Promise.all([this.loadOverview(), this.reload()]);
  }

  private edition(): number {
    return Number(this.editionId());
  }

  protected date(value: string | null): string {
    return value ? formatInZone(value, undefined, this.language.current()) : '—';
  }

  protected problem(row: CertificateOverview): string {
    return codeMessage(this.translate, row.problem);
  }

  protected pdfUrl(row: Certificate): string {
    return eventsUrls.certificatePdf(this.editionId(), row.id);
  }

  protected async issue(row: CertificateOverview): Promise<void> {
    const nature = row.nature as CertificateNature;
    const natureLabel = this.translate.instant(`gestion.certificates.nature.${nature}`);
    const answer = await confirmAction(this.dialog, this.translate, 'gestion.certificates.issue', {
      nature: natureLabel,
      count: row.eligible,
    });
    if (!answer) {
      return;
    }
    await this.run(async () => {
      await this.api.issue(this.edition(), nature);
      this.status.set(
        this.translate.instant('gestion.certificates.issue.done', { nature: natureLabel }),
      );
      await this.loadOverview();
    });
  }

  protected async revoke(row: Certificate): Promise<void> {
    const answer = await confirmAction(
      this.dialog,
      this.translate,
      'gestion.certificates.revoke',
      { name: row.name, reference: row.reference },
      true,
    );
    if (!answer) {
      return;
    }
    await this.run(async () => {
      await this.api.revokeCertificate(this.edition(), row.id, answer.reason.trim());
      this.status.set(
        this.translate.instant('gestion.certificates.revoke.done', { reference: row.reference }),
      );
      await Promise.all([this.loadOverview(), this.reload()]);
    });
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

  protected async refresh(): Promise<void> {
    await Promise.all([this.loadOverview(), this.reload()]);
  }

  private filters(): CertificateFilters {
    const value = this.form.getRawValue();
    const filters: CertificateFilters = { page: this.page(), page_size: PAGE_SIZE };
    if (value.q.trim()) filters.q = value.q.trim();
    if (value.nature) filters.nature = value.nature;
    if (value.revoked) filters.revoked = value.revoked === 'true';
    return filters;
  }

  private async loadOverview(): Promise<void> {
    try {
      this.overview.set(await this.api.overview(this.edition()));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
  }

  private async reload(): Promise<void> {
    try {
      const result = await this.api.certificates(this.edition(), this.filters());
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
