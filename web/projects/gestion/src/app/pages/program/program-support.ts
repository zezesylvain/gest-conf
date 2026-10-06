import type {
  Equipment,
  ProgramBoard,
  ProgramConflict,
  Room,
  ScheduledSubmission,
  Session,
  SessionKind,
  SessionRoleKind,
  Slot,
} from '@gestconf/shared';

/**
 * Outils du programme dans la gestion (plan L5 §5), sans Angular : regroupements du
 * brouillon, heures dans le fuseau de l'édition (I12), conflits par session et par créneau.
 *
 * Les débuts et fins de session arrivent aussi à l'heure de l'édition, sans fuseau
 * (`starts_local`) : le jour et l'heure affichés en sont tirés tels quels, sans conversion
 * par le navigateur. Les créneaux n'ont que l'UTC : on les convertit dans le fuseau de
 * l'édition (`Intl`), jamais dans celui du navigateur.
 */

// Catalogues fermés du serveur, dans l'ordre d'affichage. Le type `Record` impose
// l'exhaustivité : une valeur ajoutée au schéma casse la compilation tant qu'elle manque ici.
const KINDS: Record<SessionKind, true> = {
  opening: true,
  keynote: true,
  parallel: true,
  poster: true,
  workshop: true,
  tutorial: true,
  round_table: true,
  assembly: true,
  break: true,
  meal: true,
  social: true,
  closing: true,
};
const EQUIPMENT: Record<Equipment, true> = {
  projector: true,
  microphone: true,
  sound_system: true,
  computer: true,
  whiteboard: true,
  interpretation: true,
  recording: true,
  wifi: true,
};
const ROLES: Record<SessionRoleKind, true> = {
  chair: true,
  discussant: true,
  moderator: true,
  panelist: true,
};
export const SESSION_KINDS = Object.keys(KINDS) as SessionKind[];
export const EQUIPMENT_KINDS = Object.keys(EQUIPMENT) as Equipment[];
export const SESSION_ROLE_KINDS = Object.keys(ROLES) as SessionRoleKind[];

/** Types de session sans communication : pas de cible « Placer dans… ». */
export const NON_SCIENTIFIC_KINDS: readonly SessionKind[] = ['break', 'meal', 'social'];

/** Jour d'une session à l'heure de l'édition (`2027-06-10`). */
export function sessionDay(session: Pick<Session, 'starts_local'>): string {
  return session.starts_local.slice(0, 10);
}

/** Heure à l'heure de l'édition (`09:30`) d'une valeur locale sans fuseau. */
export function localTime(value: string): string {
  return value.slice(11, 16);
}

/** Heure d'un instant UTC dans le fuseau de l'édition (`14:20`). */
export function timeInZone(iso: string, timeZone: string, locale: string): string {
  const value = new Date(iso);
  const options: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit', hour12: false };
  try {
    return new Intl.DateTimeFormat(locale, { ...options, timeZone }).format(value);
  } catch {
    return new Intl.DateTimeFormat(locale, { ...options, timeZone: 'UTC' }).format(value);
  }
}

/** Libellé d'un jour (`jeudi 10 juin 2027`), sans conversion de fuseau. */
export function dayLabel(day: string, locale: string): string {
  const value = new Date(`${day}T12:00:00Z`);
  if (Number.isNaN(value.getTime())) {
    return day;
  }
  return new Intl.DateTimeFormat(locale, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(value);
}

/** Titre d'une session dans la langue de l'interface (repli sur le français). */
export function sessionTitle(
  session: Pick<Session, 'title_fr' | 'title_en'>,
  lang: string,
): string {
  return (lang === 'en' && session.title_en) || session.title_fr;
}

/** Titre d'un créneau : la communication (référence et titre) ou l'élément libre. */
export function slotTitle(slot: Slot, lang: string): string {
  if (slot.submission) {
    return slot.submission.reference
      ? `${slot.submission.reference} — ${slot.submission.title}`
      : slot.submission.title;
  }
  return (lang === 'en' && slot.title_en) || slot.title_fr;
}

/** Sessions triées par début, puis par identifiant (ordre stable). */
export function sortSessions(sessions: readonly Session[]): Session[] {
  return [...sessions].sort(
    (a, b) =>
      a.starts_at.localeCompare(b.starts_at) || (a.room ?? 0) - (b.room ?? 0) || a.id - b.id,
  );
}

/** Jours du programme : ceux de l'édition, plus ceux des sessions hors de ses dates. */
export function programDays(board: Pick<ProgramBoard, 'days' | 'sessions'>): string[] {
  return [...new Set([...board.days, ...board.sessions.map(sessionDay)])].sort();
}

export interface GridColumn {
  /** `null` : événement hors salle (pause, repas, social). */
  room: Room | null;
  sessions: Session[];
}

/**
 * Grille d'un jour (I15) : une colonne par salle active, plus les salles inactives encore
 * utilisées ce jour-là, plus une colonne « hors salle » si besoin.
 */
export function dayGrid(
  board: Pick<ProgramBoard, 'rooms' | 'sessions'>,
  day: string,
): GridColumn[] {
  const sessions = sortSessions(board.sessions.filter((item) => sessionDay(item) === day));
  const used = new Set(sessions.map((item) => item.room));
  const rooms = [...board.rooms]
    .filter((room) => room.is_active !== false || used.has(room.id))
    .sort((a, b) => (a.position ?? 0) - (b.position ?? 0) || a.name.localeCompare(b.name));
  const columns: GridColumn[] = rooms.map((room) => ({
    room,
    sessions: sessions.filter((item) => item.room === room.id),
  }));
  const outside = sessions.filter((item) => item.room === null);
  if (outside.length) {
    columns.push({ room: null, sessions: outside });
  }
  return columns;
}

/** Conflits qui touchent une session (salle, personne, dépassement). */
export function sessionConflicts(
  conflicts: readonly ProgramConflict[],
  sessionId: number,
): ProgramConflict[] {
  return conflicts.filter((item) => item.sessions.includes(sessionId));
}

/** Conflits qui touchent un créneau (personne). */
export function slotConflicts(
  conflicts: readonly ProgramConflict[],
  slotId: number,
): ProgramConflict[] {
  return conflicts.filter((item) => item.slots.includes(slotId));
}

export interface ToScheduleFilters {
  track: string;
  type: string;
  query: string;
}

/** Liste « à programmer » filtrée (thématique, type, texte dans la référence ou le titre). */
export function filterToSchedule(
  items: readonly ScheduledSubmission[],
  filters: ToScheduleFilters,
): ScheduledSubmission[] {
  const query = filters.query.trim().toLocaleLowerCase();
  return items.filter(
    (item) =>
      (!filters.track || item.track === filters.track) &&
      (!filters.type || item.submission_type === filters.type) &&
      (!query ||
        item.title.toLocaleLowerCase().includes(query) ||
        (item.reference ?? '').toLocaleLowerCase().includes(query)),
  );
}

/** Durée totale d'une session en minutes (temps réel, I12). */
export function sessionMinutes(session: Pick<Session, 'starts_at' | 'ends_at'>): number {
  return Math.round((Date.parse(session.ends_at) - Date.parse(session.starts_at)) / 60000);
}

/** Minutes occupées par les créneaux et les tampons entre eux (RG-13). */
export function usedMinutes(session: Pick<Session, 'slots'>, buffer: number): number {
  const durations = session.slots.reduce((sum, slot) => sum + slot.duration_min, 0);
  return durations + Math.max(session.slots.length - 1, 0) * buffer;
}
