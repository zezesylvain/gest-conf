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
export const HELP_PROFILES: readonly Role[] = ['ADMIN', 'CHAIR', 'SC_CHAIR', 'OC_MEMBER'];

/** Fiches qui ne correspondent à aucun écran et ne sont pas orphelines pour autant. */
export const TRANSVERSAL: readonly string[] = [
  'first-steps',
  'security',
  'roles',
  'portal-publish',
];

const ALL = HELP_PROFILES;
const SETTINGS_WRITERS: readonly Role[] = ['ADMIN', 'CHAIR'];
const MEMBER_MANAGERS: readonly Role[] = ['ADMIN', 'CHAIR', 'SC_CHAIR'];
const PORTAL_EDITORS: readonly Role[] = ['ADMIN', 'CHAIR', 'OC_MEMBER'];

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
  sheet('first-steps', ALL, (k) => [
    text(k('intro')),
    steps(k, 'choose', 'rail', 'search', 'help'),
    callout('info', k, 'activeRole'),
    callout('tip', k, 'versioned'),
  ]),
  sheet('security', ALL, (k) => [
    text(k('intro')),
    steps(k, 'enable', 'stepUp'),
    callout('warning', k, 'reauth'),
    callout('danger', k, 'lost'),
  ]),
  sheet('roles', ALL, (k) => [
    text(k('intro')),
    list(k('admin'), k('chair'), k('scChair'), k('ocMember')),
    callout('info', k, 'grantors'),
    callout('warning', k, 'lastAdmin'),
  ]),
  sheet('dashboard', ALL, (k) => [
    text(k('intro')),
    steps(k, 'publish', 'archive'),
    callout('warning', k, 'noReturn'),
    callout('info', k, 'who'),
  ]),
  sheet('settings-general', ALL, (k) => [
    text(k('intro')),
    callout('warning', k, 'timezone'),
    callout('info', k, 'readOnly'),
  ]),
  sheet('settings-lists', ALL, (k) => [
    text(k('intro')),
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
    list(k('reviewers')),
    callout('warning', k, 'sensitive'),
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
    callout('info', k, 'who'),
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
