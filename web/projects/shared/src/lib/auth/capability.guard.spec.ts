import { TestBed } from '@angular/core/testing';
import { ActivatedRouteSnapshot, convertToParamMap, provideRouter, UrlTree } from '@angular/router';

import { TEST_ME } from '../../testing';
import { anyCapabilityGuard, capabilityGuard } from './capability.guard';
import { MeStore } from './me.store';

function routeFor(editionId: string): ActivatedRouteSnapshot {
  const parent = { paramMap: convertToParamMap({ editionId }), parent: null };
  return { paramMap: convertToParamMap({}), parent } as unknown as ActivatedRouteSnapshot;
}

describe('capabilityGuard', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        {
          provide: MeStore,
          useValue: {
            loaded: () => true,
            me: () => ({
              ...TEST_ME,
              editions: [
                {
                  id: 3,
                  code: 'GC27',
                  title_fr: 'x',
                  title_en: 'x',
                  year: 2027,
                  status: 'draft',
                  roles: [{ role: 'SC_CHAIR', oc_function: '' }],
                  capabilities: ['members.read', 'members.manage'],
                  mfa_required: true,
                },
              ],
            }),
          },
        },
      ],
    });
  });

  async function run(guard: ReturnType<typeof capabilityGuard>, editionId: string) {
    return TestBed.runInInjectionContext(() => guard(routeFor(editionId), {} as never)) as Promise<
      boolean | UrlTree
    >;
  }

  it('capacité détenue dans l’édition de la route (paramètre du parent) : accès', async () => {
    expect(await run(capabilityGuard('members.read'), '3')).toBe(true);
  });

  it('capacité absente ou autre édition : page « accès refusé »', async () => {
    const denied = await run(capabilityGuard('edition.write'), '3');
    expect(String(denied)).toBe('/acces-refuse');
    expect(String(await run(capabilityGuard('members.read'), '4'))).toBe('/acces-refuse');
  });

  it('toutes les capacités exigées par capabilityGuard, une seule par anyCapabilityGuard', async () => {
    expect(String(await run(capabilityGuard('members.read', 'checkin.scan'), '3'))).toBe(
      '/acces-refuse',
    );
    expect(await run(anyCapabilityGuard('checkin.scan', 'members.read'), '3')).toBe(true);
    expect(String(await run(anyCapabilityGuard('checkin.scan', 'sessions.chair'), '3'))).toBe(
      '/acces-refuse',
    );
  });
});
