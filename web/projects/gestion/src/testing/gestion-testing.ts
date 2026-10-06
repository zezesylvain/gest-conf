import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { EnvironmentProviders, Provider, signal } from '@angular/core';
import { provideRouter, Routes } from '@angular/router';
import { Me, MeEdition, MeStore } from '@gestconf/shared';
import { provideI18nTesting, TEST_ME } from '@gestconf/shared/testing';

/** Édition de test : président de la conférence (capacités du serveur : tout sauf l'archivage
 * et l'évaluation elle-même, `reviews.write`). */
export const CHAIR_EDITION: MeEdition = {
  id: 3,
  code: 'GC27',
  title_fr: 'GEST-CONF 2027',
  title_en: 'GEST-CONF 2027',
  year: 2027,
  status: 'draft',
  roles: [{ role: 'CHAIR', oc_function: '' }],
  capabilities: [
    'edition.read',
    'edition.write',
    'edition.publish',
    'members.read',
    'members.manage',
    'audit.read',
    'submissions.read',
    'submissions.extend',
    'submissions.export',
    'reviews.manage',
    'reviews.read_all',
    'decisions.decide',
    'decisions.publish',
    'grids.write',
    'program.read',
    'program.publish',
    'registrations.read',
    'finance.read',
  ],
  mfa_required: true,
};

/** Membre du CO de fonction « programme » (plan L5, I1) : lecture et écriture du programme. */
export const PROGRAM_EDITION: MeEdition = {
  ...CHAIR_EDITION,
  roles: [{ role: 'OC_MEMBER', oc_function: 'program' }],
  capabilities: ['edition.read', 'submissions.read', 'program.read', 'program.write'],
};

/** Membre du CO de fonction « finances » (plan L6, J1) : inscriptions, tarifs et finances. */
export const FINANCE_EDITION: MeEdition = {
  ...CHAIR_EDITION,
  roles: [{ role: 'OC_MEMBER', oc_function: 'finance' }],
  capabilities: [
    'edition.read',
    'submissions.read',
    'program.read',
    'registrations.read',
    'registrations.manage',
    'pricing.write',
    'finance.read',
  ],
};

/** Relecteur (membre du comité scientifique) : ses évaluations seulement (plan L4, H19). */
export const REVIEWER_EDITION: MeEdition = {
  ...CHAIR_EDITION,
  roles: [{ role: 'SC_MEMBER', oc_function: '' }],
  capabilities: ['reviews.write'],
};

/** Fournisseurs communs des tests de la gestion : traductions réelles, `/me` simulé. */
export function provideGestionTesting(
  editions: MeEdition[] = [CHAIR_EDITION],
  routes: Routes = [],
): (Provider | EnvironmentProviders)[] {
  const me = signal<Me | null>({ ...TEST_ME, id: 1, mfa_enabled: true, editions });
  return [
    provideRouter(routes),
    provideHttpClient(),
    provideHttpClientTesting(),
    provideI18nTesting({
      fr: () => import('../i18n/fr.json'),
      en: () => import('../i18n/en.json'),
    }),
    {
      provide: MeStore,
      useValue: {
        me,
        loaded: () => me() !== null,
        load: async () => me(),
        updateLocale: async () => me(),
        clear: () => me.set(null),
      },
    },
  ];
}
