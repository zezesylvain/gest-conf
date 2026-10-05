import { Routes } from '@angular/router';

// La propriété « title » contient une clé de traduction (voir TranslatedTitleStrategy).
export const routes: Routes = [
  {
    path: '',
    title: 'gestion.dashboard.title',
    loadComponent: () => import('./pages/dashboard/dashboard-page').then((m) => m.DashboardPage),
  },
  {
    path: '**',
    title: 'gestion.notFound.title',
    loadComponent: () => import('./pages/not-found/not-found-page').then((m) => m.NotFoundPage),
  },
];
