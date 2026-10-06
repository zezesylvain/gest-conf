import { formatMoney } from './money-format';

/** Espaces insécables (séparateur de milliers, devise) ramenées à des espaces. */
const plain = (value: string) => value.replace(/[\u00a0\u202f]/g, ' ');

describe('formatMoney', () => {
  it('franc CFA sans décimales, euro avec deux décimales, langue de l’interface', () => {
    expect(plain(formatMoney('25000.00', 'XOF', 'fr'))).toBe('25 000 F CFA');
    expect(plain(formatMoney('12.5', 'EUR', 'fr'))).toBe('12,50 €');
    expect(formatMoney('12.5', 'EUR', 'en')).toBe('€12.50');
  });

  it('montant absent : tiret', () => {
    expect(formatMoney(null, 'XOF', 'fr')).toBe('—');
    expect(formatMoney('', 'XOF', 'fr')).toBe('—');
  });
});
