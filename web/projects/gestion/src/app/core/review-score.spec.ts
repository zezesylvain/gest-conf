import { weightedScore } from './review-score';

const GRID = [
  { code: 'originalite', weight: '25' },
  { code: 'methode', weight: '30' },
  { code: 'pertinence', weight: '15' },
  { code: 'redaction', weight: '15' },
  { code: 'impact', weight: '15', is_required: false },
];

describe('Note pondérée indicative (H4)', () => {
  it('exemple de l’étude : 3,70 sur 5 → 74 sur 100', () => {
    // (4×25 + 4×30 + 3×15 + 3×15 + 4×15) / 100 = 3,70.
    const values = { originalite: 4, methode: 4, pertinence: 3, redaction: 3, impact: 4 };
    expect(weightedScore(GRID, values, 0, 5)).toBe(74);
  });

  it('critère facultatif non noté exclu ; obligatoire manquant : indéfinie', () => {
    const values = { originalite: '5', methode: '5', pertinence: '5', redaction: '5' };
    expect(weightedScore(GRID, values, 0, 5)).toBe(100);
    expect(weightedScore(GRID, { ...values, methode: '' }, 0, 5)).toBeNull();
  });

  it('minimum de l’échelle soustrait ; arrondi à deux décimales', () => {
    const grid = [
      { code: 'a', weight: '1' },
      { code: 'b', weight: '2' },
    ];
    expect(weightedScore(grid, { a: 1, b: 1 }, 1, 5)).toBe(0);
    expect(weightedScore(grid, { a: 2, b: 3 }, 1, 5)).toBe(41.67);
  });
});
