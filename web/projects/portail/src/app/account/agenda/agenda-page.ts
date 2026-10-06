import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  OnInit,
  signal,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import {
  AgendaEntry,
  Api,
  apiErrorMessage,
  ErrorSummary,
  LanguageService,
  meAgenda,
  PageHeader,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

/** Passages d'une journée d'une édition, à l'heure de l'édition. */
export interface AgendaDay {
  key: string;
  edition: string;
  day: string;
  timezone: string;
  entries: AgendaEntry[];
}

/** Jour (`2027-06-01`) d'un instant dans un fuseau donné. */
export function dayInZone(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat('en-CA', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    timeZone,
  }).format(new Date(iso));
}

/** Regroupe les passages par édition et par jour, dans l'ordre chronologique. */
export function groupByDay(entries: readonly AgendaEntry[]): AgendaDay[] {
  const groups = new Map<string, AgendaDay>();
  for (const entry of [...entries].sort((a, b) => a.starts_at.localeCompare(b.starts_at))) {
    const zone = entry.edition.timezone;
    const day = dayInZone(entry.starts_at, zone);
    const key = `${entry.edition.code}:${day}`;
    if (!groups.has(key)) {
      groups.set(key, { key, edition: entry.edition.code, day, timezone: zone, entries: [] });
    }
    groups.get(key)!.entries.push(entry);
  }
  return [...groups.values()];
}

/**
 * « Mon passage » (plan L5, I8) : présentations, interventions et rôles de séance de la
 * personne connectée, d'après le **programme publié** (jamais le brouillon) ; heures dans le
 * fuseau de chaque édition, qui est indiqué. Fichier iCal pour l'agenda personnel.
 */
@Component({
  selector: 'portail-agenda-page',
  imports: [TranslatePipe, MatButtonModule, ErrorSummary, PageHeader],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <gc-page-header
      [heading]="'portail.agenda.title' | translate"
      [lead]="'portail.agenda.lead' | translate"
    />
    <gc-error-summary [messages]="errors()" />
    @if (loading()) {
      <p role="status">{{ 'portail.account.home.loading' | translate }}</p>
    } @else if (days().length) {
      <p class="actions">
        <a mat-stroked-button href="/api/v1/me/agenda.ics" download="mon-passage.ics">
          {{ 'portail.agenda.ics' | translate }}
        </a>
        <span class="hint">{{ 'portail.agenda.icsHint' | translate }}</span>
      </p>
      @for (group of days(); track group.key) {
        <section [attr.aria-labelledby]="'day-' + group.key">
          <h2 [id]="'day-' + group.key">
            {{ dayLabel(group) }}
            <span class="hint">· {{ group.edition }} · {{ group.timezone }}</span>
          </h2>
          <ul class="passages">
            @for (entry of group.entries; track $index) {
              <li>
                <p class="when">
                  <strong
                    >{{ time(entry.starts_at, group.timezone) }} –
                    {{ time(entry.ends_at, group.timezone) }}</strong
                  >
                  · {{ 'portail.agenda.roles.' + entry.role | translate }} ·
                  {{ 'portail.agenda.duration' | translate: { count: entry.duration_min } }}
                </p>
                <h3>
                  {{ title(entry) }}
                  @if (entry.reference) {
                    <span class="hint">({{ entry.reference }})</span>
                  }
                </h3>
                <p>
                  {{ 'portail.agenda.session' | translate }} : {{ sessionTitle(entry) }}
                  @if (entry.room.name) {
                    · {{ 'portail.agenda.room' | translate }} : {{ entry.room.name }}
                    @if (entry.room.is_accessible) {
                      ({{ 'portail.agenda.accessible' | translate }})
                    }
                  }
                </p>
                @if (entry.room.access_note) {
                  <p class="hint">{{ entry.room.access_note }}</p>
                }
                @if (entry.co_speakers.length) {
                  <p>
                    {{ 'portail.agenda.coSpeakers' | translate }} :
                    {{ entry.co_speakers.join(', ') }}
                  </p>
                }
                @if (entry.chairs.length) {
                  <p>{{ 'portail.agenda.chairs' | translate }} : {{ entry.chairs.join(', ') }}</p>
                }
                @if (entry.instructions) {
                  <p class="instructions">
                    <strong>{{ 'portail.agenda.instructions' | translate }} :</strong>
                    {{ entry.instructions }}
                  </p>
                }
              </li>
            }
          </ul>
        </section>
      }
    } @else {
      <p>{{ 'portail.agenda.empty' | translate }}</p>
    }
  `,
  styles: `
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem 1rem;
      align-items: center;
    }
    .hint {
      color: var(--gc-muted);
      font-weight: normal;
    }
    h2 {
      font-size: 1.15rem;
      margin: 1.5rem 0 0.5rem;
    }
    h3 {
      font-size: 1rem;
      margin: 0.25rem 0;
      overflow-wrap: anywhere;
    }
    .passages {
      list-style: none;
      padding: 0;
      margin: 0;
      display: grid;
      gap: 0.75rem;
    }
    .passages li {
      padding: 0.75rem 1rem;
      border: 1px solid var(--gc-border);
      border-left: 4px solid var(--gc-primary);
      border-radius: 0.25rem;
    }
    .passages p {
      margin: 0.25rem 0;
    }
    .instructions {
      white-space: pre-wrap;
    }
  `,
})
export class AgendaPage implements OnInit {
  private readonly api = inject(Api);
  private readonly translate = inject(TranslateService);
  private readonly language = inject(LanguageService);

  protected readonly entries = signal<AgendaEntry[]>([]);
  protected readonly loading = signal(true);
  protected readonly errors = signal<string[]>([]);
  protected readonly days = computed(() => groupByDay(this.entries()));

  async ngOnInit(): Promise<void> {
    try {
      this.entries.set(await this.api.invoke(meAgenda));
    } catch (error) {
      this.errors.set([apiErrorMessage(this.translate, error)]);
    } finally {
      this.loading.set(false);
    }
  }

  private lang(): string {
    return this.language.current();
  }

  protected dayLabel(group: AgendaDay): string {
    return new Intl.DateTimeFormat(this.lang(), {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
      year: 'numeric',
      timeZone: 'UTC',
    }).format(new Date(`${group.day}T12:00:00Z`));
  }

  protected time(iso: string, timeZone: string): string {
    return new Intl.DateTimeFormat(this.lang(), {
      hour: '2-digit',
      minute: '2-digit',
      timeZone,
    }).format(new Date(iso));
  }

  protected title(entry: AgendaEntry): string {
    return (this.lang() === 'en' && entry.title_en) || entry.title;
  }

  protected sessionTitle(entry: AgendaEntry): string {
    return (this.lang() === 'en' && entry.session.title_en) || entry.session.title_fr;
  }
}
