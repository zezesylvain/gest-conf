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
  'registrations.read',
  'finance.read',
  'certificates.manage',
];
/**
 * Tous les écrans ouverts : président qui évalue aussi (H19), écrit le programme, et cumule
 * les capacités du jour J, des lettres et de la signature (plan L7).
 */
const EVERYTHING = [
  ...CHAIR,
  'reviews.write',
  'program.write',
  'checkin.scan',
  'checkin.manage',
  'registrations.manage',
  'letters.manage',
  'signature.manage',
  'tasks.read',
  'budget.read',
  'logistics.read',
  'volunteers.plan',
  'shifts.own',
  'sponsors.read',
  'communications.send',
  'surveys.manage',
];

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
  it('président : douze catégories, ordre du rail numéroté', () => {
    const groups = buildNavigation(3, CHAIR);
    expect(groups.map((group) => group.key)).toEqual([
      'steering',
      'submissions',
      'reviewing',
      'program',
      'registrations',
      'dayof',
      'documents',
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

  it('inscriptions (plan L6, J12) : liste avec registrations.read, finances avec finance.read', () => {
    // CO sans fonction : inscriptions et tarifs en lecture, ni paiements ni pièces ni finances.
    const oc = buildNavigation(
      3,
      ['edition.read', 'submissions.read', 'program.read', 'registrations.read'],
      'OC_MEMBER',
    );
    expect(oc.find((group) => group.key === 'registrations')!.entries.map((e) => e.key)).toEqual([
      'registrations',
    ]);
    const ocKeys = catalogue(oc).map((entry) => entry.key);
    expect(ocKeys).toContain('pricing');
    expect(ocKeys).not.toContain('billingProfile');
    // Chair : suivi des finances.
    const chair = buildNavigation(3, CHAIR);
    expect(chair.find((group) => group.key === 'registrations')!.entries.map((e) => e.key)).toEqual(
      ['registrations', 'payments', 'billingDocuments', 'finance'],
    );
    // Relecteur : rien.
    const reviewer = catalogue(buildNavigation(3, ['reviews.write'])).map((entry) => entry.key);
    expect(reviewer).not.toContain('registrations');
    // Le détail d'une inscription relève de la fiche de la liste ; les sous-écrans, de la leur.
    expect(helpForUrl('/editions/3/inscriptions/42')).toBe('registrations');
    expect(activeGroup(chair, '/editions/3/inscriptions/42')).toBe('registrations');
    expect(helpForUrl('/editions/3/inscriptions/paiements')).toBe('payments');
    expect(helpForUrl('/editions/3/inscriptions/factures')).toBe('billing-documents');
    expect(helpForUrl('/editions/3/inscriptions/finances')).toBe('finance-dashboard');
    expect(helpForUrl('/editions/3/parametrage/tarifs')).toBe('settings-pricing');
    expect(helpForUrl('/editions/3/parametrage/facturation')).toBe('settings-billing');
  });

  it('jour J (plan L7, K15) : chaque écran selon sa capacité, l’une d’elles pour les sessions', () => {
    // Bénévole : accueil et sessions du jour seulement.
    const volunteer = buildNavigation(3, ['checkin.scan']);
    expect(catalogue(volunteer).map((entry) => entry.key)).toEqual([
      'reception',
      'daySessions',
      'guide',
    ]);
    expect(catalogue(volunteer)[0].url).toBe('/editions/3/accueil');
    // Président de séance : ses sessions, sans l'accueil (capacité « l'une de »).
    const chair = buildNavigation(3, ['sessions.chair'], 'SESSION_CHAIR');
    expect(catalogue(chair).map((entry) => entry.key)).toEqual(['daySessions', 'guide']);
    // Signataire : sa signature seulement (K18).
    const signatory = buildNavigation(3, ['signature.manage'], 'SIGNATORY');
    expect(catalogue(signatory).map((entry) => entry.key)).toEqual(['signature', 'guide']);
    // CO « secrétariat » : tout le jour J, attestations et lettres ; pas la signature.
    const secretariat = buildNavigation(
      3,
      [
        'edition.read',
        'registrations.read',
        'registrations.manage',
        'checkin.scan',
        'checkin.manage',
        'certificates.manage',
        'letters.manage',
      ],
      'OC_MEMBER',
    );
    expect(secretariat.find((g) => g.key === 'dayof')!.entries.map((e) => e.key)).toEqual([
      'reception',
      'daySessions',
      'attendance',
      'badges',
      'counter',
    ]);
    expect(secretariat.find((g) => g.key === 'documents')!.entries.map((e) => e.key)).toEqual([
      'certificates',
      'certificateSettings',
      'letters',
    ]);
    // Président de la conférence : badges (lecture des inscriptions) et attestations.
    const president = buildNavigation(3, CHAIR);
    expect(president.find((g) => g.key === 'dayof')!.entries.map((e) => e.key)).toEqual(['badges']);
    // Le plus long préfixe : le modèle a sa fiche ; le détail d'une lettre, celle des lettres.
    expect(helpForUrl('/editions/3/attestations')).toBe('certificates');
    expect(helpForUrl('/editions/3/attestations/modele')).toBe('certificate-settings');
    expect(helpForUrl('/editions/3/lettres/12')).toBe('letters');
    expect(helpForUrl('/editions/3/jour-j/presences')).toBe('attendance');
  });

  it('organisation (plan L8, N16) : tâches et activité pour le CO, budget avec budget.read', () => {
    const team = buildNavigation(3, ['edition.read', 'tasks.read', 'tasks.write']);
    expect(team.find((group) => group.key === 'organisation')!.entries.map((e) => e.key)).toEqual([
      'tasks',
      'activity',
    ]);
    const finance = buildNavigation(3, ['edition.read', 'tasks.read', 'budget.read'], 'OC_MEMBER');
    expect(finance.map((group) => group.key)).toContain('organisation');
    expect(catalogue(finance).map((entry) => entry.url)).toContain(
      '/editions/3/organisation/budget',
    );
  });

  it('logistique (plan L8, N16) : intervenants et restauration en lecture, postes à part', () => {
    const reader = buildNavigation(3, ['edition.read', 'logistics.read'], 'CHAIR');
    expect(reader.find((group) => group.key === 'logistics')!.entries.map((e) => e.key)).toEqual([
      'speakers',
      'catering',
    ]);
    const planner = buildNavigation(3, ['edition.read', 'volunteers.plan'], 'OC_MEMBER');
    expect(planner.find((group) => group.key === 'logistics')!.entries.map((e) => e.key)).toEqual([
      'volunteerShifts',
    ]);
    // Le bénévole : « Mon planning » dans « Jour J », rien de la logistique.
    const volunteer = buildNavigation(3, ['checkin.scan', 'shifts.own'], 'VOLUNTEER');
    expect(volunteer.map((group) => group.key)).not.toContain('logistics');
    expect(volunteer.find((group) => group.key === 'dayof')!.entries.map((e) => e.key)).toContain(
      'myShifts',
    );
    expect(helpForUrl('/editions/3/logistique/intervenants/12')).toBe('speakers');
    expect(helpForUrl('/editions/3/jour-j/mon-planning')).toBe('my-shifts');
  });

  it('partenaires (plan L8, N16) : liste et niveaux avec sponsors.read', () => {
    const finance = buildNavigation(3, ['edition.read', 'sponsors.read'], 'OC_MEMBER');
    expect(finance.find((group) => group.key === 'partners')!.entries.map((e) => e.key)).toEqual([
      'sponsors',
      'sponsorLevels',
    ]);
    expect(buildNavigation(3, ['edition.read']).map((group) => group.key)).not.toContain(
      'partners',
    );
    // Le plus long préfixe : la fiche d'un partenaire relève de la liste, les niveaux de
    // leur propre fiche.
    expect(helpForUrl('/editions/3/partenaires/8')).toBe('sponsors');
    expect(helpForUrl('/editions/3/partenaires/niveaux')).toBe('sponsor-levels');
  });

  it('communication (plan L8, N16) : annonces et questionnaires selon la capacité', () => {
    const secretariat = buildNavigation(3, ['edition.read', 'surveys.manage'], 'OC_MEMBER');
    expect(
      secretariat.find((group) => group.key === 'communication')!.entries.map((e) => e.key),
    ).toEqual(['surveys']);
    const communication = buildNavigation(
      3,
      ['edition.read', 'communications.send', 'surveys.manage'],
      'OC_MEMBER',
    );
    expect(
      communication.find((group) => group.key === 'communication')!.entries.map((e) => e.key),
    ).toEqual(['announcements', 'surveys']);
    expect(helpForUrl('/editions/3/communication/annonces/4')).toBe('announcements');
    expect(helpForUrl('/editions/3/communication/questionnaires/6')).toBe('surveys');
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
