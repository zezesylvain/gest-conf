import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { GcApiError, PublicSession } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { SiteLanguage } from '../site-pages';
import { ProgramData } from './program-data';
import { ProgramRoutePage } from './program-route-page';
import { ProgramSlotList } from './program-slot-list';
import { dayPath, inLanguage, sessionPath } from './program-support';

/**
 * Fiche d'une session du programme public (plan L5, I7, I11) : horaire, salle et accès,
 * thématique, présidents de séance, description, communications et intervenants invités.
 */
@Component({
  selector: 'portail-program-session-page',
  imports: [RouterLink, TranslatePipe, ProgramSlotList],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <article class="program-page" [attr.data-gc-rendered]="marker()" [attr.lang]="lang()">
      @switch (state()) {
        @case ('loading') {
          <p role="status" class="muted">{{ 'portail.site.loading' | translate }}</p>
        }
        @case ('missing') {
          <h1>{{ 'portail.notFound.heading' | translate }}</h1>
          <p>
            <a [routerLink]="programLink()">{{ 'portail.program.back' | translate }}</a>
          </p>
        }
        @case ('error') {
          <h1>{{ 'portail.site.errorTitle' | translate }}</h1>
          <p>{{ 'portail.site.errorLead' | translate }}</p>
        }
        @case ('ready') {
          @if (session(); as current) {
            <p class="crumbs">
              <a [routerLink]="programLink()">{{ 'portail.program.back' | translate }}</a>
              › <a [routerLink]="dayLink()">{{ day(date()) }}</a>
            </p>
            <h1>{{ heading() }}</h1>
            <p class="when">
              {{ day(date()) }} · {{ time(current.starts_at, zone()) }} –
              {{ time(current.ends_at, zone()) }}
              <span class="muted">({{ zone() }})</span>
            </p>
            <p class="meta">
              {{ 'portail.program.kinds.' + current.kind | translate }}
              @if (current.track; as track) {
                · {{ text(track, 'name') }}
              }
            </p>
            @if (current.room; as room) {
              <p>
                {{ 'portail.program.room' | translate }} : <strong>{{ room.name }}</strong>
                @if (room.is_accessible) {
                  ({{ 'portail.program.accessible' | translate }})
                }
              </p>
              @if (room.access_note) {
                <p class="meta">{{ room.access_note }}</p>
              }
            }
            @for (chair of current.chairs; track $index) {
              <p>
                {{ 'portail.program.roles.' + chair.role | translate }} : {{ chair.name }}
                @if (chair.institution) {
                  ({{ chair.institution }})
                }
              </p>
            }
            @if (text(current, 'description')) {
              <p class="description">{{ text(current, 'description') }}</p>
            }
            @if (current.slots.length) {
              <h2>{{ 'portail.program.contributions' | translate }}</h2>
              <portail-program-slot-list
                [slots]="current.slots"
                [timezone]="zone()"
                [language]="lang()"
                [detailed]="true"
              />
            }
          }
        }
      }
    </article>
  `,
  styleUrl: './program.scss',
})
export class ProgramSessionPage extends ProgramRoutePage {
  private readonly data = inject(ProgramData);
  private readonly id = Number(this.route.snapshot.paramMap.get('id'));

  protected readonly session = signal<PublicSession | null>(null);
  protected readonly zone = computed(() => this.site()?.edition.timezone ?? 'UTC');
  /** Jour de la session, à l'heure de l'édition. */
  protected readonly date = computed(() => {
    const current = this.session();
    if (!current) {
      return '';
    }
    return new Intl.DateTimeFormat('en-CA', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      timeZone: this.zone(),
    }).format(new Date(current.starts_at));
  });

  protected paths(): Record<SiteLanguage, string> {
    return { fr: sessionPath(this.id, 'fr'), en: sessionPath(this.id, 'en') };
  }

  protected async fetch(): Promise<void> {
    if (!Number.isInteger(this.id) || this.id < 1) {
      throw new GcApiError(404, 'not_found', '');
    }
    this.session.set(await this.data.session(this.id));
  }

  protected heading(): string {
    const current = this.session();
    return current ? inLanguage(current.title_fr, current.title_en, this.lang()) : '';
  }

  protected markerKey(): string {
    return `program-session-${this.id}`;
  }

  protected dayLink(): string {
    return dayPath(this.date(), this.lang());
  }
}
