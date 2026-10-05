import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  signal,
} from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { ActiveContext, Capability, LanguageService, MeStore, Role } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { editionTitle, managedEditions } from '../core/managed-editions';

type Section = 'dashboard' | 'settings' | 'members' | 'audit';

interface NavItem {
  path: string;
  label: string;
  capability: Capability;
  section: Section;
}

const NAV: NavItem[] = [
  {
    path: 'tableau-de-bord',
    label: 'gestion.nav.dashboard',
    capability: 'edition.read',
    section: 'dashboard',
  },
  {
    path: 'parametrage/general',
    label: 'gestion.nav.general',
    capability: 'edition.read',
    section: 'settings',
  },
  {
    path: 'parametrage/thematiques',
    label: 'gestion.nav.tracks',
    capability: 'edition.read',
    section: 'settings',
  },
  {
    path: 'parametrage/types',
    label: 'gestion.nav.types',
    capability: 'edition.read',
    section: 'settings',
  },
  {
    path: 'parametrage/calendrier',
    label: 'gestion.nav.calendar',
    capability: 'edition.read',
    section: 'settings',
  },
  {
    path: 'parametrage/confidentialite',
    label: 'gestion.nav.confidentiality',
    capability: 'edition.read',
    section: 'settings',
  },
  {
    path: 'comites/membres',
    label: 'gestion.nav.members',
    capability: 'members.read',
    section: 'members',
  },
  {
    path: 'comites/invitations',
    label: 'gestion.nav.invitations',
    capability: 'members.read',
    section: 'members',
  },
  { path: 'audit', label: 'gestion.nav.audit', capability: 'audit.read', section: 'audit' },
];

/**
 * Rubriques mises en avant par rôle actif (plan L1 §5.8) : **filtre de menu seulement**,
 * jamais un droit. Le serveur ignore le rôle actif ; les capacités de `/me` décident.
 */
const ROLE_SECTIONS: Partial<Record<Role, Section[]>> = {
  ADMIN: ['dashboard', 'settings', 'members', 'audit'],
  CHAIR: ['dashboard', 'settings', 'members', 'audit'],
  SC_CHAIR: ['dashboard', 'members'],
  OC_MEMBER: ['dashboard', 'settings'],
};

/**
 * Mise en page d'une édition : sélecteurs d'édition et de rôle actif, menu filtré par les
 * capacités de `/me` dans cette édition (plan L1 §10.3). L'édition active est dans l'URL et
 * mémorisée comme dernière utilisée.
 */
@Component({
  selector: 'gestion-edition-layout',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './edition-layout.html',
  styleUrl: './edition-layout.scss',
})
export class EditionLayout {
  /** Paramètre `:editionId` de la route (liaison des entrées du routeur). */
  readonly editionId = input.required<string>();

  private readonly meStore = inject(MeStore);
  private readonly context = inject(ActiveContext);
  private readonly router = inject(Router);
  protected readonly language = inject(LanguageService);

  protected readonly editions = computed(() => managedEditions(this.meStore));
  protected readonly edition = computed(() =>
    this.meStore.me()?.editions.find((item) => String(item.id) === this.editionId()),
  );
  protected readonly managementRoles = computed(() =>
    [...new Set((this.edition()?.roles ?? []).map((item) => item.role))].filter(
      (role) => role in ROLE_SECTIONS,
    ),
  );
  protected readonly activeRole = signal<string | null>(null);
  protected readonly nav = computed(() => {
    const edition = this.edition();
    if (!edition) {
      return [];
    }
    const role = this.activeRole() as Role | null;
    const sections = role ? ROLE_SECTIONS[role] : undefined;
    return NAV.filter(
      (item) =>
        edition.capabilities.includes(item.capability) &&
        (!sections || sections.includes(item.section)),
    );
  });

  constructor() {
    effect(() => {
      const edition = this.edition();
      if (edition) {
        this.context.rememberEdition(edition.id);
        const remembered = this.context.activeRole(edition.id);
        this.activeRole.set(
          remembered && this.managementRoles().includes(remembered as Role) ? remembered : null,
        );
      }
    });
  }

  protected title(edition: { title_fr: string; title_en?: string }): string {
    return editionTitle(edition, this.language.current());
  }

  protected selectEdition(value: string): void {
    void this.router.navigate(['/editions', Number(value)]);
  }

  protected selectRole(value: string): void {
    const edition = this.edition();
    const role = value || null;
    this.activeRole.set(role);
    if (edition) {
      this.context.setActiveRole(edition.id, role);
    }
  }
}
