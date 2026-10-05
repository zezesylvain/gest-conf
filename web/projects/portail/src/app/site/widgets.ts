import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import {
  formatInZone,
  PublicEdition,
  PublicFileRef,
  PublicKeyDate,
  PublicSubmissionType,
  PublicTrack,
} from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { localized, SiteLanguage } from './site-pages';

/** « 2027-06-01 » → « 1 juin 2027 » (date civile, sans fuseau). */
export function formatDay(day: string | null | undefined, language: SiteLanguage): string {
  if (!day) return '';
  return new Intl.DateTimeFormat(language, {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(`${day}T00:00:00Z`));
}

export function countryName(code: string, language: SiteLanguage): string {
  if (!code) return '';
  try {
    return new Intl.DisplayNames([language], { type: 'region' }).of(code) ?? code;
  } catch {
    return code;
  }
}

/** En-tête de l'édition : titre, thème, dates, lieu ; contenu projeté (compte à rebours). */
@Component({
  selector: 'portail-edition-hero',
  imports: [TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @let item = edition();
    <section class="hero">
      <p class="eyebrow">{{ item.code }} · {{ item.year }}</p>
      <!-- Un seul h1 par page : en section, l'en-tête de l'édition prend un h2. -->
      @if (level() === 1) {
        <h1>{{ text(item, 'title') }}</h1>
      } @else {
        <h2>{{ text(item, 'title') }}</h2>
      }
      @if (text(item, 'theme')) {
        <p class="theme">{{ text(item, 'theme') }}</p>
      }
      @if (item.start_date) {
        <p class="when">
          {{
            'portail.site.datesRange'
              | translate: { start: day(item.start_date), end: day(item.end_date) }
          }}
        </p>
      }
      @if (item.venue || item.city) {
        <p class="where">{{ place(item) }}</p>
      }
      <ng-content />
    </section>
  `,
  styleUrl: './site.scss',
})
export class EditionHero {
  readonly edition = input.required<PublicEdition>();
  readonly language = input.required<SiteLanguage>();
  readonly level = input<1 | 2>(1);

  protected text(item: object, field: string): string {
    return localized(item, field, this.language());
  }

  protected day(value: string | null): string {
    return formatDay(value, this.language());
  }

  protected place(item: PublicEdition): string {
    return [item.venue, item.city, countryName(item.country, this.language())]
      .filter(Boolean)
      .join(', ');
  }
}

/** Dates clés publiques, à l'heure de l'édition (fuseau affiché). */
@Component({
  selector: 'portail-dates-list',
  imports: [TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (dates().length) {
      <ol class="dates">
        @for (item of dates(); track item.code) {
          <li>
            <time [attr.datetime]="item.at">{{ when(item) }}</time>
            <span>{{ label(item) | translate }}</span>
          </li>
        }
      </ol>
      @if (timezone()) {
        <p class="muted">{{ 'portail.site.timezone' | translate: { zone: timezone() } }}</p>
      }
    } @else {
      <p class="muted">{{ 'portail.site.noDates' | translate }}</p>
    }
  `,
  styleUrl: './site.scss',
})
export class DatesList {
  readonly dates = input.required<PublicKeyDate[]>();
  readonly language = input.required<SiteLanguage>();
  readonly timezone = input<string>('');

  protected when(item: PublicKeyDate): string {
    return formatInZone(item.at, this.timezone() || undefined, this.language());
  }

  /** Libellé saisi, sinon libellé traduit du code réservé. */
  protected label(item: PublicKeyDate): string {
    return localized(item, 'label', this.language()) || `portail.site.keyDates.${item.code}`;
  }
}

@Component({
  selector: 'portail-tracks-list',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <ul class="cards">
      @for (track of tracks(); track track.code) {
        <li>
          <h3>{{ text(track, 'name') }}</h3>
          @if (text(track, 'description')) {
            <p>{{ text(track, 'description') }}</p>
          }
        </li>
      }
    </ul>
  `,
  styleUrl: './site.scss',
})
export class TracksList {
  readonly tracks = input.required<PublicTrack[]>();
  readonly language = input.required<SiteLanguage>();

  protected text(item: object, field: string): string {
    return localized(item, field, this.language());
  }
}

@Component({
  selector: 'portail-submission-types-list',
  imports: [TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <ul class="cards">
      @for (type of types(); track type.code) {
        <li>
          <h3>{{ text(type, 'label') }}</h3>
          @if (text(type, 'description')) {
            <p>{{ text(type, 'description') }}</p>
          }
          <p class="muted">
            @if (type.default_duration_min) {
              {{ 'portail.site.duration' | translate: { minutes: type.default_duration_min } }} ·
            }
            {{ 'portail.site.abstractWords' | translate: { words: type.abstract_max_words } }}
          </p>
        </li>
      }
    </ul>
  `,
  styleUrl: './site.scss',
})
export class SubmissionTypesList {
  readonly types = input.required<PublicSubmissionType[]>();
  readonly language = input.required<SiteLanguage>();

  protected text(item: object, field: string): string {
    return localized(item, field, this.language());
  }
}

@Component({
  selector: 'portail-documents-list',
  imports: [TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (documents().length) {
      <ul class="documents">
        @for (item of documents(); track item.uuid) {
          <li>
            <a [href]="item.url" download>{{ text(item, 'title') || item.extension }}</a>
            <span class="muted"> ({{ item.extension.toUpperCase() }}, {{ size(item.size) }})</span>
          </li>
        }
      </ul>
    } @else {
      <p class="muted">{{ 'portail.site.noDocuments' | translate }}</p>
    }
  `,
  styleUrl: './site.scss',
})
export class DocumentsList {
  readonly documents = input.required<PublicFileRef[]>();
  readonly language = input.required<SiteLanguage>();

  protected text(item: object, field: string): string {
    return localized(item, field, this.language());
  }

  protected size(bytes: number): string {
    const units = this.language() === 'fr' ? ['o', 'Ko', 'Mo'] : ['B', 'KB', 'MB'];
    let value = bytes;
    let unit = 0;
    while (value >= 1024 && unit < units.length - 1) {
      value /= 1024;
      unit += 1;
    }
    const number = new Intl.NumberFormat(this.language(), { maximumFractionDigits: 1 });
    return `${number.format(value)} ${units[unit]}`;
  }
}
