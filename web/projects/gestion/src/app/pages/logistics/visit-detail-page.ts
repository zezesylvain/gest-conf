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
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import {
  Equipment,
  ErrorSummary,
  LanguageService,
  ManageVisit,
  MeStore,
  PageHeader,
  TravelMeans,
  VisitStatus,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { LogisticsApi } from '../../core/logistics-api';
import { editionCapabilities, errorMessages } from '../../core/page-support';
import { EQUIPMENT, TRAVEL_MEANS, VISIT_STATUSES } from './logistics-support';

/**
 * Fiche de venue d'un intervenant invité (plan L8, N6) : sa part (besoins, voyages,
 * demandes) et celle du CO (hôtel, nuits, prise en charge, note interne jamais servie à
 * l'intervenant). Heures **en heure locale de l'édition** (D13). Écriture `logistics.write`.
 */
@Component({
  selector: 'gestion-visit-detail-page',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TranslatePipe,
    MatButtonModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './visit-detail-page.html',
  styleUrl: '../page.scss',
  styles: `
    fieldset {
      border: 1px solid var(--gc-border);
      border-radius: 0.5rem;
      padding: 0.75rem;
    }
    .checks {
      display: flex;
      flex-wrap: wrap;
      gap: 0.25rem 1rem;
    }
  `,
})
export class VisitDetailPage implements OnInit {
  readonly editionId = input.required<string>();
  readonly userId = input.required<string>();

  private readonly api = inject(LogisticsApi);
  private readonly meStore = inject(MeStore);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly equipmentList = EQUIPMENT;
  protected readonly means = TRAVEL_MEANS;
  protected readonly statuses = VISIT_STATUSES;
  protected readonly visit = signal<ManageVisit | null>(null);
  protected readonly needs = signal<Equipment[]>([]);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  protected readonly canWrite = computed(() =>
    editionCapabilities(this.meStore, this.editionId()).includes('logistics.write'),
  );

  protected readonly form = inject(NonNullableFormBuilder).group({
    technical_note: ['', Validators.maxLength(500)],
    arrival_local: [''],
    arrival_means: ['' as TravelMeans | ''],
    arrival_reference: ['', Validators.maxLength(60)],
    departure_local: [''],
    departure_means: ['' as TravelMeans | ''],
    departure_reference: ['', Validators.maxLength(60)],
    accommodation_needed: [false],
    transfer_needed: [false],
    speaker_note: ['', Validators.maxLength(1000)],
    hotel: ['', Validators.maxLength(150)],
    check_in: [''],
    check_out: [''],
    status: ['to_arrange' as VisitStatus],
    internal_note: ['', Validators.maxLength(2000)],
  });

  async ngOnInit(): Promise<void> {
    try {
      this.show(await this.api.visit(Number(this.editionId()), Number(this.userId())));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }

  protected toggleNeed(item: Equipment, checked: boolean): void {
    const current = this.needs().filter((need) => need !== item);
    this.needs.set(checked ? [...current, item] : current);
  }

  protected missing(item: string): boolean {
    return this.visit()?.missing_equipment.includes(item) ?? false;
  }

  protected async save(): Promise<void> {
    const visit = this.visit();
    if (!visit || this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const value = this.form.getRawValue();
    this.busy.set(true);
    this.errors.set([]);
    this.status.set('');
    try {
      const saved = await this.api.updateVisit(Number(this.editionId()), visit.speaker.id, {
        ...value,
        technical_needs: this.needs(),
        arrival_local: value.arrival_local || null,
        departure_local: value.departure_local || null,
        check_in: value.check_in || null,
        check_out: value.check_out || null,
      });
      this.show(saved);
      this.status.set(this.translate.instant('gestion.speakers.detail.saved'));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error, this.form));
    } finally {
      this.busy.set(false);
    }
  }

  private show(visit: ManageVisit): void {
    this.visit.set(visit);
    this.needs.set([...visit.technical_needs]);
    this.form.reset({
      technical_note: visit.technical_note,
      arrival_local: visit.arrival_local ?? '',
      arrival_means: visit.arrival_means as TravelMeans | '',
      arrival_reference: visit.arrival_reference,
      departure_local: visit.departure_local ?? '',
      departure_means: visit.departure_means as TravelMeans | '',
      departure_reference: visit.departure_reference,
      accommodation_needed: visit.accommodation_needed,
      transfer_needed: visit.transfer_needed,
      speaker_note: visit.speaker_note,
      hotel: visit.hotel,
      check_in: visit.check_in ?? '',
      check_out: visit.check_out ?? '',
      status: visit.status,
      internal_note: visit.internal_note,
    });
    if (this.canWrite()) {
      this.form.enable();
    } else {
      this.form.disable();
    }
  }
}
