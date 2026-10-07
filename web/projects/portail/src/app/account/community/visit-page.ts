import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  OnInit,
  signal,
} from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import {
  Equipment,
  ErrorSummary,
  LanguageService,
  MeStore,
  MyVisit,
  PageHeader,
  TravelMeans,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { CommunityService } from './community.service';
import { EQUIPMENT, messagesOf, TRAVEL_MEANS } from './community-support';
import { DietaryCard } from './dietary-card';

/**
 * « Ma venue » de l'intervenant invité (plan L8, N6) : besoins techniques, voyages,
 * hébergement et transfert demandés, message au comité ; heures **à l'heure de la
 * conférence** (D13). En lecture : ce que le comité a réservé (hôtel, nuits, prise en
 * charge) ; jamais sa note interne (le serveur ne la renvoie pas). Carte « Régime ».
 */
@Component({
  selector: 'portail-visit-page',
  imports: [
    ReactiveFormsModule,
    TranslatePipe,
    MatButtonModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    ErrorSummary,
    PageHeader,
    DietaryCard,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './visit-page.html',
  styleUrl: './community.scss',
})
export class VisitPage implements OnInit {
  private readonly service = inject(CommunityService);
  private readonly meStore = inject(MeStore);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly equipment = EQUIPMENT;
  protected readonly means = TRAVEL_MEANS;
  protected readonly visit = signal<MyVisit | null>(null);
  protected readonly needs = signal<Equipment[]>([]);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  /** Éditions où le compte est intervenant invité ; la plus récente d'abord. */
  protected readonly editions = computed(() =>
    (this.meStore.me()?.editions ?? [])
      .filter((edition) => edition.roles.some((item) => item.role === 'SPEAKER'))
      .sort((a, b) => b.year - a.year),
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
  });

  async ngOnInit(): Promise<void> {
    if (!this.meStore.me()) {
      await this.meStore.load().catch(() => undefined);
    }
    const edition = this.editions()[0];
    if (edition) {
      try {
        this.show(await this.service.visit(edition.id));
      } catch (error) {
        this.errors.set(messagesOf(this.translate, error));
      }
    }
    this.loading.set(false);
  }

  protected toggleNeed(item: Equipment, checked: boolean): void {
    const current = this.needs().filter((need) => need !== item);
    this.needs.set(checked ? [...current, item] : current);
  }

  protected day(value: string | null): string {
    if (!value) return '—';
    return new Intl.DateTimeFormat(this.language.current() === 'en' ? 'en-GB' : 'fr-FR', {
      dateStyle: 'medium',
      timeZone: 'UTC',
    }).format(new Date(`${value}T00:00:00Z`));
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
      this.show(
        await this.service.updateVisit(visit.edition_id, {
          ...value,
          technical_needs: this.needs(),
          arrival_local: value.arrival_local || null,
          departure_local: value.departure_local || null,
        }),
      );
      this.status.set(this.translate.instant('portail.community.visit.saved'));
    } catch (error) {
      this.errors.set(messagesOf(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }

  private show(visit: MyVisit): void {
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
    });
  }
}
