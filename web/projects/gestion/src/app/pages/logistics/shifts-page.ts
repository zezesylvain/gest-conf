import { ChangeDetectionStrategy, Component, inject, input, OnInit, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import {
  ErrorSummary,
  LanguageService,
  PageHeader,
  Shift,
  ShiftBoard,
  TaskPerson,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { LogisticsApi } from '../../core/logistics-api';
import { errorMessages } from '../../core/page-support';
import { confirmAction } from '../events/events-support';
import { localLabel } from './logistics-support';

/**
 * Postes de bénévolat (plan L8, N9 ; `volunteers.plan`) : intitulés, lieu, horaires **en
 * heure locale de l'édition**, besoin ; affectation des bénévoles de l'édition, refusée par
 * le serveur quand deux postes d'une même personne se chevauchent ; places manquantes.
 */
@Component({
  selector: 'gestion-shifts-page',
  imports: [
    ReactiveFormsModule,
    TranslatePipe,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './shifts-page.html',
  styleUrl: '../page.scss',
  styles: `
    .assign {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      align-items: center;
    }
    select {
      font: inherit;
      padding: 0.25rem;
    }
  `,
})
export class ShiftsPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(LogisticsApi);
  private readonly dialog = inject(MatDialog);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly board = signal<ShiftBoard | null>(null);
  protected readonly editing = signal<Shift | null>(null);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');

  protected readonly form = inject(NonNullableFormBuilder).group({
    title_fr: ['', [Validators.required, Validators.maxLength(150)]],
    title_en: ['', Validators.maxLength(150)],
    place: ['', Validators.maxLength(150)],
    starts_local: ['', Validators.required],
    ends_local: ['', Validators.required],
    needed: [1, [Validators.min(1), Validators.max(100)]],
    instructions: ['', Validators.maxLength(1000)],
  });

  async ngOnInit(): Promise<void> {
    try {
      this.board.set(await this.api.shifts(this.edition()));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }

  private edition(): number {
    return Number(this.editionId());
  }

  protected local(value: string): string {
    return localLabel(value, this.language.current());
  }

  protected title(shift: Shift): string {
    return (this.language.current() === 'en' && shift.title_en) || shift.title_fr;
  }

  protected available(shift: Shift): TaskPerson[] {
    const assigned = new Set(shift.volunteers.map((person) => person.id));
    return (this.board()?.volunteers ?? []).filter((person) => !assigned.has(person.id));
  }

  protected edit(shift: Shift): void {
    this.editing.set(shift);
    this.form.reset({
      title_fr: shift.title_fr,
      title_en: shift.title_en,
      place: shift.place,
      starts_local: shift.starts_local,
      ends_local: shift.ends_local,
      needed: shift.needed,
      instructions: shift.instructions,
    });
  }

  protected cancelEdit(): void {
    this.editing.set(null);
    this.form.reset();
  }

  protected async submit(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const value = this.form.getRawValue();
    const body = { ...value, needed: Number(value.needed) };
    const shift = this.editing();
    await this.run(shift ? 'gestion.shifts.updated' : 'gestion.shifts.created', async () => {
      const board = shift
        ? await this.api.updateShift(this.edition(), shift.id, body)
        : await this.api.createShift(this.edition(), body);
      this.cancelEdit();
      return board;
    });
  }

  protected async remove(shift: Shift): Promise<void> {
    const answer = await confirmAction(this.dialog, this.translate, 'gestion.shifts.delete', {
      title: this.title(shift),
    });
    if (!answer) return;
    await this.run('gestion.shifts.deleted', () => this.api.deleteShift(this.edition(), shift.id));
  }

  protected async assign(shift: Shift, select: HTMLSelectElement): Promise<void> {
    const volunteer = Number(select.value);
    if (!volunteer) return;
    await this.run('gestion.shifts.assigned', () =>
      this.api.assign(this.edition(), shift.id, volunteer),
    );
  }

  protected async unassign(shift: Shift, person: TaskPerson): Promise<void> {
    await this.run('gestion.shifts.unassigned', () =>
      this.api.unassign(this.edition(), shift.id, person.id),
    );
  }

  private async run(message: string, action: () => Promise<ShiftBoard>): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    this.status.set('');
    try {
      this.board.set(await action());
      this.status.set(this.translate.instant(message));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error, this.form));
    } finally {
      this.busy.set(false);
    }
  }
}
