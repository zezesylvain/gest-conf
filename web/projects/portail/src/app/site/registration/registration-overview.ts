import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  OnInit,
  PendingTasks,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import {
  formatInZone,
  formatMoney,
  GcApiError,
  Period,
  PublicCategory,
  PublicOption,
  PublicRegistration,
  Zone,
} from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { SiteLanguage } from '../site-pages';
import { RegistrationData } from './registration-data';
import { feeColumns, feeFor, inLanguage } from './registration-support';

/** Adresse de l'espace « Mon inscription » (rendu dans le navigateur, connexion exigée). */
export const MY_REGISTRATION_PATH = '/compte/mon-inscription';

/**
 * Page publique « Inscription » (plan L6, J13) : catégories et grille des tarifs (période ×
 * zone), options, dates, moyens de paiement, pays « locaux ». Lue au pré-rendu : une
 * modification n'apparaît qu'à la publication du portail (`deploy.sh --portal-only`). Le prix
 * exact (code promo, zone du profil, période du jour) est calculé par le serveur dans
 * l'espace « Mon inscription ». Sans Material.
 */
@Component({
  selector: 'portail-registration-overview',
  imports: [RouterLink, TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './registration-overview.html',
  styleUrls: ['../site.scss', './registration.scss'],
})
export class RegistrationOverview implements OnInit {
  readonly language = input.required<SiteLanguage>();

  private readonly data = inject(RegistrationData);
  private readonly pendingTasks = inject(PendingTasks);

  protected readonly myRegistration = MY_REGISTRATION_PATH;
  protected readonly catalog = signal<PublicRegistration | null>(null);
  protected readonly state = signal<'loading' | 'ready' | 'unavailable' | 'error'>('loading');
  protected readonly columns = computed(() => feeColumns(this.catalog()?.categories ?? []));
  /** Dates du calendrier des inscriptions, dans l'ordre, celles qui sont fixées. */
  protected readonly dates = computed(() => {
    const catalog = this.catalog();
    if (!catalog) {
      return [];
    }
    return (
      [
        ['registration_open', catalog.opens_at],
        ['early_bird_end', catalog.early_bird_end],
        ['registration_close', catalog.closes_at],
      ] as const
    )
      .filter(([, at]) => !!at)
      .map(([code, at]) => ({ code, at: at as string }));
  });
  protected readonly localCountries = computed(() => {
    const codes = this.catalog()?.local_countries ?? [];
    let names: Intl.DisplayNames | null = null;
    try {
      names = new Intl.DisplayNames([this.language()], { type: 'region' });
    } catch {
      names = null;
    }
    return codes.map((code) => names?.of(code) ?? code).join(', ');
  });

  async ngOnInit(): Promise<void> {
    // Le pré-rendu attend la fin de cette lecture (page complète).
    await this.pendingTasks.run(async () => {
      try {
        this.catalog.set(await this.data.catalog());
        this.state.set('ready');
      } catch (error) {
        this.state.set(
          error instanceof GcApiError && error.status === 404 ? 'unavailable' : 'error',
        );
      }
    });
  }

  protected text(item: { label_fr: string; label_en: string }): string {
    return inLanguage(item.label_fr, item.label_en, this.language());
  }

  protected description(item: { description_fr: string; description_en: string }): string {
    return inLanguage(item.description_fr, item.description_en, this.language());
  }

  protected when(at: string): string {
    return formatInZone(at, this.catalog()?.timezone, this.language());
  }

  protected amount(value: string): string {
    return formatMoney(value, this.catalog()?.currency ?? 'XOF', this.language());
  }

  protected fee(category: PublicCategory, period: Period, zone: Zone): string {
    const found = feeFor(category.fees, period, zone);
    return found ? this.amount(found.amount) : '—';
  }

  /** Catégories auxquelles l'option est réservée (libellés), vide : toutes. */
  protected optionCategories(option: PublicOption): string {
    const categories = this.catalog()?.categories ?? [];
    return option.categories
      .map((code) => categories.find((category) => category.code === code))
      .filter((category): category is PublicCategory => !!category)
      .map((category) => this.text(category))
      .join(', ');
  }
}
