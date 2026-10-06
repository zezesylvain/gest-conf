import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { PublicProgramDay, PublicSession } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { SiteLanguage } from '../site-pages';
import { ProgramData } from './program-data';
import { ProgramRoutePage } from './program-route-page';
import { ProgramSlotList } from './program-slot-list';
import {
  dayPath,
  distinct,
  filterSessions,
  inLanguage,
  NO_FILTERS,
  ProgramFilters,
  roomColumns,
  sessionPath,
} from './program-support';

/**
 * Journée du programme public (plan L5, I7) : liste chronologique détaillée, ou grille par
 * salle ; filtres par salle et thématique, recherche (titres, auteurs, intervenants). Une
 * page pré-rendue par jour (bilan L5.0).
 */
@Component({
  selector: 'portail-program-day-page',
  imports: [RouterLink, TranslatePipe, ProgramSlotList],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './program-day-page.html',
  styleUrl: './program.scss',
})
export class ProgramDayPage extends ProgramRoutePage {
  private readonly data = inject(ProgramData);
  private readonly date = this.route.snapshot.paramMap.get('day') ?? '';

  protected readonly program = signal<PublicProgramDay | null>(null);
  protected readonly view = signal<'list' | 'grid'>('list');
  protected readonly filters = signal<ProgramFilters>(NO_FILTERS);

  protected readonly sessions = computed(() =>
    filterSessions(this.program()?.sessions ?? [], this.filters()),
  );
  protected readonly columns = computed(() => roomColumns(this.sessions()));
  protected readonly rooms = computed(() =>
    distinct(this.program()?.sessions ?? [], (item) => item.room?.name ?? null),
  );
  protected readonly tracks = computed(() => {
    const seen = new Map<string, string>();
    for (const item of this.program()?.sessions ?? []) {
      if (item.track) {
        seen.set(item.track.code, inLanguage(item.track.name_fr, item.track.name_en, this.lang()));
      }
    }
    return [...seen.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  });

  protected paths(): Record<SiteLanguage, string> {
    return { fr: dayPath(this.date, 'fr'), en: dayPath(this.date, 'en') };
  }

  protected async fetch(): Promise<void> {
    this.program.set(await this.data.day(this.date));
  }

  protected heading(): string {
    return `${this.translate.instant('portail.program.title')} — ${this.day(this.date)}`;
  }

  protected markerKey(): string {
    return `program-day-${this.date}`;
  }

  protected setFilter(name: keyof ProgramFilters, value: string): void {
    this.filters.update((current) => ({ ...current, [name]: value }));
  }

  protected sessionLink(id: number): string {
    return sessionPath(id, this.lang());
  }

  protected hours(session: PublicSession): string {
    const zone = this.program()?.timezone ?? 'UTC';
    return `${this.time(session.starts_at, zone)} – ${this.time(session.ends_at, zone)}`;
  }

  protected title(session: PublicSession): string {
    return inLanguage(session.title_fr, session.title_en, this.lang());
  }

  protected pause(session: PublicSession): boolean {
    return ['break', 'meal', 'social'].includes(session.kind);
  }
}
