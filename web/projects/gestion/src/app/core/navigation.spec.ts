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
  it('président : cinq catégories, ordre du rail numéroté', () => {
    const groups = buildNavigation(3, CHAIR);
    expect(groups.map((group) => group.key)).toEqual([
      'steering',
      'settings',
      'committees',
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
      'members',
      'invitations',
      'guide',
    ]);
  });

  it('rôle actif : filtre de menu (catégories du rôle), aide toujours présente', () => {
    const groups = buildNavigation(3, CHAIR, 'SC_CHAIR');
    expect(groups.map((group) => group.key)).toEqual(['steering', 'committees', 'help']);
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
      items(CHAIR)
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
