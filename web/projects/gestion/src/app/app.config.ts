import {
  ApplicationConfig,
  inject,
  provideAppInitializer,
  provideBrowserGlobalErrorListeners,
} from '@angular/core';
import { provideRouter, withComponentInputBinding, withRouterConfig } from '@angular/router';
import { provideGestconfApi, provideI18n } from '@gestconf/shared';

import { routes } from './app.routes';
import { SessionBootstrap } from './core/session-bootstrap';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    // L'édition (:editionId) est lue par les pages enfants : héritage des paramètres.
    provideRouter(
      routes,
      withComponentInputBinding(),
      withRouterConfig({ paramsInheritanceStrategy: 'always' }),
    ),
    // Connexion dans le portail (D11) : retour par une navigation de page entière.
    provideGestconfApi({ loginNavigation: 'document' }),
    provideI18n({
      fr: () => import('../i18n/fr.json'),
      en: () => import('../i18n/en.json'),
    }),
    // Démarrage (plan L1 §10.4) : session, puis /me ; sans session, connexion du portail.
    provideAppInitializer(() => inject(SessionBootstrap).start()),
  ],
};
