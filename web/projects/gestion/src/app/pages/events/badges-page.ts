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
import {
  BadgeBatches,
  Category,
  ErrorSummary,
  LanguageService,
  PageHeader,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { EventsApi, eventsUrls } from '../../core/events-api';
import { errorMessages } from '../../core/page-support';
import { RegistrationsApi } from '../../core/registrations-api';
import { label } from '../registrations/registrations-support';

/**
 * Badges imprimables (plan L7, K3) : planches A4 de quatre badges A6, inscriptions
 * confirmées, filtrées par catégorie ; fichiers de 200 badges au plus (bilan de L7.0 : temps
 * d'une requête Passenger). Badges générés à la demande, jamais stockés (le QR est un titre
 * d'accès) ; chaque téléchargement est journalisé. `registrations.read`.
 */
@Component({
  selector: 'gestion-badges-page',
  imports: [
    ReactiveFormsModule,
    TranslatePipe,
    MatButtonModule,
    MatFormFieldModule,
    MatSelectModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './badges-page.html',
  styleUrl: '../page.scss',
  styles: `
    .swatch {
      display: inline-block;
      width: 1rem;
      height: 1rem;
      margin-inline-end: 0.5rem;
      vertical-align: middle;
      border: 1px solid var(--gc-border);
    }
  `,
})
export class BadgesPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(EventsApi);
  private readonly registrations = inject(RegistrationsApi);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly categories = signal<Category[]>([]);
  protected readonly batches = signal<BadgeBatches | null>(null);
  /** Catégorie des lots affichés (les liens portent le filtre du calcul). */
  protected readonly selected = signal('');
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly links = computed(() => {
    const batches = this.batches();
    if (!batches) return [];
    return Array.from({ length: batches.batches }, (_, index) => ({
      number: index + 1,
      from: index * batches.batch_size + 1,
      to: Math.min((index + 1) * batches.batch_size, batches.count),
      url: eventsUrls.badgeSheets(this.editionId(), index + 1, this.selected() || undefined),
    }));
  });
  protected readonly form = inject(NonNullableFormBuilder).group({ category: [''] });

  async ngOnInit(): Promise<void> {
    try {
      this.categories.set(await this.registrations.categories(Number(this.editionId())));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
    await this.compute();
  }

  protected label(category: Category): string {
    return label(category, this.language.current());
  }

  protected async compute(): Promise<void> {
    const category = this.form.getRawValue().category;
    this.busy.set(true);
    this.errors.set([]);
    try {
      this.batches.set(
        await this.api.badgeBatches(Number(this.editionId()), category || undefined),
      );
      this.selected.set(category);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }
}
