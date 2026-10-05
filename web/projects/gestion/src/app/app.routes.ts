import { Routes } from '@angular/router';
import { capabilityGuard } from '@gestconf/shared';

import { editionHomeRedirect, lastEditionRedirect } from './core/redirects';

// La propriété « title » contient une clé de traduction (voir TranslatedTitleStrategy).
// Les gardes sont de l'ergonomie (règle n° 2) : chaque endpoint revérifie les droits.
export const routes: Routes = [
  { path: '', pathMatch: 'full', canActivate: [lastEditionRedirect], children: [] },
  {
    path: 'editions',
    title: 'gestion.editions.title',
    loadComponent: () => import('./pages/editions/editions-page').then((m) => m.EditionsPage),
  },
  {
    path: 'editions/:editionId',
    loadComponent: () => import('./layout/edition-layout').then((m) => m.EditionLayout),
    children: [
      { path: '', pathMatch: 'full', canActivate: [editionHomeRedirect], children: [] },
      {
        path: 'tableau-de-bord',
        title: 'gestion.dashboard.title',
        canActivate: [capabilityGuard('edition.read')],
        loadComponent: () =>
          import('./pages/dashboard/dashboard-page').then((m) => m.DashboardPage),
      },
      {
        path: 'parametrage/general',
        title: 'gestion.settings.general.title',
        canActivate: [capabilityGuard('edition.read')],
        loadComponent: () => import('./pages/settings/general-page').then((m) => m.GeneralPage),
      },
      {
        path: 'parametrage/thematiques',
        title: 'gestion.settings.tracks.title',
        canActivate: [capabilityGuard('edition.read')],
        loadComponent: () => import('./pages/settings/tracks-page').then((m) => m.TracksPage),
      },
      {
        path: 'parametrage/types',
        title: 'gestion.settings.types.title',
        canActivate: [capabilityGuard('edition.read')],
        loadComponent: () =>
          import('./pages/settings/submission-types-page').then((m) => m.SubmissionTypesPage),
      },
      {
        path: 'parametrage/calendrier',
        title: 'gestion.settings.calendar.title',
        canActivate: [capabilityGuard('edition.read')],
        loadComponent: () => import('./pages/settings/calendar-page').then((m) => m.CalendarPage),
      },
      {
        path: 'parametrage/confidentialite',
        title: 'gestion.settings.confidentiality.title',
        canActivate: [capabilityGuard('edition.read')],
        loadComponent: () =>
          import('./pages/settings/confidentiality-page').then((m) => m.ConfidentialityPage),
      },
      {
        path: 'comites/membres',
        title: 'gestion.members.title',
        canActivate: [capabilityGuard('members.read')],
        loadComponent: () => import('./pages/committees/members-page').then((m) => m.MembersPage),
      },
      {
        path: 'comites/invitations',
        title: 'gestion.invitations.title',
        canActivate: [capabilityGuard('members.read')],
        loadComponent: () =>
          import('./pages/committees/invitations-page').then((m) => m.InvitationsPage),
      },
      {
        path: 'portail/sections',
        title: 'gestion.portal.sections.title',
        canActivate: [capabilityGuard('edition.read')],
        loadComponent: () => import('./pages/portal/sections-page').then((m) => m.SectionsPage),
      },
      {
        path: 'portail/sections/:sectionId',
        title: 'gestion.portal.sections.title',
        canActivate: [capabilityGuard('edition.read')],
        loadComponent: () =>
          import('./pages/portal/section-editor-page').then((m) => m.SectionEditorPage),
      },
      {
        path: 'portail/pages',
        title: 'gestion.portal.pages.title',
        canActivate: [capabilityGuard('edition.read')],
        loadComponent: () => import('./pages/portal/pages-page').then((m) => m.PagesPage),
      },
      {
        path: 'portail/pages/:pageId',
        title: 'gestion.portal.pages.title',
        canActivate: [capabilityGuard('edition.read')],
        loadComponent: () =>
          import('./pages/portal/page-composer-page').then((m) => m.PageComposerPage),
      },
      {
        path: 'portail/documents',
        title: 'gestion.portal.files.title',
        canActivate: [capabilityGuard('edition.read')],
        loadComponent: () => import('./pages/portal/files-page').then((m) => m.FilesPage),
      },
      {
        path: 'portail/menus',
        title: 'gestion.portal.menus.title',
        canActivate: [capabilityGuard('edition.read')],
        loadComponent: () => import('./pages/portal/menus-page').then((m) => m.MenusPage),
      },
      {
        path: 'audit',
        title: 'gestion.audit.title',
        canActivate: [capabilityGuard('audit.read')],
        loadComponent: () => import('./pages/audit/audit-page').then((m) => m.AuditPage),
      },
    ],
  },
  {
    path: 'aide',
    title: 'gestion.help.title',
    loadComponent: () => import('./help/help-page').then((m) => m.HelpPage),
  },
  {
    path: 'acces-refuse',
    title: 'gestion.forbidden.title',
    loadComponent: () => import('./pages/forbidden/forbidden-page').then((m) => m.ForbiddenPage),
  },
  {
    path: '**',
    title: 'gestion.notFound.title',
    loadComponent: () => import('./pages/not-found/not-found-page').then((m) => m.NotFoundPage),
  },
];
