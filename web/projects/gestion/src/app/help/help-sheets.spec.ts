import en from '../../i18n/en.json';
import fr from '../../i18n/fr.json';
import { EXTRA_HELP_ROUTES, SCREENS } from '../core/navigation';
import { HELP_SHEETS, HELP_SHEETS_BY_ID, sheetKeys, TRANSVERSAL } from './help-sheets';

interface Tree {
  [key: string]: string | Tree;
}

function lookup(tree: Tree, key: string): unknown {
  return key.split('.').reduce<unknown>((node, part) => (node as Tree | undefined)?.[part], tree);
}

/** Contrôles de cohérence du guide (compétence guide-utilisateur-integre-angular). */
describe('Fiches d’aide de la gestion', () => {
  const ids = HELP_SHEETS.map((sheet) => sheet.id);
  const referenced = new Set([
    ...SCREENS.map((screen) => screen.help),
    ...EXTRA_HELP_ROUTES.map((route) => route.help),
  ]);

  it('identifiants uniques', () => {
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('chaque écran du rail pointe une fiche qui existe', () => {
    expect([...referenced].filter((id) => !HELP_SHEETS_BY_ID[id])).toEqual([]);
  });

  it('aucune fiche d’écran orpheline (hors fiches transversales)', () => {
    expect(ids.filter((id) => !referenced.has(id) && !TRANSVERSAL.includes(id))).toEqual([]);
  });

  it('les fiches transversales existent', () => {
    expect(TRANSVERSAL.filter((id) => !HELP_SHEETS_BY_ID[id])).toEqual([]);
  });

  it('chaque fiche nomme au moins un profil', () => {
    expect(HELP_SHEETS.filter((sheet) => !sheet.profiles.length).map((s) => s.id)).toEqual([]);
  });

  it('chaque clé de texte existe, non vide, en français et en anglais', () => {
    const missing = HELP_SHEETS.flatMap(sheetKeys).flatMap((key) =>
      [
        ['fr', fr],
        ['en', en],
      ]
        .filter(([, tree]) => {
          const value = lookup(tree as Tree, key);
          return typeof value !== 'string' || !value.trim();
        })
        .map(([lang]) => `${lang}:${key}`),
    );
    expect(missing).toEqual([]);
  });

  it('aucune clé de fiche inutilisée dans les traductions', () => {
    const used = new Set(HELP_SHEETS.flatMap(sheetKeys));
    const sheets = (fr as unknown as Tree)['gestion'] as Tree;
    const declared = Object.entries((sheets['help'] as Tree)['sheets'] as Tree).flatMap(
      ([id, node]) => Object.keys(node as Tree).map((name) => `gestion.help.sheets.${id}.${name}`),
    );
    expect(declared.filter((key) => !used.has(key))).toEqual([]);
  });

  it('chaque écran a ses mots-clés de recherche en français et en anglais', () => {
    const missing = SCREENS.map((screen) => `gestion.nav.keywords.${screen.key}`).filter(
      (key) =>
        typeof lookup(fr as Tree, key) !== 'string' || typeof lookup(en as Tree, key) !== 'string',
    );
    expect(missing).toEqual([]);
  });
});
