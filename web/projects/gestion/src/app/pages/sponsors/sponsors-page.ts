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
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { Router, RouterLink } from '@angular/router';
import {
  ErrorSummary,
  LanguageService,
  MeStore,
  PageHeader,
  Sponsor,
  SponsorLevel,
  Sponsors,
  SponsorStatus,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { editionCapabilities, errorMessages } from '../../core/page-support';
import { money, saveBlob } from '../../core/registrations-api';
import { SponsorsApi } from '../../core/sponsors-api';
import { levelName, SPONSOR_STATUSES } from './sponsors-support';

/**
 * Partenaires (plan L8, N5 ; `sponsors.read`, écriture `sponsors.write`) : totaux convenus
 * et reçus, effectifs par statut, liste avec niveau, contreparties livrées et publication ;
 * export contacts compris (réauthentification et journal, RG-17) ; création d'une fiche,
 * complétée ensuite dans la fiche.
 */
@Component({
  selector: 'gestion-sponsors-page',
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
  templateUrl: './sponsors-page.html',
  styleUrl: '../page.scss',
  styles: `
    .amount {
      text-align: end;
      white-space: nowrap;
    }
  `,
})
export class SponsorsPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(SponsorsApi);
  private readonly meStore = inject(MeStore);
  private readonly router = inject(Router);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly statuses = SPONSOR_STATUSES;
  protected readonly data = signal<Sponsors | null>(null);
  protected readonly levels = signal<SponsorLevel[]>([]);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly canWrite = computed(() =>
    editionCapabilities(this.meStore, this.editionId()).includes('sponsors.write'),
  );

  protected readonly form = inject(NonNullableFormBuilder).group({
    name: ['', [Validators.required, Validators.maxLength(150)]],
    level: [null as number | null],
    status: ['prospect' as SponsorStatus],
  });

  async ngOnInit(): Promise<void> {
    const edition = this.edition();
    try {
      const [data, levels] = await Promise.all([
        this.api.sponsors(edition),
        this.api.levels(edition),
      ]);
      this.data.set(data);
      this.levels.set(levels);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }

  private edition(): number {
    return Number(this.editionId());
  }

  protected amount(value: string | null | undefined): string {
    return money(value, this.data()?.totals.currency ?? 'XOF', this.language.current());
  }

  protected levelLabel(levelId: number | null): string {
    const level = this.levels().find((item) => item.id === levelId);
    return levelName(level, this.language.current()) || '—';
  }

  protected levelOption(level: SponsorLevel): string {
    return levelName(level, this.language.current());
  }

  protected count(status: SponsorStatus): number {
    return this.data()?.totals.by_status[status] ?? 0;
  }

  protected benefits(sponsor: Sponsor): string {
    return this.translate.instant('gestion.sponsors.benefitsCount', {
      delivered: sponsor.benefits_delivered,
      due: sponsor.benefits_due,
    });
  }

  protected async create(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const value = this.form.getRawValue();
    this.busy.set(true);
    this.errors.set([]);
    try {
      const sponsor = await this.api.create(this.edition(), {
        name: value.name.trim(),
        level: value.level,
        status: value.status,
      });
      await this.router.navigate(['/editions', this.editionId(), 'partenaires', sponsor.id]);
    } catch (error) {
      // Erreurs de champ du serveur au résumé : ce formulaire n'en affiche pas sous ses champs.
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }

  protected async export(fileFormat: 'csv' | 'xlsx'): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    try {
      saveBlob(
        await this.api.exportSponsors(this.edition(), fileFormat),
        `partenaires.${fileFormat}`,
      );
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }
}
