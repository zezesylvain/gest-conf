/**
 * Recherche d'écran (plan L2 §2.3, compétence `recherche-menu-topbar-angular`) : rapprochement
 * d'une saisie avec le catalogue dérivé du rail. Aucun import Angular.
 */

export interface SearchItem {
  /** Libellé traduit de l'écran. */
  title: string;
  /** Mots du métier traduits. */
  keywords: readonly string[];
  /** Libellé traduit de la catégorie. */
  group: string;
  /** Rang dans le rail : tri stable à pertinence égale. */
  order: number;
}

/**
 * Minuscules, sans accents (décomposition NFD), espaces réduits. Limite assumée : NFD ne
 * décompose pas les ligatures (« œ » reste « œ »).
 */
export function normalize(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()
    .replace(/\s+/g, ' ');
}

/**
 * Rang de pertinence (0 = meilleur), ou `null` si l'écran ne correspond pas :
 * 0 titre qui commence par la saisie, 1 titre qui la contient, 2 mot-clé qui commence par
 * elle, 3 mot-clé qui la contient, 4 catégorie qui la contient, 5 tous les mots de la saisie
 * présents, dans n'importe quel ordre.
 */
export function rank(item: SearchItem, query: string): number | null {
  const q = normalize(query);
  const title = normalize(item.title);
  const keywords = item.keywords.map(normalize);
  const group = normalize(item.group);
  if (title.startsWith(q)) return 0;
  if (title.includes(q)) return 1;
  if (keywords.some((keyword) => keyword.startsWith(q))) return 2;
  if (keywords.some((keyword) => keyword.includes(q))) return 3;
  if (group.includes(q)) return 4;
  const haystack = [title, ...keywords, group].join(' ');
  const words = q.split(' ');
  if (words.length > 1 && words.every((word) => haystack.includes(word))) return 5;
  return null;
}

/**
 * Écrans correspondant à la saisie, du plus pertinent au moins pertinent, l'ordre du rail
 * départageant les égalités. Saisie vide : tout le catalogue (le champ devient un menu) ;
 * une seule lettre : rien (elle remonterait la moitié du menu).
 */
export function search<T extends SearchItem>(items: readonly T[], query: string): T[] {
  const q = normalize(query);
  if (!q) {
    return [...items].sort((a, b) => a.order - b.order);
  }
  if (q.length < 2) {
    return [];
  }
  return items
    .map((item) => ({ item, rank: rank(item, q) }))
    .filter((result): result is { item: T; rank: number } => result.rank !== null)
    .sort((a, b) => a.rank - b.rank || a.item.order - b.item.order)
    .map((result) => result.item);
}
