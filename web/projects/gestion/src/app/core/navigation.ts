import type { Capability, Role } from '@gestconf/shared';

/**
 * Table de navigation de la gestion, **source unique** (plan L2 §2.3, compétence
 * `recherche-menu-topbar-angular`) : le rail, la recherche d'écran et l'aide contextuelle
 * en dérivent tous trois. Aucun import Angular : la logique se teste sans DOM.
 *
 * Le rail n'est que le reflet des capacités de `/me` ; la sécurité reste aux gardes et,
 * surtout, au serveur (règle n° 2).
 */

export type NavGroupKey =
  | 'steering'
  | 'submissions'
  | 'reviewing'
  | 'program'
  | 'settings'
  | 'committees'
  | 'portal'
  | 'control'
  | 'help';

/** Entrée du rail, prête à afficher (libellés en clés de traduction). */
export interface NavEntry {
  key: string;
  /** URL absolue du routeur (`/editions/3/parametrage/general`, `/aide`). */
  url: string;
  label: string;
  /** Clé de traduction : mots du métier séparés par des virgules. */
  keywords: string;
  /** Identifiant de la fiche d'aide de l'écran. */
  help: string;
  group: NavGroupKey;
  /** Rang d'affichage dans le rail, qui sert aussi de tri stable à la recherche. */
  order: number;
}

export interface NavGroup {
  key: NavGroupKey;
  label: string;
  entries: NavEntry[];
}

/** Définition d'un écran : chemin relatif à l'édition, ou absolu (commençant par `/`). */
export interface ScreenDef {
  key: string;
  path: string;
  label: string;
  help: string;
  group: NavGroupKey;
  /** Capacité exigée dans l'édition ; `null` : écran ouvert à tout rôle de gestion. */
  capability: Capability | null;
}

export const GROUP_ORDER: readonly NavGroupKey[] = [
  'steering',
  'submissions',
  'reviewing',
  'program',
  'settings',
  'committees',
  'portal',
  'control',
  'help',
];

