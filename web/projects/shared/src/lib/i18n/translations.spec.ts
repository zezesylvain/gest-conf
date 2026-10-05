import { ERROR_CODE } from '../api/models/error-code-array';
import en from './en.json';
import fr from './fr.json';

interface Tree {
  [key: string]: string | Tree;
}

/** Toutes les clés « a.b.c » d'un arbre de traductions. */
export function translationKeys(tree: Tree, prefix = ''): string[] {
  return Object.entries(tree).flatMap(([key, value]) =>
    typeof value === 'string' ? [`${prefix}${key}`] : translationKeys(value, `${prefix}${key}.`),
  );
}

describe('Traductions communes (shared.*)', () => {
  it('FR et EN ont exactement les mêmes clés (parité, plan L1 §10.5)', () => {
    expect(translationKeys(en as Tree).sort()).toEqual(translationKeys(fr as Tree).sort());
  });

  it('chaque code ErrorCode de l’API a une traduction', () => {
    const keys = new Set(translationKeys(fr as Tree));
    const missing = ERROR_CODE.filter((code) => !keys.has(`shared.errors.${code}`));
    expect(missing).toEqual([]);
  });
});
