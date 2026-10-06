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
import { GcApiError, PublicProgram, SessionKind } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { SiteLanguage } from '../site-pages';
import { ProgramData } from './program-data';
import {
  dayLabel,
  dayPath,
  distinct,
  filterDays,
  inLanguage,
  kindsOf,
  NO_FILTERS,
  ProgramFilters,
  sessionPath,
  timeIn,
} from './program-support';

/**
 * Accueil du programme public (plan L5, I7 ; bilan L5.0) : jours et sessions, sans le détail
 * des communications (une page par jour et par session). Filtres par jour, salle, thématique
 * et type, recherche dans la page : tout est pré-rendu, les filtres n'agissent que dans le
 * navigateur. Avant la première publication, la page le dit.
 */
@Component({
  selector: 'portail-program-overview',
  imports: [RouterLink, TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './program-overview.html',
  styleUrl: './program.scss',
})
export class ProgramOverview implements OnInit {
  readonly language = input.required<SiteLanguage>();

  private readonly data = inject(ProgramData);
  private readonly pendingTasks = inject(PendingTasks);

  protected readonly program = signal<PublicProgram | null>(null);
  protected readonly state = signal<'loading' | 'ready' | 'unpublished' | 'error'>('loading');
  protected readonly filters = signal<ProgramFilters>(NO_FILTERS);

  private readonly sessions = computed(() =>
    (this.program()?.days ?? []).flatMap((day) => day.sessions),
  );
  protected readonly rooms = computed(() => distinct(this.sessions(), (item) => item.room));
  protected readonly tracks = computed(() => {
    const seen = new Map<string, string>();
    for (const item of this.sessions()) {
      if (item.track) {
        seen.set(
          item.track.code,
          inLanguage(item.track.name_fr, item.track.name_en, this.language()),
        );
      }
    }
    return [...seen.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  });
  protected readonly kinds = computed(() =>
    kindsOf(this.sessions().map((item) => item.kind as SessionKind)),
  );
  protected readonly days = computed(() => filterDays(this.program()?.days ?? [], this.filters()));
  protected readonly count = computed(() =>
    this.days().reduce((sum, day) => sum + day.sessions.length, 0),
  );

  async ngOnInit(): Promise<void> {
    // Le pré-rendu attend la fin de cette lecture (page complète).
    await this.pendingTasks.run(async () => {
      try {
        this.program.set(await this.data.summary());
        this.state.set('ready');
      } catch (error) {
        this.state.set(
          error instanceof GcApiError && error.status === 404 ? 'unpublished' : 'error',
        );
      }
    });
  }

  protected setFilter(name: keyof ProgramFilters, value: string): void {
    this.filters.update((current) => ({ ...current, [name]: value }));
  }

  protected day(date: string): string {
    return dayLabel(date, this.language());
  }

  protected dayLink(date: string): string {
    return dayPath(date, this.language());
  }

  protected sessionLink(id: number): string {
    return sessionPath(id, this.language());
  }

  protected hours(startsAt: string, endsAt: string): string {
    const zone = this.program()?.timezone ?? 'UTC';
    return `${timeIn(startsAt, zone, this.language())} – ${timeIn(endsAt, zone, this.language())}`;
  }

  protected title(item: { title_fr: string; title_en: string }): string {
    return inLanguage(item.title_fr, item.title_en, this.language());
  }

  protected trackName(track: { name_fr: string; name_en: string }): string {
    return inLanguage(track.name_fr, track.name_en, this.language());
  }
}
