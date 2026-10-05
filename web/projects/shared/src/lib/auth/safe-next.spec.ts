import { DEFAULT_NEXT, isManagementUrl, safeNext } from './safe-next';

describe('safeNext (redirections ouvertes)', () => {
  it.each([
    ['/compte/profil', '/compte/profil'],
    ['/compte', '/compte'],
    ['/gestion/editions/3?onglet=a#x', '/gestion/editions/3?onglet=a#x'],
    ['/gestion/', '/gestion/'],
  ])('accepte %s', (value, expected) => {
    expect(safeNext(value)).toBe(expected);
  });

  it.each([
    'https://pirate.example/compte',
    '//pirate.example/compte',
    '/\\pirate.example',
    '\\\\pirate.example',
    'javascript:alert(1)',
    'compte/profil',
    '/compte/../admin',
    '/compte/%2e%2e/admin',
    '/compte//pirate',
    '/autre',
    '/comptes',
    '/gestionnaire',
    '/compte\u0000',
    '/compte\n/x',
    '',
    null,
    42,
  ])('refuse %s', (value) => {
    expect(safeNext(value)).toBe(DEFAULT_NEXT);
  });

  it('identifie la gestion (autre application)', () => {
    expect(isManagementUrl('/gestion/editions/1')).toBe(true);
    expect(isManagementUrl('/compte')).toBe(false);
  });
});
