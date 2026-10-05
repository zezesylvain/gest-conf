import { EnvironmentInjector, inject, Injectable } from '@angular/core';

import { MeStore } from '../auth/me.store';

/**
 * Ouvre la fenêtre de réauthentification. Le composant **et** `MatDialog` sont chargés à
 * la demande (rien dans le bundle initial des coques). La coque de chaque application
 * l'enregistre auprès de `ReauthenticationPrompt` : `prompt.register(() => dialog.open())`.
 */
@Injectable({ providedIn: 'root' })
export class ReauthenticationDialog {
  private readonly injector = inject(EnvironmentInjector);
  private readonly meStore = inject(MeStore);

  async open(): Promise<boolean> {
    const { openReauthDialog } = await import('./reauth-dialog');
    const done = await openReauthDialog(this.injector);
    if (done) {
      // État 2FA de la session (mfa_verified) à jour après une réauthentification.
      await this.meStore.load().catch(() => undefined);
    }
    return done;
  }
}
