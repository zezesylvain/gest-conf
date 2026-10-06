import {
  ChangeDetectionStrategy,
  Component,
  computed,
  ElementRef,
  inject,
  signal,
} from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import {
  ErrorSummary,
  fieldErrorMessage,
  focusFirstInvalid,
  PageHeader,
  PersonSearch,
  Session,
  SessionKind,
  SessionRole,
  SessionRoleKind,
  SessionWriteRequest,
  Slot,
  Track,
  toDateTimeLocalValue,
} from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { EditionApi } from '../../core/edition-api';
import { PersonPicker } from './person-picker';
import { ProgramPage } from './program-page';
import {
  dayLabel,
  localTime,
  programDays,
  SESSION_KINDS,
  SESSION_ROLE_KINDS,
  sessionConflicts,
  sessionDay,
  sessionTitle,
  sortSessions,
} from './program-support';

/**
 * Sessions du programme (plan L5, I2, I10, I11, I12) : type, titres, salle, horaires saisis
 * à l'heure de l'édition (convertis par le serveur, qui refuse une heure inexistante ou
 * ambiguë), consignes ; rôles de séance et éléments libres (intervenant invité). Le placement
 * des communications se fait dans le planificateur.
 */
@Component({
  selector: 'gestion-sessions-page',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TranslatePipe,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    ErrorSummary,
    PageHeader,
    PersonPicker,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './sessions-page.html',
  styleUrl: '../page.scss',
  styles: `
    h3 {
      margin: 1rem 0 0.5rem;
      font-size: 1.05rem;
    }
    .people {
      list-style: none;
      padding: 0;
      margin: 0 0 0.5rem;
      display: grid;
      gap: 0.25rem;
    }
    .people li {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      align-items: center;
    }
    .conflict {
      border-color: var(--gc-danger);
      color: var(--gc-danger);
    }
  `,
})
export class SessionsPage extends ProgramPage {
  private readonly fb = inject(NonNullableFormBuilder);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly editionApi = inject(EditionApi);

  protected readonly kinds = SESSION_KINDS;
  protected readonly roleKinds = SESSION_ROLE_KINDS;
  protected readonly tracks = signal<Track[]>([]);
  /** `null` : pas de formulaire ; `0` : création ; sinon : session modifiée. */
  protected readonly editing = signal<number | null>(null);
  protected readonly rolePerson = signal<PersonSearch | null>(null);
  protected readonly speaker = signal<PersonSearch | null>(null);

  protected readonly form = this.fb.group({
    kind: ['parallel' as SessionKind, Validators.required],
    title_fr: ['', [Validators.required, Validators.maxLength(255)]],
    title_en: ['', Validators.maxLength(255)],
    description_fr: ['', Validators.maxLength(5000)],
    description_en: ['', Validators.maxLength(5000)],
    track: [null as string | null],
    room: [null as number | null],
    starts_local: ['', Validators.required],
    ends_local: ['', Validators.required],
    instructions: ['', Validators.maxLength(5000)],
  });
  protected readonly roleForm = this.fb.group({
    role: ['chair' as SessionRoleKind, Validators.required],
  });
  protected readonly freeForm = this.fb.group({
    title_fr: ['', [Validators.required, Validators.maxLength(300)]],
    title_en: ['', Validators.maxLength(300)],
    duration_min: [20, [Validators.required, Validators.min(1), Validators.max(600)]],
  });

  /** Sessions groupées par jour, à l'heure de l'édition. */
  protected readonly days = computed(() => {
    const board = this.board();
    if (!board) {
      return [];
    }
    const sessions = sortSessions(board.sessions);
    return programDays(board)
      .map((day) => ({ day, sessions: sessions.filter((item) => sessionDay(item) === day) }))
      .filter((group) => group.sessions.length);
  });
  /** Session en cours de modification, relue dans le dernier brouillon. */
  protected readonly current = computed(
    () => this.board()?.sessions.find((item) => item.id === this.editing()) ?? null,
  );
  protected readonly activeRooms = computed(() =>
    (this.board()?.rooms ?? []).filter(
      (room) => room.is_active !== false || room.id === this.current()?.room,
    ),
  );

  override async ngOnInit(): Promise<void> {
    try {
      this.tracks.set(await this.editionApi.tracks(this.edition()));
    } catch {
      // Thématiques facultatives : leur absence n'empêche pas l'écran.
    }
    await super.ngOnInit();
  }

  protected title(session: Session): string {
    return sessionTitle(session, this.lang());
  }

  protected day(day: string): string {
    return dayLabel(day, this.lang());
  }

  protected hours(session: Session): string {
    return `${localTime(session.starts_local)} – ${localTime(session.ends_local)}`;
  }

  protected roomName(id: number | null): string {
    if (id === null) {
      return this.translate.instant('gestion.program.noRoom');
    }
    return this.board()?.rooms.find((room) => room.id === id)?.name ?? '—';
  }

  protected conflictCount(session: Session): number {
    return sessionConflicts(this.board()?.conflicts ?? [], session.id).length;
  }

