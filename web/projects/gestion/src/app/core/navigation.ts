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
  | 'organisation'
  | 'submissions'
  | 'reviewing'
  | 'program'
  | 'registrations'
  | 'logistics'
  | 'partners'
  | 'communication'
  | 'reports'
  | 'dayof'
  | 'documents'
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
  /**
   * Capacité exigée dans l'édition ; une liste : **l'une** d'elles suffit (les sessions du
   * jour, pour qui pointe ou préside une séance, plan L7) ; `null` : écran ouvert à tout
   * rôle de gestion.
   */
  capability: Capability | readonly Capability[] | null;
}

/** L'écran est-il permis par ces capacités (l'une d'elles, pour une liste) ? */
export function screenAllowed(screen: ScreenDef, capabilities: readonly string[]): boolean {
  if (screen.capability === null) {
    return true;
  }
  const required: readonly string[] =
    typeof screen.capability === 'string' ? [screen.capability] : screen.capability;
  return required.some((capability) => capabilities.includes(capability));
}

export const GROUP_ORDER: readonly NavGroupKey[] = [
  'steering',
  'organisation',
  'submissions',
  'reviewing',
  'program',
  'registrations',
  'logistics',
  'partners',
  'communication',
  'reports',
  'dayof',
  'documents',
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
  // Organisation du CO (plan L8, N3, N4, N14) : tâches et activité pour tout le CO, budget
  // pour le Chair et le CO « finances ».
  {
    key: 'tasks',
    path: 'organisation/taches',
    label: 'gestion.nav.tasks',
    help: 'tasks',
    group: 'organisation',
    capability: 'tasks.read',
  },
  {
    key: 'budget',
    path: 'organisation/budget',
    label: 'gestion.nav.budget',
    help: 'budget',
    group: 'organisation',
    capability: 'budget.read',
  },
  {
    key: 'activity',
    path: 'organisation/activite',
    label: 'gestion.nav.activity',
    help: 'activity',
    group: 'organisation',
    capability: 'tasks.read',
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
  // Inscriptions (plan L6, J12) : lecture registrations.read ; finances finance.read.
  {
    key: 'registrations',
    path: 'inscriptions',
    label: 'gestion.nav.registrations',
    help: 'registrations',
    group: 'registrations',
    capability: 'registrations.read',
  },
  {
    key: 'payments',
    path: 'inscriptions/paiements',
    label: 'gestion.nav.payments',
    help: 'payments',
    group: 'registrations',
    capability: 'finance.read',
  },
  {
    key: 'billingDocuments',
    path: 'inscriptions/factures',
    label: 'gestion.nav.billingDocuments',
    help: 'billing-documents',
    group: 'registrations',
    capability: 'finance.read',
  },
  {
    key: 'finance',
    path: 'inscriptions/finances',
    label: 'gestion.nav.finance',
    help: 'finance-dashboard',
    group: 'registrations',
    capability: 'finance.read',
  },
  // Logistique (plan L8, N6 à N9) : intervenants invités et restauration (logistics.read),
  // postes des bénévoles (volunteers.plan).
  {
    key: 'speakers',
    path: 'logistique/intervenants',
    label: 'gestion.nav.speakers',
    help: 'speakers',
    group: 'logistics',
    capability: 'logistics.read',
  },
  {
    key: 'catering',
    path: 'logistique/restauration',
    label: 'gestion.nav.catering',
    help: 'catering',
    group: 'logistics',
    capability: 'logistics.read',
  },
  {
    key: 'volunteerShifts',
    path: 'logistique/benevoles',
    label: 'gestion.nav.volunteerShifts',
    help: 'volunteer-shifts',
    group: 'logistics',
    capability: 'volunteers.plan',
  },
  // Partenaires (plan L8, N5) : lecture sponsors.read, écriture revérifiée.
  {
    key: 'sponsors',
    path: 'partenaires',
    label: 'gestion.nav.sponsors',
    help: 'sponsors',
    group: 'partners',
    capability: 'sponsors.read',
  },
  {
    key: 'sponsorLevels',
    path: 'partenaires/niveaux',
    label: 'gestion.nav.sponsorLevels',
    help: 'sponsor-levels',
    group: 'partners',
    capability: 'sponsors.read',
  },
  // Communication (plan L8, N10 à N12) : annonces (communications.send), questionnaires
  // (surveys.manage).
  {
    key: 'announcements',
    path: 'communication/annonces',
    label: 'gestion.nav.announcements',
    help: 'announcements',
    group: 'communication',
    capability: 'communications.send',
  },
  {
    key: 'surveys',
    path: 'communication/questionnaires',
    label: 'gestion.nav.surveys',
    help: 'surveys',
    group: 'communication',
    capability: 'surveys.manage',
  },
  // Rapports (plan L8, N13) : sections filtrées par le serveur selon les capacités.
  {
    key: 'reports',
    path: 'rapports',
    label: 'gestion.nav.reports',
    help: 'reports',
    group: 'reports',
    capability: 'edition.read',
  },
  // Jour J (plan L7, K15) : accueil (PWA), sessions du jour, présences, badges, comptoir.
  {
    key: 'reception',
    path: 'accueil',
    label: 'gestion.nav.reception',
    help: 'reception',
    group: 'dayof',
    capability: 'checkin.scan',
  },
  {
    key: 'daySessions',
    path: 'jour-j/sessions',
    label: 'gestion.nav.daySessions',
    help: 'day-sessions',
    group: 'dayof',
    capability: ['checkin.scan', 'sessions.chair'],
  },
  {
    key: 'attendance',
    path: 'jour-j/presences',
    label: 'gestion.nav.attendance',
    help: 'attendance',
    group: 'dayof',
    capability: 'checkin.manage',
  },
  {
    key: 'badges',
    path: 'jour-j/badges',
    label: 'gestion.nav.badges',
    help: 'badges',
    group: 'dayof',
    capability: 'registrations.read',
  },
  {
    key: 'counter',
    path: 'jour-j/comptoir',
    label: 'gestion.nav.counter',
    help: 'counter',
    group: 'dayof',
    capability: 'registrations.manage',
  },
  // « Mon planning » du bénévole (plan L8, N9).
  {
    key: 'myShifts',
    path: 'jour-j/mon-planning',
    label: 'gestion.nav.myShifts',
    help: 'my-shifts',
    group: 'dayof',
    capability: 'shifts.own',
  },
  // Attestations et lettres (plan L7, K9 à K12, K18, K19).
  {
    key: 'certificates',
    path: 'attestations',
    label: 'gestion.nav.certificates',
    help: 'certificates',
    group: 'documents',
    capability: 'certificates.manage',
  },
  {
    key: 'certificateSettings',
    path: 'attestations/modele',
    label: 'gestion.nav.certificateSettings',
    help: 'certificate-settings',
    group: 'documents',
    capability: 'certificates.manage',
  },
  {
    key: 'letters',
    path: 'lettres',
    label: 'gestion.nav.letters',
    help: 'letters',
    group: 'documents',
    capability: 'letters.manage',
  },
  {
    key: 'signature',
    path: 'signature',
    label: 'gestion.nav.signature',
    help: 'signature',
    group: 'documents',
    capability: 'signature.manage',
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
    key: 'pricing',
    path: 'parametrage/tarifs',
    label: 'gestion.nav.pricing',
    help: 'settings-pricing',
    group: 'settings',
    capability: 'registrations.read',
  },
  {
    key: 'billingProfile',
    path: 'parametrage/facturation',
    label: 'gestion.nav.billingProfile',
    help: 'settings-billing',
    group: 'settings',
    capability: 'finance.read',
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
    'organisation',
    'submissions',
    'reviewing',
    'program',
    'registrations',
    'logistics',
    'partners',
    'communication',
    'reports',
    'dayof',
    'documents',
    'settings',
    'committees',
    'portal',
    'control',
  ],
  CHAIR: [
    'steering',
    'organisation',
    'submissions',
    'reviewing',
    'program',
    'registrations',
    'logistics',
    'partners',
    'communication',
    'reports',
    'dayof',
    'documents',
    'settings',
    'committees',
    'portal',
    'control',
  ],
  // Paramétrage pour les grilles d'évaluation (plan L4, H3) ; programme en lecture (L5, I1).
  // Rapports (plan L8, N13) : soumissions et relecture, sections de ses capacités.
  SC_CHAIR: [
    'steering',
    'submissions',
    'reviewing',
    'program',
    'reports',
    'settings',
    'committees',
  ],
  // Comités : le CO « bénévoles » recrute les bénévoles (plan L7, K1).
  OC_MEMBER: [
    'steering',
    'organisation',
    'submissions',
    'program',
    'registrations',
    'logistics',
    'partners',
    'communication',
    'reports',
    'dayof',
    'documents',
    'settings',
    'committees',
    'portal',
  ],
  // Relecteur (plan L4, H1) : ses évaluations seulement.
  SC_MEMBER: ['reviewing'],
  // Plan L7 : le bénévole pointe, le président de séance émarge ses sessions (K1, K7), le
  // signataire renseigne sa signature (K18).
  VOLUNTEER: ['dayof'],
  SESSION_CHAIR: ['dayof'],
  SIGNATORY: ['documents'],
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
      (screen) => screen.group === key && screenAllowed(screen, capabilities),
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
