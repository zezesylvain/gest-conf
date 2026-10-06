import { inject } from '@angular/core';
import { CanActivateFn, Route, Routes } from '@angular/router';
import { LanguageService } from '@gestconf/shared';

import { SITE_LANGUAGES, SITE_PAGES, SITE_PAGES_BY_SLUG, SiteLanguage } from './site/site-pages';

/** La langue du portail public est celle de l'adresse (E2) : appliquée avant le rendu. */
function useLanguage(lang: SiteLanguage): CanActivateFn {
  return () =>
    inject(LanguageService)
      .use(lang)
      .then(() => true);
}

const portalPage = () => import('./site/portal-page').then((m) => m.PortalPage);

/** `/fr/…` ou `/en/…` : pages du site (adresses figées), puis pages personnalisées `/p/:slug`. */
function languageRoutes(lang: SiteLanguage): Route {
  return {
    path: lang,
    canActivate: [useLanguage(lang)],
    children: [
      ...SITE_PAGES.map((page): Route => ({
        path: page[lang],
        pathMatch: 'full',
        loadComponent: portalPage,
        data: { lang, slug: page.slug },
      })),
      // Programme publié (plan L5, I7) : une page par jour et par session ; l'accueil du
      // programme reste la page du site (ci-dessus, adresse exacte).
      {
        path: SITE_PAGES_BY_SLUG['program'][lang],
        loadChildren: () =>
          import('./site/program/program.routes').then((m) => m.programRoutes(lang)),
      },
      // Déclarée avant « ** » (plan L2 §2.2) ; le slug vient du paramètre.
      { path: 'p/:slug', loadComponent: portalPage, data: { lang, custom: true } },
    ],
  };
}

// La propriété « title » contient une clé de traduction (voir TranslatedTitleStrategy) ; les
// pages publiques posent elles-mêmes leur titre (titre de la page en base).
export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'fr' },
  ...SITE_LANGUAGES.map(languageRoutes),
  {
    path: 'compte',
    loadChildren: () => import('./account/account.routes').then((m) => m.accountRoutes),
  },
  // Vérification publique d'une attestation ou d'une lettre (plan L7, K10) : adresse du QR,
  // hors des préfixes de langue, rendue dans le navigateur (jamais pré-rendue).
  {
    path: 'verification',
    title: 'portail.verification.title',
    loadComponent: () =>
      import('./pages/verification/verification-page').then((m) => m.VerificationPage),
  },
  {
    path: 'verification/:code',
    title: 'portail.verification.title',
    loadComponent: () =>
      import('./pages/verification/verification-page').then((m) => m.VerificationPage),
  },
  {
    path: '**',
    title: 'portail.notFound.title',
    loadComponent: () => import('./pages/not-found/not-found-page').then((m) => m.NotFoundPage),
  },
];
