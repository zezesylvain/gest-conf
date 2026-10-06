import {
  dayGrid,
  dayLabel,
  filterToSchedule,
  programDays,
  sessionConflicts,
  sessionMinutes,
  slotConflicts,
  slotTitle,
  timeInZone,
  usedMinutes,
} from './program-support';
import { board, session, slot } from './testing';

describe('Outils du programme (plan L5)', () => {
  it('grille du jour : salles actives, inactives encore utilisées, colonne hors salle', () => {
    const data = board();
    const columns = dayGrid(data, '2027-06-01');
    expect(columns.map((column) => column.room?.name ?? null)).toEqual(['Amphi A', null]);
    expect(columns[0].sessions.map((item) => item.id)).toEqual([10, 30]);
    expect(columns[1].sessions.map((item) => item.id)).toEqual([20]);
    // Salle B inactive : réapparaît si une session l'utilise encore.
    const used = board({ sessions: [session(50, { room: 2 })] });
    expect(dayGrid(used, '2027-06-01').map((column) => column.room?.name)).toEqual([
      'Amphi A',
      'Salle B',
    ]);
  });

  it('jours : ceux de l’édition, plus ceux des sessions hors de ses dates', () => {
    const data = board({
      sessions: [
        session(60, { starts_local: '2027-05-31T18:00:00', ends_local: '2027-05-31T19:00:00' }),
      ],
    });
    expect(programDays(data)).toEqual(['2027-05-31', '2027-06-01', '2027-06-02']);
    expect(dayLabel('2027-06-01', 'fr')).toBe('mardi 1 juin 2027');
  });

  it('I12 : heure d’un créneau dans le fuseau de l’édition, pas celui du navigateur', () => {
    expect(timeInZone('2027-06-01T07:30:00Z', 'Europe/Paris', 'fr')).toBe('09:30');
    expect(timeInZone('2027-06-01T07:30:00Z', 'Africa/Abidjan', 'fr')).toBe('07:30');
  });

  it('liste « à programmer » filtrée par thématique, type et texte', () => {
    const items = board().to_schedule;
    const none = { track: '', type: '', query: '' };
    expect(filterToSchedule(items, none)).toHaveLength(2);
    expect(filterToSchedule(items, { ...none, track: 'reseaux' }).map((i) => i.id)).toEqual([2]);
    expect(filterToSchedule(items, { ...none, type: 'oral' }).map((i) => i.id)).toEqual([1]);
    expect(filterToSchedule(items, { ...none, query: 'gc27-0002' }).map((i) => i.id)).toEqual([2]);
  });

  it('RG-13 : minutes occupées (durées et tampons) et durée de la session', () => {
    const item = session(1, { slots: [slot(1, 0), slot(2, 1), slot(3, 2)] });
    expect(usedMinutes(item, 0)).toBe(60);
    expect(usedMinutes(item, 5)).toBe(70);
    expect(sessionMinutes(item)).toBe(90);
  });

  it('RG-12 : conflits rattachés aux sessions et aux créneaux concernés', () => {
    const { conflicts } = board();
    expect(sessionConflicts(conflicts, 30)).toHaveLength(1);
    expect(sessionConflicts(conflicts, 20)).toHaveLength(0);
    expect(slotConflicts(conflicts, 1)).toHaveLength(1);
    expect(slotConflicts(conflicts, 2)).toHaveLength(0);
  });

  it('titre d’un créneau : référence et titre, ou élément libre dans la langue', () => {
    expect(slotTitle(slot(1, 0), 'fr')).toBe('GC27-000101 — Étude 101');
    const free = slot(9, 0, { submission: null, title_fr: 'Discours', title_en: 'Speech' });
    expect(slotTitle(free, 'en')).toBe('Speech');
    expect(slotTitle({ ...free, title_en: '' }, 'en')).toBe('Discours');
  });
});