export const SCREENS: readonly ScreenDef[] = [
  {
    key: 'dashboard',
    path: 'tableau-de-bord',
    label: 'gestion.nav.dashboard',
    help: 'dashboard',
    group: 'steering',
    capability: 'edition.read',
  },
  {
    key: 'submissions',
    path: 'soumissions',
    label: 'gestion.nav.submissions',
    help: 'submissions',
    group: 'submissions',
    capability: 'submissions.read',
  },
  // Évaluation (plan L4, H1) : espace du relecteur, puis pilotage du président du CS.
  {
    key: 'myReviews',
    path: 'evaluations',
    label: 'gestion.nav.myReviews',
    help: 'my-reviews',
    group: 'reviewing',
    capability: 'reviews.write',
  },
  {
    key: 'expertise',
    path: 'expertises',
    label: 'gestion.nav.expertise',
    help: 'my-reviews',
    group: 'reviewing',
    capability: 'reviews.write',
  },
  {
    key: 'followUp',
    path: 'pilotage',
    label: 'gestion.nav.followUp',
    help: 'review-follow-up',
    group: 'reviewing',
    capability: 'reviews.manage',
  },
  {
    key: 'ranking',
    path: 'classement',
    label: 'gestion.nav.ranking',
    help: 'ranking',
    group: 'reviewing',
    capability: 'reviews.read_all',
  },
  // Programme (plan L5, I15) : lecture program.read ; écriture et publication revérifiées.
  {
    key: 'programPlanner',
    path: 'programme',
    label: 'gestion.nav.programPlanner',
    help: 'program-planner',
    group: 'program',
    capability: 'program.read',
  },
  {
    key: 'programSessions',
    path: 'programme/sessions',
    label: 'gestion.nav.programSessions',
    help: 'program-sessions',
    group: 'program',
    capability: 'program.read',
  },
  {
    key: 'programRooms',
    path: 'programme/salles',
    label: 'gestion.nav.programRooms',
    help: 'program-rooms',
    group: 'program',
    capability: 'program.read',
  },
  {
    key: 'programPublication',
    path: 'programme/publication',
    label: 'gestion.nav.programPublication',
    help: 'program-publication',
    group: 'program',
    capability: 'program.read',
  },
  {
    key: 'general',
    path: 'parametrage/general',
    label: 'gestion.nav.general',
    help: 'settings-general',
    group: 'settings',
    capability: 'edition.read',
  },
  {
    key: 'tracks',
    path: 'parametrage/thematiques',
    label: 'gestion.nav.tracks',
    help: 'settings-lists',
    group: 'settings',
    capability: 'edition.read',
  },
  {
    key: 'types',
    path: 'parametrage/types',
    label: 'gestion.nav.types',
    help: 'settings-lists',
    group: 'settings',
    capability: 'edition.read',
  },
  {
    key: 'calendar',
    path: 'parametrage/calendrier',
    label: 'gestion.nav.calendar',
    help: 'settings-calendar',
    group: 'settings',
    capability: 'edition.read',
  },
  {
    key: 'confidentiality',
    path: 'parametrage/confidentialite',
    label: 'gestion.nav.confidentiality',
    help: 'settings-confidentiality',
    group: 'settings',
    capability: 'edition.read',
  },
  {
    key: 'programSettings',
    path: 'parametrage/programme',
    label: 'gestion.nav.programSettings',
    help: 'settings-program',
    group: 'settings',
    capability: 'program.read',
  },
  {
    key: 'grids',
    path: 'parametrage/grilles',
    label: 'gestion.nav.grids',
    help: 'grids',
    group: 'settings',
    capability: 'edition.read',
  },
  {
    key: 'members',
    path: 'comites/membres',
    label: 'gestion.nav.members',
    help: 'members',
    group: 'committees',
    capability: 'members.read',
  },
  {
    key: 'invitations',
    path: 'comites/invitations',
    label: 'gestion.nav.invitations',
    help: 'invitations',
    group: 'committees',
    capability: 'members.read',
  },
  {
    key: 'portalSections',
    path: 'portail/sections',
    label: 'gestion.nav.portalSections',
    help: 'portal-sections',
    group: 'portal',
    capability: 'edition.read',
  },
  {
    key: 'portalPages',
    path: 'portail/pages',
    label: 'gestion.nav.portalPages',
    help: 'portal-pages',
    group: 'portal',
    capability: 'edition.read',
  },
  {
    key: 'portalFiles',
    path: 'portail/documents',
    label: 'gestion.nav.portalFiles',
    help: 'portal-files',
    group: 'portal',
    capability: 'edition.read',
  },
  {
    key: 'portalMenus',
    path: 'portail/menus',
    label: 'gestion.nav.portalMenus',
    help: 'portal-menus',
    group: 'portal',
    capability: 'edition.read',
  },
  {
    key: 'audit',
    path: 'audit',
    label: 'gestion.nav.audit',
    help: 'audit',
    group: 'control',
    capability: 'audit.read',
  },
  {
    key: 'guide',
    path: '/aide',
    label: 'gestion.nav.guide',
    help: 'first-steps',
    group: 'help',
    capability: null,
  },
];

/**
 * Écrans hors du rail qui ont pourtant une fiche (aide contextuelle seulement, adresse
 * exacte) : la sélection de l'édition.
 */
export const EXTRA_HELP_ROUTES: readonly { url: string; help: string }[] = [
  { url: '/editions', help: 'first-steps' },
];

/**
 * Catégories mises en avant par rôle actif (plan L1 §5.8) : **filtre de menu seulement**,
 * jamais un droit. Le serveur ignore le rôle actif ; les capacités de `/me` décident.
 * L'aide est toujours présente.
 */
export const ROLE_GROUPS: Partial<Record<Role, readonly NavGroupKey[]>> = {
  ADMIN: [
    'steering',
    'submissions',
    'reviewing',
    'program',
    'settings',
    'committees',
    'portal',
    'control',
  ],
  CHAIR: [
    'steering',
    'submissions',
    'reviewing',
    'program',
    'settings',
    'committees',
    'portal',
    'control',
  ],
  // Paramétrage pour les grilles d'évaluation (plan L4, H3) ; programme en lecture (L5, I1).
  SC_CHAIR: ['steering', 'submissions', 'reviewing', 'program', 'settings', 'committees'],
  OC_MEMBER: ['steering', 'submissions', 'program', 'settings', 'portal'],
  // Relecteur (plan L4, H1) : ses évaluations seulement.
  SC_MEMBER: ['reviewing'],
};

