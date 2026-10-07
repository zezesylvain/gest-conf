import type { Role } from '@gestconf/shared';

/**
 * Fiches du guide de la gestion (plan L2 §2.3, compétence `guide-utilisateur-integre-angular`).
 * Une fiche est une **donnée** rendue par un gabarit unique (page `/aide` et tiroir « ? ») ;
 * tous les textes sont des clés de traduction (FR/EN). Aucun import Angular.
 *
 * Une fiche est une promesse : quand une règle change, la corriger dans le même commit que
 * le code. Trame : vue d'ensemble → étapes → cas particuliers en encadrés (dire ce que le
 * logiciel refuse, et pourquoi). Écrire pour 460 px : pas de tableau large.
 */

export type CalloutTone = 'info' | 'tip' | 'warning' | 'danger';

export type HelpBlock =
  | { type: 'text'; text: string }
  | { type: 'list'; items: readonly string[] }
  | { type: 'steps'; steps: readonly { title: string; body: string }[] }
  | { type: 'callout'; tone: CalloutTone; title: string; text: string };

export interface HelpSheet {
  id: string;
  title: string;
  summary: string;
  /** Chemin d'accès en clair (« Paramétrage › Calendrier »). */
  path: string;
  /** Profils concernés : index par profil de la page `/aide`. */
  profiles: readonly Role[];
  blocks: readonly HelpBlock[];
}

/** Profils de l'index du guide, dans l'ordre d'affichage. */
export const HELP_PROFILES: readonly Role[] = [
  'ADMIN',
  'CHAIR',
  'SC_CHAIR',
  'OC_MEMBER',
  'SC_MEMBER',
  'VOLUNTEER',
  'SESSION_CHAIR',
  'SIGNATORY',
];

/** Fiches qui ne correspondent à aucun écran et ne sont pas orphelines pour autant. */
export const TRANSVERSAL: readonly string[] = [
  'first-steps',
  'security',
  'roles',
  'portal-publish',
];

// Fiches générales : profils de gestion (le relecteur n'a que l'espace d'évaluation).
const ALL: readonly Role[] = ['ADMIN', 'CHAIR', 'SC_CHAIR', 'OC_MEMBER'];
const SETTINGS_WRITERS: readonly Role[] = ['ADMIN', 'CHAIR'];
const MEMBER_MANAGERS: readonly Role[] = ['ADMIN', 'CHAIR', 'SC_CHAIR'];
const PORTAL_EDITORS: readonly Role[] = ['ADMIN', 'CHAIR', 'OC_MEMBER'];
const REVIEWERS: readonly Role[] = ['SC_MEMBER', 'SC_CHAIR'];
const REVIEW_MANAGERS: readonly Role[] = ['SC_CHAIR', 'CHAIR', 'ADMIN'];
// Programme (plan L5, I1) : lecture pour tous les profils de gestion ; écriture par
// l'administrateur et le CO « programme » ; publication par le Chair.
const PROGRAM_WRITERS: readonly Role[] = ['OC_MEMBER', 'ADMIN', 'CHAIR'];
// Inscriptions (plan L6, J1) : lecture pour l'administrateur, le Chair et le CO ; gestion
// par le CO « finances » ou « secrétariat » et l'administrateur ; finances : le Chair suit.
const REGISTRATION_READERS: readonly Role[] = ['OC_MEMBER', 'ADMIN', 'CHAIR'];
// Jour J (plan L7, K1) : le bénévole et le CO pointent ; le président de séance émarge ses
// sessions ; le CO selon sa fonction et l'administrateur suivent les présences et le comptoir.
const RECEPTION: readonly Role[] = ['VOLUNTEER', 'OC_MEMBER', 'ADMIN'];
const DAY_SESSIONS: readonly Role[] = ['SESSION_CHAIR', 'VOLUNTEER', 'OC_MEMBER', 'ADMIN'];
const DAY_MANAGERS: readonly Role[] = ['OC_MEMBER', 'ADMIN'];
// Attestations : CO « secrétariat », administrateur, Chair ; lettres : CO « secrétariat » et
// « relations extérieures », administrateur ; signature : le signataire seul (K18).
const DOCUMENT_MANAGERS: readonly Role[] = ['OC_MEMBER', 'ADMIN', 'CHAIR'];
const LETTER_MANAGERS: readonly Role[] = ['OC_MEMBER', 'ADMIN'];
const SIGNATORIES: readonly Role[] = ['SIGNATORY'];
// Organisation (plan L8, N2) : tâches et activité pour tout le CO, l'administrateur et le
// Chair ; budget pour le Chair, le CO « finances » et l'administrateur.
const ORGANISERS: readonly Role[] = ['OC_MEMBER', 'ADMIN', 'CHAIR'];
// Logistique (plan L8, N2) : lecture pour le Chair et le CO « logistique » ou
// « secrétariat », écriture par le CO « logistique » ; postes : CO « logistique » ou
// « bénévoles » et administrateur ; « Mon planning » : le bénévole.
const LOGISTICS: readonly Role[] = ['OC_MEMBER', 'ADMIN', 'CHAIR'];
const VOLUNTEER_PLANNERS: readonly Role[] = ['OC_MEMBER', 'ADMIN'];
const VOLUNTEERS: readonly Role[] = ['VOLUNTEER'];
// Partenaires (plan L8, N2) : lecture pour le Chair et le CO « relations extérieures »,
// « finances » ou « communication » ; écriture par les relations extérieures.
const PARTNERS: readonly Role[] = ['OC_MEMBER', 'ADMIN', 'CHAIR'];

