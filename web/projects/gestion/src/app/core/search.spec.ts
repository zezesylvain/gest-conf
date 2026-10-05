import { normalize, rank, search, SearchItem } from './search';

const ITEMS: SearchItem[] = [
  { title: 'Tableau de bord', keywords: ['publier', 'statut'], group: 'Pilotage', order: 0 },
  { title: 'Thématiques', keywords: ['axes', 'sujets'], group: 'Paramétrage', order: 1 },
  {
    title: 'Calendrier',
    keywords: ['dates clés', 'échéances'],
    group: 'Paramétrage',
    order: 2,
  },
  {
    title: 'Confidentialité',
    keywords: ['double aveugle', 'relecteurs'],
    group: 'Paramétrage',
    order: 3,
  },
  { title: 'Membres', keywords: ['rôles', 'comité'], group: 'Comités', order: 4 },
  { title: 'Invitations', keywords: ['inviter', 'comité'], group: 'Comités', order: 5 },
];

const titles = (query: string) => search(ITEMS, query).map((item) => item.title);

describe('Recherche d’écran (compétence recherche-menu-topbar-angular)', () => {
  it('normalisation NFD : sans accents, minuscules, espaces réduits', () => {
    expect(normalize('  Échéances   CLÉS ')).toBe('echeances cles');
  });

  it('limite connue : NFD ne décompose pas les ligatures', () => {
    expect(normalize('Œuvre')).toBe('œuvre');
  });

  it('un terme sans accent trouve le libellé accentué', () => {
    expect(titles('thematiques')).toEqual(['Thématiques']);
    expect(titles('echeance')).toEqual(['Calendrier']);
  });

  it('un mot du métier trouve un écran dont le titre ne le contient pas', () => {
    expect(titles('relecteur')).toEqual(['Confidentialité']);
  });

  it('rangs : titre (début, contenu), mot-clé (début, contenu), catégorie, tous les mots', () => {
    const [board, , calendar, , members] = ITEMS;
    expect(rank(board, 'tab')).toBe(0);
    expect(rank(board, 'bord')).toBe(1);
    expect(rank(board, 'pub')).toBe(2);
    expect(rank(calendar, 'cles')).toBe(3);
    expect(rank(calendar, 'parametrage')).toBe(4);
    expect(rank(members, 'comite roles')).toBe(5);
    expect(rank(members, 'roles comite')).toBe(5);
    expect(rank(members, 'facture')).toBeNull();
  });

  it('tri par rang, puis ordre du rail à rang égal (tri stable)', () => {
    // « co » : Confidentialité (titre, rang 0), Membres puis Invitations (mot-clé « comité »).
    expect(titles('co')).toEqual(['Confidentialité', 'Membres', 'Invitations']);
  });

  it('saisie vide : tout le catalogue, dans l’ordre du rail', () => {
    expect(titles('  ')).toEqual(ITEMS.map((item) => item.title));
  });

  it('une seule lettre : rien', () => {
    expect(titles('c')).toEqual([]);
  });
});
