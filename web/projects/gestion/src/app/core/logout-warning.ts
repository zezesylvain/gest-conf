import { EnvironmentInjector } from '@angular/core';
import { MatDialog } from '@angular/material/dialog';
import { ConfirmDialog, ConfirmDialogData, ConfirmDialogResult } from '@gestconf/shared';
import { firstValueFrom } from 'rxjs';

/**
 * Avertissement de déconnexion avec des pointages non synchronisés (plan L7, K5). Chargé à
 * la demande par la coque, comme la fenêtre de réauthentification : `MatDialog` et la
 * fenêtre de confirmation restent hors du bundle initial.
 */
export async function confirmLogout(
  injector: EnvironmentInjector,
  data: ConfirmDialogData,
): Promise<boolean> {
  const ref = injector
    .get(MatDialog)
    .open<ConfirmDialog, ConfirmDialogData, ConfirmDialogResult>(ConfirmDialog, {
      data,
      width: '30rem',
    });
  return !!(await firstValueFrom(ref.afterClosed()));
}
