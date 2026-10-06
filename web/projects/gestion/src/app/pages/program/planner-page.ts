import { CdkDrag, CdkDragDrop, CdkDropList, CdkDropListGroup } from '@angular/cdk/drag-drop';
import {
  afterNextRender,
  ChangeDetectionStrategy,
  Component,
  computed,
  ElementRef,
  inject,
  Injector,
  signal,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import {
  ErrorSummary,
  PageHeader,
  ProgramConflict,
  ScheduledSubmission,
  Session,
  Slot,
  SubmissionType,
  Track,
} from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { EditionApi } from '../../core/edition-api';
import { ProgramPage } from './program-page';
import {
  dayGrid,
  dayLabel,
  filterToSchedule,
  localTime,
  NON_SCIENTIFIC_KINDS,
  programDays,
  sessionConflicts,
  sessionDay,
  sessionMinutes,
  sessionTitle,
  slotConflicts,
  slotTitle,
  sortSessions,
  timeInZone,
  ToScheduleFilters,
  usedMinutes,
} from './program-support';

/** Élément déplacé : communication à programmer, ou créneau déjà placé. */
export type DragItem =
  | { kind: 'submission'; submission: ScheduledSubmission }
  | { kind: 'slot'; slot: Slot; session: Session };

/** Cible de dépôt : la liste « à programmer » ou une session. */
export type DropTarget = { kind: 'pool' } | { kind: 'session'; session: Session };

/**
 * Planificateur (plan L5, I15) : grille du jour × salles, liste « à programmer » filtrable,
 * glisser-déposer du CDK **et** équivalent au clavier (« Placer dans… », monter, descendre,
 * durée, retirer), car le CDK n'a ni clavier ni ARIA (bilan L5.0). Chaque action est
 * annoncée dans une région `aria-live`. Conflits renvoyés par le serveur à chaque écriture
 * (RG-12, RG-13). Sous 768 px, la grille devient une liste.
 */
@Component({
  selector: 'gestion-planner-page',
  imports: [
    CdkDrag,
    CdkDropList,
    CdkDropListGroup,
    RouterLink,
    TranslatePipe,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './planner-page.html',
  styleUrls: ['../page.scss', './planner-page.scss'],
})
export class PlannerPage extends ProgramPage {
  private readonly editionApi = inject(EditionApi);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly injector = inject(Injector);

  protected readonly tracks = signal<Track[]>([]);
  protected readonly types = signal<SubmissionType[]>([]);
  protected readonly filters = signal<ToScheduleFilters>({ track: '', type: '', query: '' });
  protected readonly selectedDay = signal<string | null>(null);
  /** Panneau clavier ouvert : `submission:<id>` ou `slot:<id>`. */
  protected readonly panel = signal<string | null>(null);

  protected readonly days = computed(() => {
    const board = this.board();
    return board ? programDays(board) : [];
  });
  protected readonly day = computed(() => {
    const days = this.days();
    const selected = this.selectedDay();
    if (selected && days.includes(selected)) {
      return selected;
    }
    const sessions = this.board()?.sessions ?? [];
    return days.find((day) => sessions.some((item) => sessionDay(item) === day)) ?? days[0] ?? '';
  });
  protected readonly columns = computed(() => {
    const board = this.board();
    return board && this.day() ? dayGrid(board, this.day()) : [];
  });
  protected readonly pool = computed(() =>
    filterToSchedule(this.board()?.to_schedule ?? [], this.filters()),
  );
  /** Sessions cibles de « Placer dans… », tous jours confondus, groupées par jour. */
  protected readonly targets = computed(() => {
    const sessions = sortSessions(
      (this.board()?.sessions ?? []).filter((item) => !NON_SCIENTIFIC_KINDS.includes(item.kind)),
    );
    return this.days()
      .map((day) => ({
        day,
        label: dayLabel(day, this.lang()),
        sessions: sessions.filter((item) => sessionDay(item) === day),
      }))
      .filter((group) => group.sessions.length);
  });
  /** Données des listes de dépôt, typées et stables d'un rendu à l'autre. */
  protected readonly poolTarget: DropTarget = { kind: 'pool' };
  protected readonly sessionTargets = computed(
    () =>
      new Map<number, DropTarget>(
        (this.board()?.sessions ?? []).map((session) => [session.id, { kind: 'session', session }]),
      ),
  );
  protected readonly dropListIds = computed(() => [
    'pool',
    ...(this.board()?.sessions ?? []).map((item) => `session-${item.id}`),
  ]);

  override async ngOnInit(): Promise<void> {
    const id = this.edition();
    const [tracks, types] = await Promise.all([
      this.editionApi.tracks(id).catch(() => [] as Track[]),
      this.editionApi.submissionTypes(id).catch(() => [] as SubmissionType[]),
    ]);
    this.tracks.set(tracks);
    this.types.set(types);
    await super.ngOnInit();
  }

  // --- Affichage -----------------------------------------------------------------------------

  protected dayName(day: string): string {
    return dayLabel(day, this.lang());
  }

  protected title(session: Session): string {
    return sessionTitle(session, this.lang());
  }

  protected slotLabel(slot: Slot): string {
    return slotTitle(slot, this.lang());
  }

  protected hours(session: Session): string {
    return `${localTime(session.starts_local)} – ${localTime(session.ends_local)}`;
  }

  protected slotHours(slot: Slot): string {
    const zone = this.board()?.timezone ?? 'UTC';
    return `${timeInZone(slot.starts_at, zone, this.lang())} – ${timeInZone(slot.ends_at, zone, this.lang())}`;
  }

  protected targetLabel(session: Session): string {
    const room = this.roomName(session.room);
    return `${localTime(session.starts_local)} · ${this.title(session)} · ${room}`;
  }

  protected roomName(id: number | null): string {
    if (id === null) {
      return this.translate.instant('gestion.program.noRoom');
    }
    return this.board()?.rooms.find((room) => room.id === id)?.name ?? '—';
  }

  protected occupancy(session: Session): string {
    return this.translate.instant('gestion.program.planner.occupancy', {
      used: usedMinutes(session, this.board()?.buffer_minutes ?? 0),
      total: sessionMinutes(session),
    });
  }

  protected trackName(code: string | null): string {
    const track = this.tracks().find((item) => item.code === code);
    return track ? (this.lang() === 'en' && track.name_en) || track.name_fr : (code ?? '');
  }

  protected typeName(code: string | null): string {
    const type = this.types().find((item) => item.code === code);
    return type ? (this.lang() === 'en' && type.label_en) || type.label_fr : (code ?? '');
  }

  protected sessionIssues(session: Session): ProgramConflict[] {
    return sessionConflicts(this.board()?.conflicts ?? [], session.id);
  }

  protected slotIssues(slot: Slot): ProgramConflict[] {
    return slotConflicts(this.board()?.conflicts ?? [], slot.id);
  }

  /** Phrase d'un conflit (RG-12, RG-13) : noms des personnes, jamais d'adresse. */
  protected describe(conflict: ProgramConflict): string {
    const sessions = conflict.sessions
      .map((id) => this.board()?.sessions.find((item) => item.id === id))
      .filter((item): item is Session => !!item);
    const names = sessions
      .map((item) => this.translate.instant('gestion.program.quoted', { title: this.title(item) }))
      .join(', ');
    return this.translate.instant(`gestion.program.conflicts.${conflict.kind}`, {
      sessions: names,
      person: conflict.person,
      minutes: conflict.minutes,
      room: sessions[0] ? this.roomName(sessions[0].room) : '',
    });
  }

  protected setFilter(name: keyof ToScheduleFilters, value: string): void {
    this.filters.update((current) => ({ ...current, [name]: value }));
  }

  /** Affiche la session d'un conflit : jour choisi, puis focus sur la session. */
  protected show(sessionId: number): void {
    const session = this.board()?.sessions.find((item) => item.id === sessionId);
    if (!session) {
      return;
    }
    this.selectedDay.set(sessionDay(session));
    this.focus(`#session-card-${sessionId}`);
  }

  protected toggle(key: string): void {
    this.panel.set(this.panel() === key ? null : key);
    if (this.panel()) {
      this.focus(`#panel-${key.replace(':', '-')} select`);
    }
  }

  /** Focus, après le rendu, sur le premier élément trouvé parmi les sélecteurs. */
  private focus(...selectors: string[]): void {
    afterNextRender(
      () => {
        const root = this.host.nativeElement;
        selectors
          .map((selector) => root.querySelector<HTMLElement>(selector))
          .find((element) => !!element)
          ?.focus();
      },
      { injector: this.injector },
    );
  }

  // --- Actions (souris et clavier) -----------------------------------------------------------

  /** Place une communication dans une session (en fin de session par défaut). */
  protected async place(
    submission: ScheduledSubmission,
    sessionId: number,
    position?: number,
  ): Promise<void> {
    const session = this.board()?.sessions.find((item) => item.id === sessionId);
    if (!session) {
      return;
    }
    const done = await this.write(
      (revision) =>
        this.api.createSlot(this.edition(), revision, session.id, {
          submission: submission.id,
          ...(position === undefined ? {} : { position }),
        }),
      'gestion.program.planner.placed',
      { title: submission.title, session: this.title(session) },
    );
    if (done) {
      this.panel.set(null);
    }
  }

  /** Déplace un créneau dans sa session ou vers une autre (position dans la cible). */
  protected async move(slot: Slot, sessionId: number, position?: number): Promise<void> {
    const session = this.board()?.sessions.find((item) => item.id === sessionId);
    if (!session) {
      return;
    }
    const done = await this.write(
      (revision) =>
        this.api.updateSlot(this.edition(), revision, slot.id, {
          session: session.id,
          ...(position === undefined ? { position: session.slots.length } : { position }),
        }),
      'gestion.program.planner.moved',
      { title: this.slotLabel(slot), session: this.title(session), position: (position ?? 0) + 1 },
    );
    if (done) {
      this.panel.set(null);
    }
  }

  protected async shift(slot: Slot, session: Session, delta: -1 | 1): Promise<void> {
    const position = slot.position + delta;
    if (position < 0 || position >= session.slots.length) {
      return;
    }
    await this.move(slot, session.id, position);
    // Le focus suit le créneau ; en tête ou en fin de session, le bouton utilisé se désactive :
    // l'autre flèche, sinon « Actions… », prend le relais.
    const [same, other] = delta < 0 ? ['up', 'down'] : ['down', 'up'];
    this.focus(
      `#slot-${slot.id} .${same}:enabled`,
      `#slot-${slot.id} .${other}:enabled`,
      `#slot-${slot.id} .more`,
    );
  }

  protected async resize(slot: Slot, raw: string): Promise<void> {
    const duration = Number(raw);
    if (!Number.isInteger(duration) || duration < 1 || duration > 600) {
      this.errors.set([this.translate.instant('gestion.program.planner.badDuration')]);
      return;
    }
    await this.write(
      (revision) =>
        this.api.updateSlot(this.edition(), revision, slot.id, { duration_min: duration }),
      'gestion.program.planner.resized',
      { title: this.slotLabel(slot), count: duration },
    );
  }

  protected async unplace(slot: Slot): Promise<void> {
    await this.write(
      (revision) => this.api.deleteSlot(this.edition(), revision, slot.id),
      slot.submission ? 'gestion.program.planner.unplaced' : 'gestion.program.free.removed',
      { title: this.slotLabel(slot) },
    );
    this.focus('#pool-title');
  }

  // --- Glisser-déposer (CDK) -----------------------------------------------------------------

  /** La liste « à programmer » ne reçoit que des communications placées. */
  protected readonly poolAccepts = (drag: CdkDrag<DragItem>): boolean =>
    drag.data.kind === 'slot' && !!drag.data.slot.submission;

  /** Pas de communication dans une pause, un repas ou une activité sociale. */
  protected readonly sessionAccepts =
    (session: Session) =>
    (drag: CdkDrag<DragItem>): boolean =>
      !NON_SCIENTIFIC_KINDS.includes(session.kind) ||
      (drag.data.kind === 'slot' && !drag.data.slot.submission);

  protected async drop(event: CdkDragDrop<DropTarget, DropTarget, DragItem>): Promise<void> {
    const item = event.item.data;
    const target = event.container.data;
    if (target.kind === 'pool') {
      if (item.kind === 'slot') {
        await this.unplace(item.slot);
      }
      return;
    }
    if (item.kind === 'submission') {
      await this.place(item.submission, target.session.id, event.currentIndex);
      return;
    }
    if (event.previousContainer === event.container && event.previousIndex === event.currentIndex) {
      return;
    }
    await this.move(item.slot, target.session.id, event.currentIndex);
  }
}
