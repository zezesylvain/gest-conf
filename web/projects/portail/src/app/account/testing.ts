import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { Provider, EnvironmentProviders } from '@angular/core';
import { provideRouter, Routes } from '@angular/router';
import { provideI18nTesting } from '@gestconf/shared/testing';

/** Fournisseurs communs des tests des pages /compte (traductions réelles du portail). */
export function provideAccountTesting(routes: Routes = []): (Provider | EnvironmentProviders)[] {
  return [
    provideRouter(routes),
    provideHttpClient(),
    provideHttpClientTesting(),
    provideI18nTesting({
      fr: () => import('../../i18n/fr.json'),
      en: () => import('../../i18n/en.json'),
    }),
  ];
}
