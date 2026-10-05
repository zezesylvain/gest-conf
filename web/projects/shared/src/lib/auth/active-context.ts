import { DOCUMENT, inject, Injectable } from '@angular/core';

const EDITION_KEY = 'gc.gestion.edition';
const ROLE_KEY = 'gc.gestion.role';

/**
 * Édition et rôle actifs de la gestion (plan L1 §5.8) : **purement ergonomiques**. Le
 * serveur ne lit aucun rôle actif ; l'édition active est dans l'URL. Préférences gardées
 * dans `localStorage`, dont l'accès peut échouer (navigation privée, stockage bloqué).
 */
@Injectable({ providedIn: 'root' })
export class ActiveContext {
  private readonly storage = storageOf(inject(DOCUMENT));

  lastEditionId(): number | null {
    const value = Number(this.read(EDITION_KEY));
    return Number.isInteger(value) && value > 0 ? value : null;
  }

  rememberEdition(id: number): void {
    this.write(EDITION_KEY, String(id));
  }

  /** Rôle actif mémorisé pour une édition (filtre des menus), `null` = tous. */
  activeRole(editionId: number): string | null {
    return this.read(`${ROLE_KEY}.${editionId}`);
  }

  setActiveRole(editionId: number, role: string | null): void {
    if (role) {
      this.write(`${ROLE_KEY}.${editionId}`, role);
    } else {
      this.remove(`${ROLE_KEY}.${editionId}`);
    }
  }

  private read(key: string): string | null {
    try {
      return this.storage?.getItem(key) ?? null;
    } catch {
      return null;
    }
  }

  private write(key: string, value: string): void {
    try {
      this.storage?.setItem(key, value);
    } catch {
      // Stockage indisponible : la préférence n'est simplement pas retenue.
    }
  }

  private remove(key: string): void {
    try {
      this.storage?.removeItem(key);
    } catch {
      // Idem.
    }
  }
}

function storageOf(document: Document): Storage | null {
  try {
    return document.defaultView?.localStorage ?? null;
  } catch {
    return null;
  }
}
