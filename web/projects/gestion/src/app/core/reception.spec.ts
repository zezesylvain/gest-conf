import { TestBed } from '@angular/core/testing';
import { ActivatedRouteSnapshot, convertToParamMap, UrlTree } from '@angular/router';
import { ActiveContext, MeStore } from '@gestconf/shared';

import { CHAIR_EDITION, provideGestionTesting } from '../../testing/gestion-testing';
import { Connectivity, ReceptionInstaller, receptionGuard, receptionRedirect } from './reception';

function route(editionId: string): ActivatedRouteSnapshot {
  return {
    paramMap: convertToParamMap({}),
    parent: { paramMap: convertToParamMap({ editionId }), parent: null },
  } as unknown as ActivatedRouteSnapshot;
}

async function run(guard: typeof receptionGuard, editionId = '3'): Promise<string> {
  const result = await TestBed.runInInjectionContext(() => guard(route(editionId), {} as never));
  return String(result as boolean | UrlTree);
}

describe('Accueil installable et hors ligne (plan L7, K5)', () => {
  afterEach(() => {
    localStorage.clear();
    document.getElementById('gestion-reception-manifest')?.remove();
  });

  it('garde : checkin.scan, ou présidence de séance ; refus sinon', async () => {
    TestBed.configureTestingModule({
      providers: provideGestionTesting([
        { ...CHAIR_EDITION, id: 3, capabilities: ['checkin.scan'] },
        { ...CHAIR_EDITION, id: 4, capabilities: ['sessions.chair'] },
        { ...CHAIR_EDITION, id: 5, capabilities: ['edition.read'] },
      ]),
    });
    expect(await run(receptionGuard, '3')).toBe('true');
    expect(await run(receptionGuard, '4')).toBe('true');
    expect(await run(receptionGuard, '5')).toBe('/acces-refuse');
  });

  it('démarré hors ligne, /me inconnu : l’accueil s’ouvre sur la liste de l’appareil', async () => {
    TestBed.configureTestingModule({ providers: provideGestionTesting([]) });
    TestBed.inject(MeStore).clear();
    TestBed.inject(Connectivity).startedOffline.set(true);
    expect(await run(receptionGuard, '3')).toBe('true');
  });

  it('adresse de démarrage de l’application installée : accueil de la dernière édition', async () => {
    TestBed.configureTestingModule({ providers: provideGestionTesting() });
    expect(await run(receptionRedirect)).toBe('/editions');
    TestBed.inject(ActiveContext).rememberEdition(3);
    expect(await run(receptionRedirect)).toBe('/editions/3/accueil');
  });

  it('manifeste ajouté par l’écran d’accueil seul ; pas de service worker en développement', async () => {
    TestBed.configureTestingModule({ providers: provideGestionTesting() });
    expect(document.querySelector('link[rel=manifest]')).toBeNull();
    expect(await TestBed.inject(ReceptionInstaller).install()).toBe(false);
    const link = document.querySelector<HTMLLinkElement>('link[rel=manifest]');
    expect(link?.getAttribute('href')).toBe('manifest.webmanifest');
    await TestBed.inject(ReceptionInstaller).install();
    expect(document.querySelectorAll('link[rel=manifest]')).toHaveLength(1);
  });
});
