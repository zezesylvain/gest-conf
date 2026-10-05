import { computed, Directive, ElementRef, inject, input, OnInit, signal } from '@angular/core';
import { FormGroup } from '@angular/forms';
import { MatDialog } from '@angular/material/dialog';
import {
  ConfirmDialog,
  ConfirmDialogData,
  ConfirmDialogResult,
  fieldErrorMessage,
  focusFirstInvalid,
  MeStore,
} from '@gestconf/shared';
import { TranslateService } from '@ngx-translate/core';
import { firstValueFrom } from 'rxjs';

import { EditionApi } from '../../core/edition-api';
import { editionCapabilities, errorMessages } from '../../core/page-support';

/** Valeur complète d'un formulaire (champs désactivés compris). */
export type RawValue<F extends FormGroup> = ReturnType<F['getRawValue']>;

/**
 * Base des listes éditables d'une édition (thématiques, types, dates clés) : chargement,
 * création, modification, suppression confirmée. Écriture réservée à `edition.write`
 * (interface) ; le serveur décide (règle n° 2).
 */
@Directive()
export abstract class ItemListPage<
  T extends { id: number },
  F extends FormGroup,
> implements OnInit {
  readonly editionId = input.required<string>();

  protected readonly api = inject(EditionApi);
  protected readonly translate = inject(TranslateService);
  private readonly meStore = inject(MeStore);
  private readonly dialog = inject(MatDialog);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  protected abstract readonly form: F;
  /** Préfixe des clés de traduction de la page (`gestion.settings.tracks`…). */
  protected abstract readonly keys: string;

  protected readonly items = signal<T[]>([]);
  /** `null` : pas de formulaire ; `0` : création ; sinon : identifiant modifié. */
  protected readonly editing = signal<number | null>(null);
  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  protected readonly canWrite = computed(() =>
    editionCapabilities(this.meStore, this.editionId()).includes('edition.write'),
  );

  protected abstract fetch(editionId: number): Promise<T[]>;
  protected abstract create(editionId: number, value: RawValue<F>): Promise<T>;
  protected abstract update(editionId: number, id: number, value: RawValue<F>): Promise<T>;
  protected abstract remove(editionId: number, id: number): Promise<void>;
  protected abstract toFormValue(item: T): RawValue<F>;
  protected abstract emptyValue(): RawValue<F>;
  protected abstract describe(item: T): string;

  async ngOnInit(): Promise<void> {
    await this.reload();
    this.loading.set(false);
  }

  protected error(name: string): string {
    const control = this.form.get(name);
    return control ? fieldErrorMessage(this.translate, control) : '';
  }

  protected startCreate(): void {
    this.form.reset(this.emptyValue());
    this.errors.set([]);
    this.editing.set(0);
  }

  protected startEdit(item: T): void {
    this.form.reset(this.toFormValue(item));
    this.errors.set([]);
    this.editing.set(item.id);
  }

  protected cancel(): void {
    this.editing.set(null);
    this.errors.set([]);
  }

  protected async save(): Promise<void> {
    this.errors.set([]);
    this.status.set('');
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      focusFirstInvalid(this.host.nativeElement);
      return;
    }
    const id = this.editing();
    const editionId = Number(this.editionId());
    this.saving.set(true);
    try {
      if (id) {
        await this.update(editionId, id, this.form.getRawValue());
      } else {
        await this.create(editionId, this.form.getRawValue());
      }
      this.editing.set(null);
      this.status.set(this.translate.instant('gestion.settings.saved'));
      await this.reload();
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error, this.form));
      focusFirstInvalid(this.host.nativeElement);
    } finally {
      this.saving.set(false);
    }
  }

  protected async confirmDelete(item: T): Promise<void> {
    const data: ConfirmDialogData = {
      title: this.translate.instant('gestion.settings.deleteTitle'),
      message: this.translate.instant('gestion.settings.deleteMessage', {
        name: this.describe(item),
      }),
      confirmLabel: this.translate.instant('gestion.settings.delete'),
    };
    const ref = this.dialog.open<ConfirmDialog, ConfirmDialogData, ConfirmDialogResult>(
      ConfirmDialog,
      { data, width: '30rem' },
    );
    if (!(await firstValueFrom(ref.afterClosed()))) {
      return;
    }
    this.errors.set([]);
    try {
      await this.remove(Number(this.editionId()), item.id);
      this.status.set(this.translate.instant('gestion.settings.deleted'));
      await this.reload();
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
  }

  private async reload(): Promise<void> {
    try {
      this.items.set(await this.fetch(Number(this.editionId())));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
  }
}
