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
import {
  AuditEntry,
  ErrorSummary,
  formatInZone,
  LanguageService,
  ManageAuditList$Params,
  PageHeader,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { EditionApi } from '../../core/edition-api';
import { errorMessages } from '../../core/page-support';

const PAGE_SIZE = 25;

/**
 * Journal de l'édition (plan L1 §7.4, RG-17) : filtrable (action exacte ou préfixe
 * « domaine. », type d'objet, période), paginé, détail avant/après. Lecture seule ; sans
 * IP ni navigateur. Les entrées sans édition (connexions) ne figurent pas ici.
 */
@Component({
  selector: 'gestion-audit-page',
  imports: [
    ReactiveFormsModule,
    TranslatePipe,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './audit-page.html',
  styleUrl: '../page.scss',
  styles: `
    pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      font-size: 0.85rem;
    }
    details summary {
      cursor: pointer;
      color: var(--gc-primary);
    }
  `,
})
export class AuditPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(EditionApi);
  private readonly translate = inject(TranslateService);
  private readonly language = inject(LanguageService);

  protected readonly entries = signal<AuditEntry[]>([]);
  protected readonly count = signal(0);
  protected readonly page = signal(1);
  protected readonly loading = signal(true);
  protected readonly errors = signal<string[]>([]);
  protected readonly pages = computed(() => Math.max(1, Math.ceil(this.count() / PAGE_SIZE)));
  protected readonly form = inject(NonNullableFormBuilder).group({
    action: [''],
    object_type: [''],
    since: [''],
    until: [''],
  });

  async ngOnInit(): Promise<void> {
    await this.reload();
  }

  protected date(value: string): string {
    return formatInZone(value, undefined, this.language.current());
  }

  protected json(value: unknown): string {
    return value === null || value === undefined ? '—' : JSON.stringify(value, null, 2);
  }

  protected actor(entry: AuditEntry): string {
    return (
      entry.actor_name || this.translate.instant(`gestion.audit.actorKind.${entry.actor_kind}`)
    );
  }

  protected async search(): Promise<void> {
    this.page.set(1);
    await this.reload();
  }

  protected async goTo(page: number): Promise<void> {
    this.page.set(page);
    await this.reload();
  }

  private async reload(): Promise<void> {
    this.errors.set([]);
    const filters = this.form.getRawValue();
    const params: ManageAuditList$Params = {
      edition_id: Number(this.editionId()),
      page: this.page(),
      page_size: PAGE_SIZE,
    };
    if (filters.action.trim()) {
      params.action = filters.action.trim();
    }
    if (filters.object_type.trim()) {
      params.object_type = filters.object_type.trim();
    }
    // Bornes de période en jours entiers, heure du navigateur, transmises en UTC (ISO 8601).
    if (filters.since) {
      params.since = new Date(`${filters.since}T00:00:00`).toISOString();
    }
    if (filters.until) {
      const end = new Date(`${filters.until}T00:00:00`);
      end.setDate(end.getDate() + 1);
      params.until = end.toISOString();
    }
    try {
      const result = await this.api.audit(params);
      this.entries.set(result.results);
      this.count.set(result.count);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }
}
