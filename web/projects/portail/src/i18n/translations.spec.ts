import en from './en.json';
import fr from './fr.json';

interface Tree {
  [key: string]: string | Tree;
}

function keys(tree: Tree, prefix = ''): string[] {
  return Object.entries(tree).flatMap(([key, value]) =>
    typeof value === 'string' ? [`${prefix}${key}`] : keys(value, `${prefix}${key}.`),
  );
}

describe('Traductions du portail', () => {
  it('FR et EN ont exactement les mêmes clés (parité, plan L1 §10.5)', () => {
    expect(keys(en as Tree).sort()).toEqual(keys(fr as Tree).sort());
  });
});
