import { DOCUMENT } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { ActiveContext } from './active-context';

describe('ActiveContext', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it('mémorise l’édition et le rôle actif (préférences seulement)', () => {
    const context = TestBed.inject(ActiveContext);
    expect(context.lastEditionId()).toBeNull();
    context.rememberEdition(5);
    context.setActiveRole(5, 'CHAIR');
    expect(context.lastEditionId()).toBe(5);
    expect(context.activeRole(5)).toBe('CHAIR');
    context.setActiveRole(5, null);
    expect(context.activeRole(5)).toBeNull();
  });

  it('stockage indisponible : aucune erreur, aucune préférence', () => {
    const failing = {
      getItem: () => {
        throw new Error('bloqué');
      },
      setItem: () => {
        throw new Error('bloqué');
      },
      removeItem: () => {
        throw new Error('bloqué');
      },
    };
    const document = TestBed.inject(DOCUMENT);
    vi.spyOn(document.defaultView!, 'localStorage', 'get').mockReturnValue(failing as never);
    const context = TestBed.inject(ActiveContext);
    expect(() => context.rememberEdition(5)).not.toThrow();
    expect(context.lastEditionId()).toBeNull();
  });
});
