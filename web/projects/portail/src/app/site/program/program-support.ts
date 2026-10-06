import type {
  PublicProgramDaySummary,
  PublicProgramSessionSummary,
  PublicSession,
  SessionKind,
} from '@gestconf/shared';

import { SITE_PAGES_BY_SLUG, SiteLanguage } from '../site-pages';

/**
 * Programme public (plan L5, I7) : adresses, heures et filtres, sans Angular. Les heures
 * s'affichent dans le fuseau de l'édition, indiqué sur la page, jamais dans celui du
 * navigateur : le programme est pré-rendu, le même pour tous.
 */

/** Segment de la page « Programme » dans une langue (`programme`, `program`). */
export function programSegment(language: SiteLanguage): string {
  return SITE_PAGES_BY_SLUG['program']?.[language] || 'programme';
}

export function programPath(language: SiteLanguage): string {
  return `/${language}/${programSegment(language)}/`;
}

export function dayPath(day: string, language: SiteLanguage): string {
  return `${programPath(language)}${day}/`;
}

export function sessionPath(id: number, language: SiteLanguage): string {
  return `${programPath(language)}session/${id}/`;
}

/** Heure (`09:30`) d'un instant dans le fuseau de l'édition. */
export function timeIn(iso: string, timeZone: string, language: SiteLanguage): string {
  return new Intl.DateTimeFormat(language, {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone,
  }).format(new Date(iso));
}

/** Libellé d'un jour (`mardi 1 juin 2027`), sans conversion de fuseau. */
export function dayLabel(day: string, language: SiteLanguage): string {
  const value = new Date(`${day}T12:00:00Z`);
  if (Number.isNaN(value.getTime())) {
    return day;
  }
  return new Intl.DateTimeFormat(language, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(value);
}

/** Valeur bilingue : l'anglais vide se replie sur le français. */
export function inLanguage(fr: string, en: string | undefined, language: SiteLanguage): string {
  return (language === 'en' && en) || fr;
}

export interface ProgramFilters {
  day: string;
  room: string;
  track: string;
  kind: string;
  query: string;
}

export const NO_FILTERS: ProgramFilters = { day: '', room: '', track: '', kind: '', query: '' };

/** Texte normalisé pour la recherche (casse et accents ignorés). */
export function normalize(text: string): string {
  return text
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLocaleLowerCase();
}

function summaryMatches(
  session: PublicProgramSessionSummary,
  filters: ProgramFilters,
  query: string,
): boolean {
  return (
    (!filters.room || session.room === filters.room) &&
    (!filters.track || session.track?.code === filters.track) &&
    (!filters.kind || session.kind === filters.kind) &&
    (!query ||
      normalize(`${session.title_fr} ${session.title_en} ${session.room ?? ''}`).includes(query))
  );
}

/** Accueil du programme filtré : jours non vides seulement. */
export function filterDays(
  days: readonly PublicProgramDaySummary[],
  filters: ProgramFilters,
): PublicProgramDaySummary[] {
  const query = normalize(filters.query.trim());
  return days
    .filter((day) => !filters.day || day.date === filters.day)
    .map((day) => ({
      ...day,
      sessions: day.sessions.filter((session) => summaryMatches(session, filters, query)),
    }))
    .filter((day) => day.sessions.length);
}

/** Sessions d'un jour filtrées ; la recherche porte aussi sur les communications. */
export function filterSessions(
  sessions: readonly PublicSession[],
  filters: ProgramFilters,
): PublicSession[] {
  const query = normalize(filters.query.trim());
  return sessions.filter((session) => {
    const text = [
      session.title_fr,
      session.title_en,
      ...session.chairs.map((chair) => chair.name),
      ...session.slots.flatMap((slot) => [
        slot.title,
        slot.title_en,
        slot.reference ?? '',
        slot.speaker?.name ?? '',
        ...slot.authors.map((author) => author.name),
      ]),
    ].join(' ');
    return (
      (!filters.room || session.room?.name === filters.room) &&
      (!filters.track || session.track?.code === filters.track) &&
      (!filters.kind || session.kind === filters.kind) &&
      (!query || normalize(text).includes(query))
    );
  });
}

/** Valeurs distinctes, triées, d'une liste (salles, thématiques, types). */
export function distinct<T>(items: readonly T[], key: (item: T) => string | null): string[] {
  return [...new Set(items.map(key).filter((value): value is string => !!value))].sort((a, b) =>
    a.localeCompare(b),
  );
}

/** Colonnes de la grille d'un jour : une par salle (ordre alphabétique), puis hors salle. */
export function roomColumns(
  sessions: readonly PublicSession[],
): { room: string | null; sessions: PublicSession[] }[] {
  const rooms = distinct(sessions, (session) => session.room?.name ?? null);
  const columns: { room: string | null; sessions: PublicSession[] }[] = rooms.map((room) => ({
    room,
    sessions: sessions.filter((session) => session.room?.name === room),
  }));
  const outside = sessions.filter((session) => !session.room);
  if (outside.length) {
    columns.push({ room: null, sessions: outside });
  }
  return columns;
}

/** Types de session présents, dans l'ordre du catalogue. */
export function kindsOf(kinds: readonly SessionKind[]): SessionKind[] {
  const order: SessionKind[] = [
    'opening',
    'keynote',
    'parallel',
    'poster',
    'workshop',
    'tutorial',
    'round_table',
    'assembly',
    'break',
    'meal',
    'social',
    'closing',
  ];
  return order.filter((kind) => kinds.includes(kind));
}
