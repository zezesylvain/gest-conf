import { ChangeDetectionStrategy, Component, ElementRef, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import {
  Equipment,
  ErrorSummary,
  fieldErrorMessage,
  focusFirstInvalid,
  PageHeader,
  Room,
  RoomWriteRequest,
} from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { ProgramPage } from './program-page';
import { EQUIPMENT_KINDS } from './program-support';

/**
 * Salles de l'édition (plan L5, I9) : capacité, équipements en liste fermée, accessibilité.
 * Une salle utilisée ne se supprime pas (409 `in_use`) : elle se désactive.
 */
@Component({
  selector: 'gestion-rooms-page',
  imports: [
    ReactiveFormsModule,
    TranslatePipe,
    MatButtonModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './rooms-page.html',
  styleUrl: '../page.scss',
  styles: `
    fieldset {
      border: 0;
      margin: 0 0 0.75rem;
      padding: 0;
    }
    legend {
      font-weight: 600;
      margin-bottom: 0.25rem;
    }
    .equipment {
      display: flex;
      flex-wrap: wrap;
      gap: 0 1rem;
    }
  `,
})
export class RoomsPage extends ProgramPage {
  private readonly fb = inject(NonNullableFormBuilder);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  protected readonly equipmentList = EQUIPMENT_KINDS;
  /** `null` : pas de formulaire ; `0` : création ; sinon : salle modifiée. */
  protected readonly editing = signal<number | null>(null);
  protected readonly form = this.fb.group({
    name: ['', [Validators.required, Validators.maxLength(150)]],
    capacity: [null as number | null, [Validators.min(0), Validators.max(100000)]],
    equipment: [[] as Equipment[]],
    note: ['', Validators.maxLength(2000)],
    is_accessible: [false],
    access_note: ['', Validators.maxLength(255)],
    is_active: [true],
    position: [0, [Validators.min(0), Validators.max(32767)]],
  });

  protected rooms(): Room[] {
    return [...(this.board()?.rooms ?? [])].sort(
      (a, b) => (a.position ?? 0) - (b.position ?? 0) || a.name.localeCompare(b.name),
    );
  }

  protected equipmentLabels(room: Room): string {
    return room.equipment
      .map((item) => this.translate.instant(`gestion.program.equipment.${item}`))
      .join(', ');
  }

  protected error(name: string): string {
    const control = this.form.get(name);
    return control ? fieldErrorMessage(this.translate, control) : '';
  }

  protected hasEquipment(item: Equipment): boolean {
    return this.form.controls.equipment.value.includes(item);
  }

  protected toggleEquipment(item: Equipment, checked: boolean): void {
    const current = this.form.controls.equipment.value.filter((value) => value !== item);
    this.form.controls.equipment.setValue(checked ? [...current, item] : current);
  }

  protected startCreate(): void {
    this.form.reset({
      name: '',
      capacity: null,
      equipment: [],
      note: '',
      is_accessible: false,
      access_note: '',
      is_active: true,
      position: this.board()?.rooms.length ?? 0,
    });
    this.errors.set([]);
    this.editing.set(0);
  }

  protected startEdit(room: Room): void {
    this.form.reset({
      name: room.name,
      capacity: room.capacity ?? null,
      equipment: [...room.equipment],
      note: room.note ?? '',
      is_accessible: room.is_accessible ?? false,
      access_note: room.access_note ?? '',
      is_active: room.is_active ?? true,
      position: room.position ?? 0,
    });
    this.errors.set([]);
    this.editing.set(room.id);
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
    const raw = this.form.getRawValue();
    const body: RoomWriteRequest = {
      ...raw,
      capacity: raw.capacity === null || (raw.capacity as unknown) === '' ? null : raw.capacity,
    };
    const id = this.editing();
    const saved = await this.write(
      (revision) =>
        id
          ? this.api.updateRoom(this.edition(), revision, id, body)
          : this.api.createRoom(this.edition(), revision, body),
      'gestion.settings.saved',
      {},
      this.form,
    );
    if (saved) {
      this.editing.set(null);
    } else {
      focusFirstInvalid(this.host.nativeElement);
    }
  }

  protected async toggleActive(room: Room): Promise<void> {
    await this.write(
      (revision) =>
        this.api.updateRoom(this.edition(), revision, room.id, {
          is_active: !(room.is_active ?? true),
        }),
      'gestion.settings.saved',
    );
  }

  protected async remove(room: Room): Promise<void> {
    if (!(await this.confirm('gestion.program.rooms.delete', { name: room.name }))) {
      return;
    }
    await this.write(
      (revision) => this.api.deleteRoom(this.edition(), revision, room.id),
      'gestion.settings.deleted',
    );
  }
}
