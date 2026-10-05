import { computed, inject, Injectable, signal } from '@angular/core';
import { ActiveContext, MeStore, Role } from '@gestconf/shared';

import { buildNavigation, catalogue, MANAGEMENT_ROLES } from './navigation';

/**
 * État de navigation partagé par le rail (mise en page de l'édition) et la recherche de la
 * barre haute (coque) : l'édition affichée et le rôle actif. Le rail et le catalogue de la
 * recherche sortent du même `computed` : une seule vérité.
 */
@Injectable({ providedIn: 'root' })
export class NavigationStore {
  private readonly meStore = inject(MeStore);
  private readonly context = inject(ActiveContext);

  /** Édition de l'URL, posée par la mise en page de l'édition ; `null` hors édition. */
  readonly editionId = signal<string | null>(null);
  private readonly selectedRole = signal<Role | null>(null);

  readonly edition = computed(() => {
    const id = this.editionId();
    return id === null
      ? undefined
      : this.meStore.me()?.editions.find((item) => String(item.id) === id);
  });
  /** Rôles de gestion détenus dans l'édition : choix du sélecteur « Rôle actif ». */
  readonly managementRoles = computed(() =>
    [...new Set((this.edition()?.roles ?? []).map((item) => item.role))].filter((role) =>
      MANAGEMENT_ROLES.includes(role),
    ),
  );
  /** Rôle actif s'il est encore détenu, sinon `null` (tous les rôles). */
  readonly activeRole = computed(() => {
    const role = this.selectedRole();
    return role && this.managementRoles().includes(role) ? role : null;
  });
  readonly groups = computed(() => {
    const edition = this.edition();
    return edition ? buildNavigation(edition.id, edition.capabilities, this.activeRole()) : [];
  });
  readonly entries = computed(() => catalogue(this.groups()));

  /** Entrée dans une édition : rôle actif mémorisé repris, édition retenue comme dernière. */
  enterEdition(editionId: string): void {
    this.editionId.set(editionId);
    const id = Number(editionId);
    this.selectedRole.set(
      Number.isInteger(id) ? (this.context.activeRole(id) as Role | null) : null,
    );
  }

  leaveEdition(): void {
    this.editionId.set(null);
    this.selectedRole.set(null);
  }

  selectRole(role: Role | null): void {
    this.selectedRole.set(role);
    const edition = this.edition();
    if (edition) {
      this.context.setActiveRole(edition.id, role);
    }
  }
}