/** Constructeur : les clés d'une fiche sont toutes sous `gestion.help.sheets.<id>`. */
function sheet(
  id: string,
  profiles: readonly Role[],
  blocks: (key: (name: string) => string) => HelpBlock[],
): HelpSheet {
  const key = (name: string) => `gestion.help.sheets.${id}.${name}`;
  return {
    id,
    title: key('title'),
    summary: key('summary'),
    path: key('path'),
    profiles,
    blocks: blocks(key),
  };
}

const text = (text: string): HelpBlock => ({ type: 'text', text });
const list = (...items: string[]): HelpBlock => ({ type: 'list', items });
const steps = (key: (name: string) => string, ...names: string[]): HelpBlock => ({
  type: 'steps',
  steps: names.map((name) => ({ title: key(`${name}Title`), body: key(`${name}Body`) })),
});
const callout = (tone: CalloutTone, key: (name: string) => string, name: string): HelpBlock => ({
  type: 'callout',
  tone,
  title: key(`${name}Title`),
  text: key(`${name}Text`),
});

export const HELP_SHEETS: readonly HelpSheet[] = [
  sheet('first-steps', [...ALL, 'VOLUNTEER', 'SESSION_CHAIR', 'SIGNATORY'], (k) => [
    text(k('intro')),
    steps(k, 'choose', 'rail', 'search', 'help'),
    callout('info', k, 'activeRole'),
    callout('tip', k, 'versioned'),
  ]),
  sheet('security', [...ALL, 'VOLUNTEER', 'SIGNATORY'], (k) => [
    text(k('intro')),
    steps(k, 'enable', 'stepUp'),
    callout('warning', k, 'reauth'),
    callout('danger', k, 'lost'),
  ]),
  sheet('roles', ALL, (k) => [
    text(k('intro')),
    list(
      k('admin'),
      k('chair'),
      k('scChair'),
      k('ocMember'),
      k('volunteer'),
      k('sessionChair'),
      k('signatory'),
    ),
    callout('info', k, 'grantors'),
    callout('warning', k, 'lastAdmin'),
  ]),
  sheet('dashboard', ALL, (k) => [
    text(k('intro')),
    steps(k, 'publish', 'archive'),
    callout('warning', k, 'noReturn'),
    callout('info', k, 'who'),
  ]),
  sheet('submissions', ALL, (k) => [
    text(k('intro')),
    steps(k, 'filter', 'detail', 'export', 'extension'),
    callout('info', k, 'drafts'),
    callout('info', k, 'duplicates'),
    callout('warning', k, 'closing'),
    callout('info', k, 'who'),
  ]),
  sheet('my-reviews', REVIEWERS, (k) => [
    text(k('intro')),
    steps(k, 'list', 'read', 'score', 'submit', 'discuss'),
    callout('info', k, 'anonymity'),
    callout('warning', k, 'decline'),
    callout('info', k, 'expertise'),
    callout('warning', k, 'frozen'),
  ]),
  sheet('review-follow-up', REVIEW_MANAGERS, (k) => [
    text(k('intro')),
    steps(k, 'assign', 'screen', 'follow', 'discuss', 'decide'),
    callout('warning', k, 'conflicts'),
    callout('info', k, 'load'),
    callout('info', k, 'reminders'),
    callout('info', k, 'divergence'),
  ]),
  sheet('ranking', REVIEW_MANAGERS, (k) => [
    text(k('intro')),
    steps(k, 'simulate', 'batch', 'publish', 'export'),
    callout('danger', k, 'noReturn'),
    callout('info', k, 'authors'),
    callout('info', k, 'waitlist'),
  ]),
  sheet('grids', ['ADMIN', 'CHAIR', 'SC_CHAIR'], (k) => [
    text(k('intro')),
    steps(k, 'create', 'criteria', 'duplicate'),
    callout('warning', k, 'sum'),
    callout('warning', k, 'locked'),
    callout('info', k, 'scope'),
  ]),
  sheet('settings-general', ALL, (k) => [
    text(k('intro')),
    list(k('languages')),
    callout('warning', k, 'timezone'),
    callout('warning', k, 'frozen'),
    callout('info', k, 'readOnly'),
  ]),
  sheet('settings-lists', ALL, (k) => [
    text(k('intro')),
    list(k('filePolicy')),
    steps(k, 'add', 'edit'),
    callout('warning', k, 'deactivate'),
    callout('info', k, 'publish'),
  ]),
  sheet('settings-calendar', ALL, (k) => [
    text(k('intro')),
    list(k('reserved'), k('free'), k('public')),
    callout('warning', k, 'order'),
    callout('info', k, 'publish'),
  ]),
  sheet('settings-confidentiality', SETTINGS_WRITERS, (k) => [
    text(k('intro')),
    list(k('reviewers'), k('load'), k('divergence'), k('confidence')),
    callout('warning', k, 'sensitive'),
    callout('warning', k, 'frozen'),
  ]),
  sheet('members', MEMBER_MANAGERS, (k) => [
    text(k('intro')),
    steps(k, 'revoke', 'history'),
    callout('info', k, 'add'),
    callout('warning', k, 'refusals'),
  ]),
  sheet('invitations', MEMBER_MANAGERS, (k) => [
    steps(k, 'invite', 'follow', 'resend'),
    callout('info', k, 'link'),
    callout('warning', k, 'sensitive'),
  ]),
  sheet('portal-sections', PORTAL_EDITORS, (k) => [
    text(k('intro')),
    list(k('content'), k('data')),
    steps(k, 'create', 'edit', 'preview'),
    callout('info', k, 'reuse'),
    callout('warning', k, 'delete'),
  ]),
  sheet('portal-pages', PORTAL_EDITORS, (k) => [
    text(k('intro')),
    list(k('site'), k('custom')),
    steps(k, 'compose', 'order', 'info'),
    callout('info', k, 'template'),
    callout('warning', k, 'refusals'),
  ]),
  sheet('portal-files', PORTAL_EDITORS, (k) => [
    text(k('intro')),
    list(k('documents'), k('images')),
    steps(k, 'upload', 'publish', 'poster'),
    callout('warning', k, 'refused'),
    callout('info', k, 'inUse'),
  ]),
  sheet('portal-menus', PORTAL_EDITORS, (k) => [
    text(k('intro')),
    steps(k, 'add', 'order'),
    callout('info', k, 'fallback'),
    callout('warning', k, 'links'),
  ]),
  sheet('portal-publish', PORTAL_EDITORS, (k) => [
    text(k('intro')),
    steps(k, 'edit', 'banner', 'deploy'),
    callout('warning', k, 'delay'),
    callout('info', k, 'committees'),
    callout('info', k, 'who'),
  ]),
  sheet('program-planner', ALL, (k) => [
    text(k('intro')),
    steps(k, 'pool', 'place', 'order', 'conflicts'),
    callout('info', k, 'keyboard'),
    callout('warning', k, 'draft'),
    callout('info', k, 'who'),
  ]),
  sheet('program-sessions', PROGRAM_WRITERS, (k) => [
    text(k('intro')),
    steps(k, 'create', 'times', 'roles', 'free'),
    callout('warning', k, 'timezone'),
    callout('info', k, 'invite'),
    callout('warning', k, 'delete'),
  ]),
  sheet('program-rooms', PROGRAM_WRITERS, (k) => [
    text(k('intro')),
    list(k('capacity'), k('equipment'), k('access')),
    callout('warning', k, 'inUse'),
  ]),
  sheet('program-publication', ALL, (k) => [
    text(k('intro')),
    steps(k, 'check', 'publish', 'portal'),
    callout('warning', k, 'conflicts'),
    callout('info', k, 'emails'),
    callout('info', k, 'who'),
  ]),
  sheet('settings-program', PROGRAM_WRITERS, (k) => [
    text(k('intro')),
    list(k('buffer'), k('registration')),
    callout('info', k, 'reflow'),
  ]),
  sheet('registrations', REGISTRATION_READERS, (k) => [
    text(k('intro')),
    steps(k, 'filter', 'detail', 'manual', 'cancel'),
    callout('info', k, 'statuses'),
    callout('warning', k, 'reauth'),
    callout('info', k, 'who'),
  ]),
  sheet('payments', REGISTRATION_READERS, (k) => [
    text(k('intro')),
    list(k('online'), k('manual'), k('statuses')),
    callout('warning', k, 'webhook'),
    callout('info', k, 'export'),
  ]),
  sheet('billing-documents', REGISTRATION_READERS, (k) => [
    text(k('intro')),
    list(k('invoice'), k('creditNote'), k('proforma')),
    callout('info', k, 'numbering'),
    callout('warning', k, 'frozen'),
  ]),
  sheet('finance-dashboard', REGISTRATION_READERS, (k) => [
    text(k('intro')),
    list(k('collected'), k('outstanding'), k('refundsDue')),
    callout('tip', k, 'pending'),
    callout('warning', k, 'orphans'),
  ]),
  sheet('settings-pricing', REGISTRATION_READERS, (k) => [
    text(k('intro')),
    steps(k, 'settings', 'categories', 'fees', 'options', 'promo'),
    callout('info', k, 'frozen'),
    callout('warning', k, 'inUse'),
    callout('info', k, 'online'),
  ]),
  sheet('settings-billing', REGISTRATION_READERS, (k) => [
    text(k('intro')),
    list(k('issuer'), k('vat'), k('bank'), k('prefixes')),
    callout('warning', k, 'incomplete'),
    callout('info', k, 'who'),
  ]),
  // Jour J (plan L7, K15).
  sheet('reception', RECEPTION, (k) => [
    text(k('intro')),
    steps(k, 'install', 'download', 'scan', 'offline', 'sync'),
    callout('warning', k, 'refusals'),
    callout('danger', k, 'logout'),
    callout('info', k, 'camera'),
  ]),
  sheet('day-sessions', DAY_SESSIONS, (k) => [
    text(k('intro')),
    list(k('scan'), k('presented'), k('attendance')),
    callout('info', k, 'chair'),
    callout('warning', k, 'correction'),
  ]),
  sheet('attendance', DAY_MANAGERS, (k) => [
    text(k('intro')),
    list(k('search'), k('cancel'), k('export')),
    callout('info', k, 'kept'),
  ]),
  sheet('badges', REGISTRATION_READERS, (k) => [
    text(k('intro')),
    steps(k, 'filter', 'download', 'print'),
    callout('warning', k, 'token'),
    callout('tip', k, 'lost'),
  ]),
  sheet('counter', DAY_MANAGERS, (k) => [
    text(k('intro')),
    steps(k, 'person', 'category', 'paid', 'badge'),
    callout('info', k, 'account'),
    callout('warning', k, 'existing'),
  ]),
  // Attestations, lettres et signature (plan L7, K9 à K12, K18, K19).
  sheet('certificates', DOCUMENT_MANAGERS, (k) => [
    text(k('intro')),
    list(k('participation'), k('presentation'), k('review')),
    steps(k, 'check', 'issue', 'follow'),
    callout('info', k, 'rg16'),
    callout('warning', k, 'revoke'),
  ]),
  sheet('certificate-settings', DOCUMENT_MANAGERS, (k) => [
    text(k('intro')),
    steps(k, 'mode', 'header', 'key', 'templates', 'signatory', 'preview'),
    callout('info', k, 'placeholders'),
    callout('warning', k, 'pades'),
    callout('info', k, 'qualified'),
  ]),
  sheet('letters', LETTER_MANAGERS, (k) => [
    text(k('intro')),
    steps(k, 'review', 'issue', 'refuse'),
    callout('warning', k, 'passport'),
    callout('info', k, 'disclaimer'),
  ]),
  sheet('signature', SIGNATORIES, (k) => [
    text(k('intro')),
    steps(k, 'identity', 'image'),
    callout('info', k, 'only'),
    callout('warning', k, 'frozen'),
  ]),
  // Organisation du CO (plan L8, N3, N4, N14).
  sheet('tasks', ORGANISERS, (k) => [
    text(k('intro')),
    steps(k, 'create', 'move', 'detail'),
    callout('info', k, 'keyboard'),
    callout('warning', k, 'stale'),
    callout('tip', k, 'reminder'),
  ]),
  sheet('budget', ORGANISERS, (k) => [
    text(k('intro')),
    list(k('planned'), k('actual'), k('computed'), k('proof')),
    callout('info', k, 'computedLines'),
    callout('warning', k, 'export'),
  ]),
  sheet('activity', ORGANISERS, (k) => [text(k('intro')), callout('info', k, 'whitelist')]),
  sheet('speakers', LOGISTICS, (k) => [
    text(k('intro')),
    steps(k, 'speaker', 'staff', 'equipment'),
    callout('info', k, 'local'),
    callout('warning', k, 'internal'),
  ]),
  sheet('catering', LOGISTICS, (k) => [
    text(k('intro')),
    list(k('audience'), k('margin'), k('diets'), k('order')),
    callout('info', k, 'estimate'),
    callout('warning', k, 'nominative'),
  ]),
  sheet('volunteer-shifts', VOLUNTEER_PLANNERS, (k) => [
    text(k('intro')),
    steps(k, 'create', 'assign', 'follow'),
    callout('warning', k, 'overlap'),
    callout('info', k, 'notify'),
  ]),
  sheet('my-shifts', VOLUNTEERS, (k) => [text(k('intro')), callout('tip', k, 'calendar')]),
  sheet('sponsors', PARTNERS, (k) => [
    text(k('intro')),
    steps(k, 'create', 'public', 'private', 'benefits'),
    callout('info', k, 'received'),
    callout('warning', k, 'logo'),
    callout('warning', k, 'export'),
  ]),
  sheet('sponsor-levels', PARTNERS, (k) => [
    text(k('intro')),
    list(k('names'), k('amount'), k('benefits'), k('size')),
    callout('info', k, 'copy'),
    callout('warning', k, 'delete'),
  ]),
  sheet('audit', SETTINGS_WRITERS, (k) => [
    text(k('intro')),
    list(k('action'), k('filters'), k('actor')),
    callout('info', k, 'immutable'),
  ]),
];

export const HELP_SHEETS_BY_ID: Readonly<Record<string, HelpSheet>> = Object.fromEntries(
  HELP_SHEETS.map((item) => [item.id, item]),
);

/** Toutes les clés de traduction d'une fiche (contrôle de cohérence). */
export function sheetKeys(item: HelpSheet): string[] {
  return [
    item.title,
    item.summary,
    item.path,
    ...item.blocks.flatMap((block) => {
      switch (block.type) {
        case 'text':
          return [block.text];
        case 'list':
          return [...block.items];
        case 'steps':
          return block.steps.flatMap((step) => [step.title, step.body]);
        case 'callout':
          return [block.title, block.text];
      }
    }),
  ];
}
