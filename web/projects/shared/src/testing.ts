/*
 * Outils de test partagés (@gestconf/shared/testing) : à n'importer que dans les fichiers *.spec.ts.
 */
import { Provider, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideTranslateLoader, provideTranslateService } from '@ngx-translate/core';

import { AllauthUser } from './lib/auth/allauth';
import { MeStore } from './lib/auth/me.store';
import { SessionStore } from './lib/auth/session.store';
import { Me } from './lib/api/models/me';
import { JsonImportLoader, TranslationImporters } from './lib/i18n/json-import-loader';
import { LanguageService } from './lib/i18n/language.service';
import { AppLanguage, DEFAULT_LANGUAGE } from './lib/i18n/languages';
import { sharedTranslations } from './lib/i18n/provide-i18n';

/** Traductions réelles (communes + application) pour les tests de composants. */
export function provideI18nTesting(appTranslations?: TranslationImporters): Provider[] {
  const sources = appTranslations ? [sharedTranslations, appTranslations] : [sharedTranslations];
  return provideTranslateService({
    loader: provideTranslateLoader(() => new JsonImportLoader(sources)),
    fallbackLang: DEFAULT_LANGUAGE,
  });
}

/** Charge une langue avant de créer le composant testé. */
export async function useTestLanguage(lang: AppLanguage = DEFAULT_LANGUAGE): Promise<void> {
  await TestBed.inject(LanguageService).use(lang, { remember: false });
}

/** Compte de test par défaut (`/v1/me`). */
export const TEST_ME: Me = {
  id: 1,
  email: 'awa.kone@univ.ci',
  locale: 'fr',
  profile_complete: false,
  privacy_notice_pending: true,
  editions: [],
  pending_invitations: [],
};

/**
 * État d'authentification pour les tests de composants : session connectée (ou
 * anonyme avec `me: null`) et compte chargé, sans appel HTTP.
 */
export function provideAuthTesting(options: { me?: Me | null } = {}): Provider[] {
  const me = options.me === undefined ? TEST_ME : options.me;
  return [
    {
      provide: SessionStore,
      useFactory: () => {
        const store = new SessionStore();
        if (me) {
          const user: AllauthUser = {
            id: me.id,
            email: me.email,
            display: me.email,
            has_usable_password: true,
          };
          store.apply({ status: 200, authenticated: true, user, pendingFlow: null, errors: [] });
        } else {
          store.clear();
        }
        return store;
      },
    },
    {
      provide: MeStore,
      useValue: {
        me: signal(me).asReadonly(),
        loaded: signal(me !== null).asReadonly(),
        load: async () => me as Me,
        set: () => undefined,
        updateLocale: async () => me as Me,
        clear: () => undefined,
      } satisfies Partial<MeStore>,
    },
  ];
}
