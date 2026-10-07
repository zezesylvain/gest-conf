import { ChangeDetectionStrategy, Component, inject, input, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ErrorSummary, LanguageService, ManageVisit, PageHeader } from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { LogisticsApi } from '../../core/logistics-api';
import { errorMessages } from '../../core/page-support';
import { localLabel } from './logistics-support';

/**
 * Venues des intervenants invités (plan L8, N6 ; `logistics.read`) : prise en charge,
 * arrivée et départ à l'heure de l'édition, hébergement, et signal d'équipement manquant
 * dans une salle où l'intervenant passe (programme **publié**).
 */
@Component({
  selector: 'gestion-speakers-page',
  imports: [RouterLink, TranslatePipe, ErrorSummary, PageHeader],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './speakers-page.html',
  styleUrl: '../page.scss',
})
export class SpeakersPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(LogisticsApi);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly visits = signal<ManageVisit[]>([]);
  protected readonly loading = signal(true);
  protected readonly errors = signal<string[]>([]);

  async ngOnInit(): Promise<void> {
    try {
      this.visits.set(await this.api.visits(Number(this.editionId())));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }

  protected local(value: string | null): string {
    return localLabel(value, this.language.current());
  }

  protected equipment(items: readonly string[]): string {
    return items
      .map((item) => this.translate.instant(`gestion.speakers.equipment.${item}`))
      .join(', ');
  }
}
