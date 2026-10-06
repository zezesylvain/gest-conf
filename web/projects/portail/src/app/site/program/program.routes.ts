import { Routes } from '@angular/router';

import { SiteLanguage } from '../site-pages';
import { ProgramDayPage } from './program-day-page';
import { ProgramSessionPage } from './program-session-page';

/**
 * Pages « jour » et « session » du programme public (plan L5, I7), sous `/<langue>/programme/`.
 * Un seul morceau chargé à la demande pour les deux pages (même raison que l'espace auteur :
 * le client partagé ne doit pas remonter dans le bundle initial).
 */
export function programRoutes(lang: SiteLanguage): Routes {
  return [
    { path: 'session/:id', component: ProgramSessionPage, data: { lang } },
    { path: ':day', component: ProgramDayPage, data: { lang } },
  ];
}
