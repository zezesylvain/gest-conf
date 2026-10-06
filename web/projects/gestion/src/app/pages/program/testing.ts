import type { ProgramBoard, ScheduledSubmission, Session, Slot } from '@gestconf/shared';

/** Communication confirmée ou placée, pour les tests du programme. */
export function paper(
  id: number,
  overrides: Partial<ScheduledSubmission> = {},
): ScheduledSubmission {
  return {
    id,
    reference: `GC27-000${id}`,
    title: `Étude ${id}`,
    status: 'confirmed',
    submission_type: 'oral',
    track: 'ia',
    default_duration_min: 20,
    presenters: [`Auteur ${id}`],
    confirmed: true,
    presenter_registered: null,
    ...overrides,
  };
}

export function slot(id: number, position: number, overrides: Partial<Slot> = {}): Slot {
  const start = 9 * 60 + position * 20;
  const at = (minutes: number) =>
    `2027-06-01T${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}:00Z`;
  return {
    id,
    position,
    duration_min: 20,
    starts_at: at(start),
    ends_at: at(start + 20),
    submission: paper(100 + id, { status: 'scheduled' }),
    title_fr: '',
    title_en: '',
    speaker: null,
    ...overrides,
  };
}

export function session(id: number, overrides: Partial<Session> = {}): Session {
  return {
    id,
    kind: 'parallel',
    title_fr: `Session ${id}`,
    title_en: `Session ${id} (EN)`,
    description_fr: '',
    description_en: '',
    instructions: '',
    track: null,
    room: 1,
    starts_at: '2027-06-01T09:00:00Z',
    ends_at: '2027-06-01T10:30:00Z',
    starts_local: '2027-06-01T09:00:00',
    ends_local: '2027-06-01T10:30:00',
    roles: [],
    slots: [],
    ...overrides,
  };
}

/**
 * Brouillon de test : deux salles (Amphi A, Salle B inactive), trois sessions le 1er juin
 * (deux dans l'Amphi A, une pause hors salle), une le 2 juin ; deux communications à
 * programmer ; un conflit de personne entre les sessions 10 et 30.
 */
export function board(overrides: Partial<ProgramBoard> = {}): ProgramBoard {
  return {
    revision: 7,
    published_revision: 5,
    published_version: 2,
    unpublished_changes: true,
    timezone: 'Africa/Abidjan',
    days: ['2027-06-01', '2027-06-02'],
    buffer_minutes: 0,
    rooms: [
      { id: 1, name: 'Amphi A', capacity: 120, equipment: ['projector'], position: 0 },
      { id: 2, name: 'Salle B', capacity: 30, equipment: [], position: 1, is_active: false },
    ],
    sessions: [
      session(10, {
        slots: [slot(1, 0), slot(2, 1)],
        roles: [
          {
            id: 5,
            role: 'chair',
            person: { id: 40, name: 'Awa Zadi', institution: 'INP-HB' },
          },
        ],
      }),
      session(20, {
        kind: 'break',
        title_fr: 'Pause café',
        room: null,
        starts_at: '2027-06-01T10:30:00Z',
        ends_at: '2027-06-01T11:00:00Z',
        starts_local: '2027-06-01T10:30:00',
        ends_local: '2027-06-01T11:00:00',
      }),
      session(30, {
        starts_at: '2027-06-01T11:00:00Z',
        ends_at: '2027-06-01T12:00:00Z',
        starts_local: '2027-06-01T11:00:00',
        ends_local: '2027-06-01T12:00:00',
      }),
      session(40, {
        starts_at: '2027-06-02T09:00:00Z',
        ends_at: '2027-06-02T10:00:00Z',
        starts_local: '2027-06-02T09:00:00',
        ends_local: '2027-06-02T10:00:00',
      }),
    ],
    to_schedule: [paper(1), paper(2, { track: 'reseaux', submission_type: 'poster' })],
    conflicts: [{ kind: 'person', sessions: [10, 30], slots: [1], person: 'Awa Zadi', minutes: 0 }],
    ...overrides,
  };
}
