import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  OnInit,
  signal,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { RouterLink } from '@angular/router';
import {
  CheckinListItem,
  DaySession,
  DaySlot,
  ErrorSummary,
  formatInZone,
  LanguageService,
  MeStore,
  PageHeader,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { EventsApi } from '../../core/events-api';
import { editionCapabilities, errorMessages } from '../../core/page-support';
import { saveBlob } from '../../core/registrations-api';
import { confirmAction, title } from './events-support';

/** Présents d'une session dépliée (première page : l'écran n'est pas un registre). */
interface AttendancePanel {
  rows: CheckinListItem[];
  count: number;
}

const ATTENDANCE_PAGE = 100;

/**
 * Sessions du jour (plan L7, K7, K8) : programme **publié**, présents pointés à l'entrée,
 * communications marquées « présentée ». Le président de séance ne voit et ne traite que
 * ses sessions ; le CO « programme » et l'administrateur corrigent une « présentée » à tort
 * (`program.write`, motif). Les droits sont revérifiés par le serveur (règle n° 2).
 */
@Component({
  selector: 'gestion-day-sessions-page',
  imports: [RouterLink, TranslatePipe, MatButtonModule, ErrorSummary, PageHeader],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './day-sessions-page.html',
  styleUrl: '../page.scss',
  styles: `
    .slots {
      list-style: none;
      padding: 0;
      margin: 0.5rem 0 0;
    }
    .slots li {
      padding: 0.5rem 0;
      border-top: 1px solid var(--gc-border);
    }
  `,
})
export class DaySessionsPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(EventsApi);
  private readonly meStore = inject(MeStore);
  private readonly dialog = inject(MatDialog);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly sessions = signal<DaySession[]>([]);
  protected readonly attendance = signal<Record<number, AttendancePanel>>({});
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  private readonly capabilities = computed(() =>
    editionCapabilities(this.meStore, this.editionId()),
  );
  protected readonly canManage = computed(() => this.capabilities().includes('checkin.manage'));
  protected readonly canCorrect = computed(() => this.capabilities().includes('program.write'));

  async ngOnInit(): Promise<void> {
    await this.reload();
  }

  private edition(): number {
    return Number(this.editionId());
  }

  protected title(session: DaySession): string {
    return title(session, this.language.current());
  }

  protected time(value: string): string {
    return formatInZone(value, undefined, this.language.current());
  }

  /** « Présentée » : président de cette session, ou `program.write` (K8). */
  protected canMark(session: DaySession): boolean {
    return session.chaired || this.canCorrect();
  }

  /** Présents : `checkin.manage`, ou présidence de cette session (K7). */
  protected canSeeAttendance(session: DaySession): boolean {
    return session.chaired || this.canManage();
  }

  protected async toggleAttendance(session: DaySession): Promise<void> {
    const current = { ...this.attendance() };
    if (current[session.id]) {
      delete current[session.id];
      this.attendance.set(current);
      return;
    }
    await this.run(async () => {
      const page = await this.api.attendance(this.edition(), session.id, {
        page_size: ATTENDANCE_PAGE,
      });
      this.attendance.set({
        ...this.attendance(),
        [session.id]: { rows: page.results, count: page.count },
      });
    });
  }

  protected async exportAttendance(session: DaySession): Promise<void> {
    await this.run(async () => {
      const blob = await this.api.exportAttendance(this.edition(), session.id);
      saveBlob(blob, `presences-session-${session.id}.csv`);
    });
  }

  protected async markPresented(session: DaySession, slot: DaySlot): Promise<void> {
    await this.run(async () => {
      this.replace(await this.api.markPresented(this.edition(), session.id, slot.id));
      this.status.set(
        this.translate.instant('gestion.daySessions.presented.done', { title: slot.title }),
      );
    });
  }

  protected async unmarkPresented(session: DaySession, slot: DaySlot): Promise<void> {
    const answer = await confirmAction(
      this.dialog,
      this.translate,
      'gestion.daySessions.unpresent',
      { title: slot.title },
      true,
    );
    if (!answer) {
      return;
    }
    await this.run(async () => {
      this.replace(
        await this.api.unmarkPresented(this.edition(), session.id, slot.id, answer.reason.trim()),
      );
      this.status.set(
        this.translate.instant('gestion.daySessions.unpresent.done', { title: slot.title }),
      );
    });
  }

  private replace(session: DaySession): void {
    this.sessions.update((rows) => rows.map((row) => (row.id === session.id ? session : row)));
  }

  private async reload(): Promise<void> {
    try {
      this.sessions.set(await this.api.daySessions(this.edition()));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }

  private async run(action: () => Promise<void>): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    this.status.set('');
    try {
      await action();
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }
}
