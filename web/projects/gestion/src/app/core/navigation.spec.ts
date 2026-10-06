import {
  activeGroup,
  buildNavigation,
  catalogue,
  entryForUrl,
  helpForUrl,
  SCREENS,
} from './navigation';
import { search } from './search';

const CHAIR = [
  'edition.read',
  'edition.write',
  'edition.publish',
  'members.read',
  'members.manage',
  'audit.read',
  'submissions.read',
  'submissions.extend',
  'submissions.export',
  'reviews.manage',
  'reviews.read_all',
  'decisions.decide',
  'decisions.publish',
  'grids.write',
  'program.read',
  'program.publish',
];
/** Président qui évalue aussi (H19) et écrit le programme : tous les écrans lui sont ouverts. */
const EVERYTHING = [...CHAIR, 'reviews.write', 'program.write'];

/** Catalogue « traduit » minimal : la clé tient lieu de libellé. */
function items(capabilities: string[], role: Parameters<typeof buildNavigation>[2] = null) {
  return catalogue(buildNavigation(3, capabilities, role)).map((entry) => ({
    ...entry,
    title: entry.key,
    keywords: [] as string[],
    group: entry.group,
  }));
}

describe('Table de navigation de la gestion (plan L2 §2.3)', () => {
  it('président : neuf catégories, ordre du rail numéroté', () => {
    const groups = buildNavigation(3, CHAIR);
    expect(groups.map((group) => group.key)).toEqual([
      'steering',
      'submissions',
      'reviewing',
      'program',
      'settings',
      'committees',
      'portal',
      'control',
      'help',
    ]);
    const entries = catalogue(groups);
    expect(entries.map((entry) => entry.order)).toEqual(entries.map((_, index) => index));
    expect(entries[0].url).toBe('/editions/3/tableau-de-bord');
    expect(entries.at(-1)!.url).toBe('/aide');
  });

  it('président du CS : paramétrage en lecture, comités, ni journal ni contrôle', () => {
    const groups = buildNavigation(3, ['edition.read', 'members.read', 'members.manage']);
    expect(catalogue(groups).map((entry) => entry.key)).toEqual([
      'dashboard',
      'general',
      'tracks',
      'types',
      'calendar',
      'confidentiality',
      // Grilles d'évaluation : lecture avec edition.read (écriture : grids.write).
      'grids',
      'members',
      'invitations',
      // Lecture du portail (edition.read) ; écriture réservée à portal.write.
      'portalSections',
      'portalPages',
      'portalFiles',
      'portalMenus',
      'guide',
    ]);
  });

  it('soumissions (plan L3) : catégorie dédiée, après le pilotage, avec submissions.read', () => {
    const groups = buildNavigation(3, CHAIR);
    expect(catalogue(groups)[1].url).toBe('/editions/3/soumissions');
    // Sans submissions.read (relecteur avant L4) : pas de catégorie.
    const reader = buildNavigation(3, ['edition.read']);
    expect(reader.map((group) => group.key)).not.toContain('submissions');
    // CO : lecture des soumissions, catégorie présente avec le rôle actif.
    const oc = buildNavigation(3, ['edition.read', 'submissions.read'], 'OC_MEMBER');
    expect(oc.map((group) => group.key)).toContain('submissions');
    // Le détail d'une soumission relève de la même fiche et de la même catégorie.
    expect(helpForUrl('/editions/3/soumissions/42')).toBe('submissions');
    expect(activeGroup(groups, '/editions/3/soumissions/42')).toBe('submissions');
  });

  it('rôle actif : filtre de menu (catégories du rôle), aide toujours présente', () => {
    const groups = buildNavigation(3, CHAIR, 'SC_CHAIR');
    expect(groups.map((group) => group.key)).toEqual([
      'steering',
      'submissions',
      'reviewing',
      'program',
      'settings',
      'committees',
      'help',
    ]);
  });

  it('évaluation (plan L4) : le relecteur ne voit que ses évaluations ; le président pilote', () => {
    const reviewer = buildNavigation(3, ['reviews.write']);
    expect(catalogue(reviewer).map((entry) => entry.key)).toEqual([
      'myReviews',
      'expertise',
      'guide',
    ]);
    expect(catalogue(reviewer)[0].url).toBe('/editions/3/evaluations');
    const chair = catalogue(buildNavigation(3, CHAIR)).map((entry) => entry.key);
    expect(chair).toContain('followUp');
    expect(chair).toContain('ranking');
    expect(chair).not.toContain('myReviews');
    expect(helpForUrl('/editions/3/evaluations/12')).toBe('my-reviews');
    expect(helpForUrl('/editions/3/pilotage/7')).toBe('review-follow-up');
    expect(helpForUrl('/editions/3/parametrage/grilles')).toBe('grids');
  });

  it('programme (plan L5) : catégorie dédiée avec program.read, réglage dans le paramétrage', () => {
    const oc = buildNavigation(
      3,
      ['edition.read', 'submissions.read', 'program.read', 'program.write'],
      'OC_MEMBER',
    );
    const keys = catalogue(oc).map((entry) => entry.key);
    expect(keys).toContain('programPlanner');
    expect(keys).toContain('programSettings');
    expect(oc.find((group) => group.key === 'program')!.entries.map((e) => e.key)).toEqual([
      'programPlanner',
      'programSessions',
      'programRooms',
      'programPublication',
    ]);
    // Sans program.read (relecteur) : ni catégorie ni réglage.
    const reviewer = catalogue(buildNavigation(3, ['reviews.write'])).map((entry) => entry.key);
    expect(reviewer).not.toContain('programPlanner');
    expect(reviewer).not.toContain('programSettings');
    // Le plus long préfixe désigne l'écran : la fiche des sessions, pas celle du planificateur.
    expect(helpForUrl('/editions/3/programme')).toBe('program-planner');
    expect(helpForUrl('/editions/3/programme/sessions')).toBe('program-sessions');
    expect(helpForUrl('/editions/3/parametrage/programme')).toBe('settings-program');
  });

  it('aucune capacité dans l’édition : rail vide (pas d’aide seule)', () => {
    expect(buildNavigation(3, [])).toEqual([]);
  });

  it('le catalogue est dérivé du rail : un écran hors périmètre est introuvable', () => {
    const restricted = items(['edition.read']);
    expect(search(restricted, 'audit')).toEqual([]);
    expect(search(items(CHAIR), 'audit').map((item) => item.key)).toEqual(['audit']);
  });

  it('une entrée ajoutée au rail est cherchable sans rien déclarer d’autre', () => {
    const keys = SCREENS.map((screen) => screen.key);
    expect(
      items(EVERYTHING)
        .map((item) => item.key)
        .sort(),
    ).toEqual([...keys].sort());
  });

  it('catégorie active : le plus long préfixe gagne', () => {
    const groups = buildNavigation(3, CHAIR);
    expect(activeGroup(groups, '/editions/3/parametrage/calendrier?x=1')).toBe('settings');
    expect(activeGroup(groups, '/editions/3/comites/invitations')).toBe('committees');
    expect(activeGroup(groups, '/aide')).toBe('help');
    expect(
      entryForUrl(
        [
          { url: '/a', id: 1 },
          { url: '/a/b', id: 2 },
        ],
        '/a/b/c',
      )?.id,
    ).toBe(2);
  });

  it('URL hors table : aucune catégorie désignée (le rail se replie ailleurs)', () => {
    expect(activeGroup(buildNavigation(3, CHAIR), '/editions/3/inconnu')).toBeNull();
    expect(entryForUrl([{ url: '/editions/3/audit' }], '/editions/3/auditx')).toBeNull();
  });

  it('fiche d’aide déduite de l’URL, indépendante des droits', () => {
    expect(helpForUrl('/editions/7/parametrage/types')).toBe('settings-lists');
    expect(helpForUrl('/editions/7/audit?page=2')).toBe('audit');
    expect(helpForUrl('/editions')).toBe('first-steps');
    expect(helpForUrl('/aide')).toBeNull();
    expect(helpForUrl('/acces-refuse')).toBeNull();
    expect(helpForUrl('/editions/7/inconnu')).toBeNull();
  });
});
