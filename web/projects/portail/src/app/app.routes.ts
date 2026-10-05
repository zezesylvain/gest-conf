import { Routes } from '@angular/router';

// La propriété « title » contient une clé de traduction (voir TranslatedTitleStrategy).
export const routes: Routes = [
  {
    path: '',
    title: 'portail.home.title',
    loadComponent: () => import('./pages/home/home-page').then((m) => m.HomePage),
  },
  {
    path: 'compte',
    loadChildren: () => import('./account/account.routes').then((m) => m.accountRoutes),
  },
  {
    path: '**',
    title: 'portail.notFound.title',
    loadComponent: () => import('./pages/not-found/not-found-page').then((m) => m.NotFoundPage),
  },
];
