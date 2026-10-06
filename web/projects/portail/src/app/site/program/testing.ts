import type { PublicProgram, PublicProgramDay, PublicSession, PublicSite } from '@gestconf/shared';

/** Site minimal (édition à Abidjan, UTC toute l'année) pour les pages du programme. */
export const PROGRAM_SITE: PublicSite = {
  edition: {
    code: 'GC27',
    slug: '2027',
    year: 2027,
    title_fr: 'GEST-CONF 2027',
    title_en: 'GEST-CONF 2027 (EN)',
    theme_fr: 'Science ouverte',
    theme_en: '',
    start_date: '2027-06-01',
    end_date: '2027-06-02',
    venue: 'Palais',
    city: 'Abidjan',
    country: 'CI',
    timezone: 'Africa/Abidjan',
    submission_languages: ['fr', 'en'],
    tracks: [],
    submission_types: [],
    key_dates: [],
  },
  poster: null,
  documents: [],
  committees: {
    scientific: { members: [], others: 0 },
    organizing: { members: [], others: 0 },
  },
  site_url: 'https://conf.example',
};

export const IA_TRACK = { code: 'ia', name_fr: 'Intelligence artificielle', name_en: 'AI' };

/** Session publiée : deux communications (une présentatrice) et un président de séance. */
export const SESSION: PublicSession = {
  id: 10,
  kind: 'parallel',
  title_fr: 'Santé numérique',
  title_en: 'Digital health',
  description_fr: 'Données de santé et IA.',
  description_en: '',
  track: IA_TRACK,
  room: { name: 'Amphi A', is_accessible: true, access_note: 'Bâtiment B' },
  starts_at: '2027-06-01T09:00:00Z',
  ends_at: '2027-06-01T10:00:00Z',
  chairs: [{ role: 'chair', name: 'Koffi Yao', institution: 'INP-HB' }],
  slots: [
    {
      id: 1,
      starts_at: '2027-06-01T09:00:00Z',
      ends_at: '2027-06-01T09:20:00Z',
      duration_min: 20,
      reference: 'GC27-0001',
      title: 'Étude sur le paludisme',
      title_en: '',
      type: { code: 'oral', label_fr: 'Communication orale', label_en: 'Oral' },
      authors: [
        { name: 'Awa Zadi', institution: 'Univ. FHB', presenter: true },
        { name: 'Mariam Traoré', institution: '', presenter: false },
      ],
      speaker: null,
    },
    {
      id: 2,
      starts_at: '2027-06-01T09:20:00Z',
      ends_at: '2027-06-01T10:05:00Z',
      duration_min: 45,
      reference: null,
      title: 'Conférence invitée',
      title_en: 'Invited talk',
      type: null,
      authors: [],
      speaker: {
        name: 'Fatou Sow',
        institution: 'UCAD',
        bio: 'Épidémiologiste.',
        photo_url: '/api/v1/public/files/x/7',
      },
    },
  ],
};

export const BREAK: PublicSession = {
  ...SESSION,
  id: 20,
  kind: 'break',
  title_fr: 'Pause café',
  title_en: 'Coffee break',
  description_fr: '',
  track: null,
  room: null,
  chairs: [],
  slots: [],
  starts_at: '2027-06-01T10:00:00Z',
  ends_at: '2027-06-01T10:30:00Z',
};

export const DAY: PublicProgramDay = {
  date: '2027-06-01',
  timezone: 'Africa/Abidjan',
  sessions: [SESSION, BREAK],
};

export const PROGRAM: PublicProgram = {
  edition: 'GC27',
  version: 2,
  published_at: '2027-05-20T10:00:00Z',
  timezone: 'Africa/Abidjan',
  days: [
    {
      date: '2027-06-01',
      sessions: [
        {
          id: 10,
          kind: 'parallel',
          title_fr: 'Santé numérique',
          title_en: 'Digital health',
          track: IA_TRACK,
          room: 'Amphi A',
          starts_at: '2027-06-01T09:00:00Z',
          ends_at: '2027-06-01T10:00:00Z',
          slot_count: 2,
        },
        {
          id: 20,
          kind: 'break',
          title_fr: 'Pause café',
          title_en: 'Coffee break',
          track: null,
          room: null,
          starts_at: '2027-06-01T10:00:00Z',
          ends_at: '2027-06-01T10:30:00Z',
          slot_count: 0,
        },
      ],
    },
    {
      date: '2027-06-02',
      sessions: [
        {
          id: 30,
          kind: 'keynote',
          title_fr: 'Plénière',
          title_en: 'Keynote',
          track: null,
          room: 'Salle B',
          starts_at: '2027-06-02T09:00:00Z',
          ends_at: '2027-06-02T10:00:00Z',
          slot_count: 1,
        },
      ],
    },
  ],
};
