import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideGestconfApi, provideI18n } from '@gestconf/shared';

import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    // Connexion dans le portail (D11) : retour par une navigation de page entière.
    provideGestconfApi({ loginNavigation: 'document' }),
    provideI18n({
      fr: () => import('../i18n/fr.json'),
      en: () => import('../i18n/en.json'),
    }),
  ],
};
