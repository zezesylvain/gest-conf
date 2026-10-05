import { Injectable, signal } from '@angular/core';

/**
 * Jeton d'invitation (ou lien de liaison) lu dans le fragment, gardé **en mémoire** le
 * temps d'une connexion faite dans l'application (navigation interne). Jamais stocké :
 * après une inscription (vérification de l'adresse par e-mail, nouvelle page), il faut
 * rouvrir le lien de l'invitation.
 */
@Injectable({ providedIn: 'root' })
export class PendingInvitation {
  readonly token = signal<string | null>(null);
  readonly link = signal<string | null>(null);

  /** Valeur du fragment : `<jeton>` ou `lier=<lien>`. */
  take(fragment: string | null): void {
    if (!fragment) {
      return;
    }
    if (fragment.startsWith('lier=')) {
      this.link.set(fragment.slice('lier='.length) || null);
    } else {
      this.token.set(fragment);
      this.link.set(null);
    }
  }

  clear(): void {
    this.token.set(null);
    this.link.set(null);
  }
}
