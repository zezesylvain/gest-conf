import { TestBed } from '@angular/core/testing';
import { ActivatedRouteSnapshot, convertToParamMap, UrlTree } from '@angular/router';
import { ActiveContext, MeEdition } from '@gestconf/shared';

import {
  CHAIR_EDITION,
  provideGestionTesting,
  REVIEWER_EDITION,
} from '../../testing/gestion-testing';
import { editionHomeRedirect, lastEditionRedirect } from './redirects';

const SC_CHAIR: MeEdition = {
  ...CHAIR_EDITION,
  id: 4,
  code: 'GC28',
  roles: [{ role: 'SC_CHAIR', oc_function: '' }],
  capabilities: ['members.read', 'members.manage'],
};

function run(guard: typeof lastEditionRedirect, editionId?: string): string {
  const route = { paramMap: convertToParamMap(editionId ? { editionId } : {}), parent: null };
  return String(
    TestBed.runInInjectionContext(() =>
      guard(route as unknown as ActivatedRouteSnapshot, {} as never),
    ) as UrlTree,
  );
}

describe('Redirections de la gestion', () => {
  afterEach(() => localStorage.clear());

  it('une seule édition gérée : directement dans l’édition', () => {
    TestBed.configureTestingModule({ providers: provideGestionTesting() });
    expect(run(lastEditionRedirect)).toBe('/editions/3');
  });

  it('plusieurs éditions : la dernière utilisée, sinon le sélecteur', () => {
    TestBed.configureTestingModule({ providers: provideGestionTesting([CHAIR_EDITION, SC_CHAIR]) });
    expect(run(lastEditionRedirect)).toBe('/editions');
    TestBed.inject(ActiveContext).rememberEdition(4);
    expect(run(lastEditionRedirect)).toBe('/editions/4');
  });

  it('accueil d’une édition selon les capacités (D8 : président du CS → membres)', () => {
    TestBed.configureTestingModule({ providers: provideGestionTesting([CHAIR_EDITION, SC_CHAIR]) });
    expect(run(editionHomeRedirect, '3')).toBe('/editions/3/tableau-de-bord');
    expect(run(editionHomeRedirect, '4')).toBe('/editions/4/comites/membres');
    expect(run(editionHomeRedirect, '99')).toBe('/acces-refuse');
  });

  it('relecteur (plan L4, H1) : « Mes évaluations »', () => {
    TestBed.configureTestingModule({
      providers: provideGestionTesting([{ ...REVIEWER_EDITION, id: 5 }]),
    });
    expect(run(editionHomeRedirect, '5')).toBe('/editions/5/evaluations');
  });
});
