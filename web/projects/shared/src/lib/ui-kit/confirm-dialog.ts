import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { TranslatePipe } from '@ngx-translate/core';

/** Textes déjà traduits par l'appelant. */
export interface ConfirmDialogData {
  title: string;
  message: string;
  confirmLabel: string;
  /** Motif demandé (révocation, changement de statut…), obligatoire s'il est demandé. */
  reasonLabel?: string;
}

export interface ConfirmDialogResult {
  confirmed: true;
  reason: string;
}

/**
 * Confirmation d'une action sensible ou irréversible, avec motif facultatif (journalisé
 * côté serveur). Résultat : `ConfirmDialogResult`, ou `undefined` si l'on renonce.
 */
@Component({
  selector: 'gc-confirm-dialog',
  imports: [
    ReactiveFormsModule,
    TranslatePipe,
    MatDialogModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h2 mat-dialog-title>{{ data.title }}</h2>
    <form [formGroup]="form" (ngSubmit)="confirm()" novalidate>
      <mat-dialog-content>
        <p>{{ data.message }}</p>
        @if (data.reasonLabel) {
          <mat-form-field appearance="outline" class="reason">
            <mat-label>{{ data.reasonLabel }}</mat-label>
            <textarea matInput formControlName="reason" rows="3" required></textarea>
            <mat-error>{{ 'shared.form.required' | translate }}</mat-error>
          </mat-form-field>
        }
      </mat-dialog-content>
      <mat-dialog-actions align="end">
        <button mat-button type="button" (click)="dialogRef.close()">
          {{ 'shared.reauth.cancel' | translate }}
        </button>
        <button mat-flat-button type="submit">{{ data.confirmLabel }}</button>
      </mat-dialog-actions>
    </form>
  `,
  styles: `
    .reason {
      width: 100%;
    }
  `,
})
export class ConfirmDialog {
  protected readonly data = inject<ConfirmDialogData>(MAT_DIALOG_DATA);
  protected readonly dialogRef =
    inject<MatDialogRef<ConfirmDialog, ConfirmDialogResult>>(MatDialogRef);
  protected readonly form = inject(NonNullableFormBuilder).group({
    reason: ['', this.data.reasonLabel ? [Validators.required, Validators.maxLength(500)] : []],
  });

  protected confirm(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.dialogRef.close({ confirmed: true, reason: this.form.controls.reason.value.trim() });
  }
}