  protected freeSlots(session: Session): Slot[] {
    return session.slots.filter((slot) => !slot.submission);
  }

  protected trackName(code: string): string {
    const track = this.tracks().find((item) => item.code === code);
    return track ? (this.lang() === 'en' && track.name_en) || track.name_fr : code;
  }

  protected error(name: string): string {
    const control = this.form.get(name);
    return control ? fieldErrorMessage(this.translate, control) : '';
  }

  protected freeError(name: string): string {
    const control = this.freeForm.get(name);
    return control ? fieldErrorMessage(this.translate, control) : '';
  }

  protected startCreate(): void {
    const day = this.board()?.days[0] ?? '';
    this.form.reset({
      kind: 'parallel',
      title_fr: '',
      title_en: '',
      description_fr: '',
      description_en: '',
      track: null,
      room: null,
      starts_local: day ? `${day}T09:00` : '',
      ends_local: day ? `${day}T10:30` : '',
      instructions: '',
    });
    this.errors.set([]);
    this.editing.set(0);
  }

  protected startEdit(session: Session): void {
    this.form.reset({
      kind: session.kind,
      title_fr: session.title_fr,
      title_en: session.title_en,
      description_fr: session.description_fr,
      description_en: session.description_en,
      track: session.track,
      room: session.room,
      starts_local: toDateTimeLocalValue(session.starts_local),
      ends_local: toDateTimeLocalValue(session.ends_local),
      instructions: session.instructions,
    });
    this.roleForm.reset({ role: 'chair' });
    this.freeForm.reset({ title_fr: '', title_en: '', duration_min: 20 });
    this.rolePerson.set(null);
    this.speaker.set(null);
    this.errors.set([]);
    this.editing.set(session.id);
  }

  protected cancel(): void {
    this.editing.set(null);
    this.errors.set([]);
  }

  protected async save(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      focusFirstInvalid(this.host.nativeElement);
      return;
    }
    const body: SessionWriteRequest = this.form.getRawValue();
    const id = this.editing();
    const known = new Set(this.board()?.sessions.map((item) => item.id));
    const saved = await this.write(
      (revision) =>
        id
          ? this.api.updateSession(this.edition(), revision, id, body)
          : this.api.createSession(this.edition(), revision, body),
      'gestion.settings.saved',
      {},
      this.form,
    );
    if (!saved) {
      focusFirstInvalid(this.host.nativeElement);
      return;
    }
    if (!id) {
      // Création : on reste sur la nouvelle session, pour ses rôles et ses éléments libres.
      const created = this.board()?.sessions.find((item) => !known.has(item.id));
      if (created) {
        this.startEdit(created);
        this.status.set(this.translate.instant('gestion.program.sessions.created'));
      } else {
        this.editing.set(null);
      }
    }
  }

  protected async remove(session: Session): Promise<void> {
    if (
      !(await this.confirm('gestion.program.sessions.delete', {
        name: this.title(session),
        count: session.slots.filter((slot) => slot.submission).length,
      }))
    ) {
      return;
    }
    const removed = await this.write(
      (revision) => this.api.deleteSession(this.edition(), revision, session.id),
      'gestion.settings.deleted',
    );
    if (removed && this.editing() === session.id) {
      this.editing.set(null);
    }
  }

  // --- Rôles de séance (I10) -----------------------------------------------------------------

  protected async addRole(session: Session): Promise<void> {
    const person = this.rolePerson();
    if (!person) {
      return;
    }
    const role = this.roleForm.getRawValue().role;
    const added = await this.write(
      (revision) =>
        this.api.addRole(this.edition(), revision, session.id, { user: person.id, role }),
      'gestion.program.roles.added',
      { name: person.name },
    );
    if (added) {
      this.rolePerson.set(null);
    }
  }

  protected async removeRole(role: SessionRole): Promise<void> {
    await this.write(
      (revision) => this.api.removeRole(this.edition(), revision, role.id),
      'gestion.program.roles.removed',
      { name: role.person.name },
    );
  }

  // --- Éléments libres (I3, I11) -------------------------------------------------------------

  protected async addFree(session: Session): Promise<void> {
    if (this.freeForm.invalid) {
      this.freeForm.markAllAsTouched();
      return;
    }
    const value = this.freeForm.getRawValue();
    const added = await this.write(
      (revision) =>
        this.api.createSlot(this.edition(), revision, session.id, {
          ...value,
          speaker: this.speaker()?.id ?? null,
        }),
      'gestion.program.free.added',
      { title: value.title_fr },
      this.freeForm,
    );
    if (added) {
      this.freeForm.reset({ title_fr: '', title_en: '', duration_min: 20 });
      this.speaker.set(null);
    }
  }

  protected async removeFree(slot: Slot): Promise<void> {
    await this.write(
      (revision) => this.api.deleteSlot(this.edition(), revision, slot.id),
      'gestion.program.free.removed',
      { title: slot.title_fr },
    );
  }
}
