import {
  afterNextRender,
  ChangeDetectionStrategy,
  Component,
  computed,
  input,
  signal,
} from '@angular/core';
import {
  formatInZone,
  PublicCommittee,
  PublicCommitteeMember,
  PublicEdition,
  PublicFileRef,
  PublicKeyDate,
  PublicSubmissionType,
  PublicTrack,
} from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { brandName } from './brand';
import { safeHref } from './sanitize';
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

/**
 * En-tête de l'édition (décision T4, V7) : bande bleu nuit pleine largeur, titre, thème,
 * dates, lieu et contenu projeté (compte à rebours, boutons) ; l'affiche à droite quand elle
 * est publiée.
 */
@Component({
  selector: 'portail-edition-hero',
  imports: [TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @let item = edition();
    <section class="hero">
      <div class="hero-grid">
        <div class="hero-text">
          <p class="eyebrow">{{ eyebrow() }}</p>
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
        </div>
        @if (poster(); as image) {
          <figure class="poster">
            <img
              [src]="image.url"
              [attr.width]="image.width"
              [attr.height]="image.height"
              [alt]="text(image, 'title')"
            />
          </figure>
        }
      </div>
    </section>
  `,
  styleUrl: './hero.scss',
})
export class EditionHero {
  readonly edition = input.required<PublicEdition>();
  readonly language = input.required<SiteLanguage>();
  readonly level = input<1 | 2>(1);
  /** Affiche publiée de l'édition (accueil) ; aucune en section. */
  readonly poster = input<PublicFileRef | null>(null);

  protected readonly eyebrow = computed(() => {
    const item = this.edition();
    return [brandName(item.code, item.year), item.city].filter(Boolean).join(' · ');
  });

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

/** État d'une date clé, calculé dans le navigateur (une page pré-rendue ne fige rien). */
export type DateStatus = 'past' | 'ongoing' | 'upcoming';

/**
 * Passée, à venir, ou en cours pour une ouverture (`…_open`) dont la clôture (`…_close`)
 * n'est pas encore atteinte (T4, V8).
 */
export function dateStatus(item: PublicKeyDate, all: PublicKeyDate[], now: Date): DateStatus {
  if (Date.parse(item.at) > now.getTime()) return 'upcoming';
  if (item.code.endsWith('_open')) {
    const close = all.find((other) => other.code === item.code.replace(/_open$/, '_close'));
    if (close && Date.parse(close.at) > now.getTime()) return 'ongoing';
  }
  return 'past';
}

/** Dates clés publiques en cartes, à l'heure de l'édition (fuseau affiché ; T4, V8). */
@Component({
  selector: 'portail-dates-list',
  imports: [TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (dates().length) {
      <ol class="dates">
        @for (item of dates(); track item.code) {
          <li>
            @if (statuses()[item.code]; as status) {
              <span class="status" [class]="status">{{
                'portail.site.dateStatus.' + status | translate
              }}</span>
            }
            <time [attr.datetime]="item.at">{{ when(item) }}</time>
            <span class="label">{{ label(item) | translate }}</span>
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
  protected readonly statuses = signal<Record<string, DateStatus>>({});

  constructor() {
    afterNextRender(() => {
      const now = new Date();
      const all = this.dates();
      this.statuses.set(
        Object.fromEntries(all.map((item) => [item.code, dateStatus(item, all, now)])),
      );
    });
  }

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
    <ul class="cards numbered">
      @for (track of tracks(); track track.code) {
        <li>
          <span class="number" aria-hidden="true">{{ number($index) }}</span>
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

  /** Numéro d'axe sur deux chiffres (« 01 »), comme l'affiche (T4, V9). */
  protected number(index: number): string {
    return String(index + 1).padStart(2, '0');
  }

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

/**
 * Membres d'un comité ayant consenti à l'annuaire (E5) ; jamais d'adresse. Les autres
 * membres sont comptés (« et N autres membres »).
 */
@Component({
  selector: 'portail-committee-list',
  imports: [TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @let data = committee();
    @if (data.members.length) {
      <ul class="people">
        @for (person of data.members; track $index) {
          <li>
            @if (person.photo_url) {
              <img [src]="person.photo_url" alt="" width="72" height="72" loading="lazy" />
            }
            <div>
              <h3>
                @if (person.title) {
                  {{ 'portail.site.titles.' + person.title | translate }}
                }
                {{ person.name }}
              </h3>
              @if (person.chair || person.function) {
                <p class="role">
                  {{
                    (person.chair
                      ? 'portail.site.chair'
                      : 'portail.site.functions.' + person.function
                    ) | translate
                  }}
                </p>
              }
              @if (affiliation(person)) {
                <p class="muted">{{ affiliation(person) }}</p>
              }
              @if (links(person).length) {
                <p class="links">
                  @for (link of links(person); track link.key) {
                    <a [href]="link.href" rel="noopener noreferrer" target="_blank">{{
                      'portail.site.links.' + link.key | translate
                    }}</a>
                  }
                </p>
              }
            </div>
          </li>
        }
      </ul>
    }
    @if (data.others) {
      <p class="muted">
        {{
          (data.members.length
            ? data.others === 1
              ? 'portail.site.othersOne'
              : 'portail.site.othersMany'
            : data.others === 1
              ? 'portail.site.membersOne'
              : 'portail.site.membersMany'
          ) | translate: { count: data.others }
        }}
      </p>
    } @else if (!data.members.length) {
      <p class="muted">{{ 'portail.site.committeeSoon' | translate }}</p>
    }
  `,
  styleUrl: './site.scss',
})
export class CommitteeList {
  readonly committee = input.required<PublicCommittee>();
  readonly language = input.required<SiteLanguage>();

  protected affiliation(person: PublicCommitteeMember): string {
    return [person.institution, countryName(person.country, this.language())]
      .filter(Boolean)
      .join(', ');
  }

  /** Liens https vérifiés au serveur, revérifiés ici (défense en profondeur). */
  protected links(person: PublicCommitteeMember): { key: string; href: string }[] {
    const candidates: [string, string][] = [
      ['website', person.website],
      ['scholar', person.scholar_url],
      ['linkedin', person.linkedin_url],
    ];
    return candidates.flatMap(([key, raw]) => {
      const href = raw ? safeHref(raw) : null;
      return href?.startsWith('https://') ? [{ key, href }] : [];
    });
  }
}