/** Rôles de gestion : ceux que le sélecteur « Rôle actif » propose. */
export const MANAGEMENT_ROLES = Object.keys(ROLE_GROUPS) as Role[];

export function screenUrl(screen: ScreenDef, editionId: string | number): string {
  return screen.path.startsWith('/') ? screen.path : `/editions/${editionId}/${screen.path}`;
}

/**
 * Rail de l'édition : écrans permis par les capacités, restreints aux catégories du rôle
 * actif s'il y en a un ; catégories vides omises ; `order` numéroté dans l'ordre affiché.
 */
export function buildNavigation(
  editionId: string | number,
  capabilities: readonly string[],
  activeRole: Role | null = null,
): NavGroup[] {
  const allowedGroups = activeRole ? ROLE_GROUPS[activeRole] : undefined;
  let order = 0;
  const groups: NavGroup[] = [];
  for (const key of GROUP_ORDER) {
    if (key !== 'help' && allowedGroups && !allowedGroups.includes(key)) {
      continue;
    }
    const entries = SCREENS.filter(
      (screen) =>
        screen.group === key &&
        (screen.capability === null || capabilities.includes(screen.capability)),
    ).map((screen): NavEntry => ({
      key: screen.key,
      url: screenUrl(screen, editionId),
      label: screen.label,
      keywords: `gestion.nav.keywords.${screen.key}`,
      help: screen.help,
      group: key,
      order: order++,
    }));
    if (entries.length) {
      groups.push({ key, label: `gestion.nav.groups.${key}`, entries });
    }
  }
  // Seule l'aide : aucun écran de l'édition n'est permis, le rail reste vide.
  return groups.some((group) => group.key !== 'help') ? groups : [];
}

/** Catalogue de la recherche, **dérivé** du rail : un écran retiré du rail est introuvable. */
export function catalogue(groups: readonly NavGroup[]): NavEntry[] {
  return groups.flatMap((group) => group.entries);
}

function pathOf(url: string): string {
  return url.split(/[?#]/)[0];
}

/** Entrée de l'URL courante : le **plus long préfixe** gagne (`/a` ne coiffe pas `/a/b`). */
export function entryForUrl<T extends { url: string }>(
  entries: readonly T[],
  url: string,
): T | null {
  const path = pathOf(url);
  return (
    entries
      .filter((entry) => path === entry.url || path.startsWith(`${entry.url}/`))
      .sort((a, b) => b.url.length - a.url.length)[0] ?? null
  );
}

/** Catégorie de l'écran courant, ou `null` si l'URL est hors de la table. */
export function activeGroup(groups: readonly NavGroup[], url: string): NavGroupKey | null {
  return entryForUrl(catalogue(groups), url)?.group ?? null;
}

/**
 * Fiche d'aide de l'URL courante, d'après la table complète (l'aide n'est pas un droit :
 * elle ne dépend ni des capacités ni du rôle actif). `null` : pas de bouton « ? ».
 */
export function helpForUrl(url: string): string | null {
  const path = pathOf(url);
  const match = /^\/editions\/([^/]+)(\/|$)/.exec(path);
  // Écrans absolus (le guide lui-même) exclus : sur `/aide`, un bouton « ? » serait redondant.
  const screens = (match ? SCREENS.filter((screen) => !screen.path.startsWith('/')) : []).map(
    (screen) => ({ url: screenUrl(screen, match![1]), help: screen.help }),
  );
  // Écrans hors du rail : adresse exacte seulement (`/editions` ne coiffe pas `/editions/3/x`).
  return (
    entryForUrl(screens, path)?.help ??
    EXTRA_HELP_ROUTES.find((route) => route.url === path)?.help ??
    null
  );
}
