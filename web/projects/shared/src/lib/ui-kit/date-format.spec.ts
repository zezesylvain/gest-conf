import { formatInZone, toDateTimeLocalValue } from './date-format';

describe('formatInZone', () => {
  it('affiche l’instant dans le fuseau demandé, avec son abréviation', () => {
    const text = formatInZone('2027-03-31T23:59:00Z', 'Africa/Abidjan', 'fr');
    expect(text).toContain('31');
    expect(text).toContain('23:59');
    expect(text).toMatch(/UTC|GMT/);
    expect(formatInZone('2027-07-01T21:59:00Z', 'Europe/Paris', 'fr')).toContain('23:59');
  });

  it('fuseau inconnu : repli en UTC ; valeur illisible : rendue telle quelle', () => {
    expect(formatInZone('2027-03-31T23:59:00Z', 'Mars/Olympus', 'en')).toMatch(/UTC/);
    expect(formatInZone('pas-une-date', 'UTC', 'fr')).toBe('pas-une-date');
  });

  it('valeur d’un champ datetime-local', () => {
    expect(toDateTimeLocalValue('2027-03-31T23:59:00')).toBe('2027-03-31T23:59');
  });
});
