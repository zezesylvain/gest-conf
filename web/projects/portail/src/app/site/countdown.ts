import { afterNextRender, ChangeDetectionStrategy, Component, input, signal } from '@angular/core';
import { PublicEdition } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { SiteLanguage } from './site-pages';

/** Jours restants avant le début (date civile de l'édition), à une date donnée. */
export function daysUntil(startDate: string, timeZone: string, now: Date): number {
  // Date du jour **dans le fuseau de l'édition** (E8), puis écart en jours civils.
  const today = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(now);
  const day = 86_400_000;
  return Math.round(
    (Date.parse(`${startDate}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`)) / day,
  );
}

/**
 * Compte à rebours (E8) : calculé **dans le navigateur** après le rendu (une page pré-rendue
 * figerait sinon le nombre du jour du build), dans le fuseau de l'édition.
 */
@Component({
  selector: 'portail-countdown',
  imports: [TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (days(); as remaining) {
      <p class="countdown" aria-live="off">
        {{ 'portail.site.countdown' | translate: { days: remaining } }}
      </p>
    }
  `,
  styleUrl: './site.scss',
})
export class Countdown {
  readonly edition = input.required<PublicEdition>();
  readonly language = input.required<SiteLanguage>();
  protected readonly days = signal<number | null>(null);

  constructor() {
    afterNextRender(() => {
      const edition = this.edition();
      if (!edition.start_date) return;
      const remaining = daysUntil(edition.start_date, edition.timezone, new Date());
      this.days.set(remaining > 0 ? remaining : null);
    });
  }
}
