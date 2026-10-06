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
        path: 'soumissions',
        title: 'gestion.submissions.title',
        canActivate: [capabilityGuard('submissions.read')],
        loadComponent: () =>
          import('./pages/submissions/submissions-page').then((m) => m.SubmissionsPage),
      },
      {
        path: 'soumissions/:submissionId',
        title: 'gestion.submissions.detail.title',
        canActivate: [capabilityGuard('submissions.read')],
        loadComponent: () =>
          import('./pages/submissions/submission-detail-page').then((m) => m.SubmissionDetailPage),
      },
      // Évaluation (plan L4, H1) : relecteur, puis président du CS.
      {
        path: 'evaluations',
        title: 'gestion.reviews.title',
        canActivate: [capabilityGuard('reviews.write')],
        loadComponent: () => import('./pages/reviews/my-reviews-page').then((m) => m.MyReviewsPage),
      },
      {
        path: 'evaluations/:assignmentId',
        title: 'gestion.reviews.form.title',
        canActivate: [capabilityGuard('reviews.write')],
        loadComponent: () =>
          import('./pages/reviews/review-form-page').then((m) => m.ReviewFormPage),
      },
      {
        path: 'expertises',
        title: 'gestion.expertise.title',
        canActivate: [capabilityGuard('reviews.write')],
        loadComponent: () => import('./pages/reviews/expertise-page').then((m) => m.ExpertisePage),
      },
      {
        path: 'pilotage',
        title: 'gestion.followUp.title',
        canActivate: [capabilityGuard('reviews.manage')],
        loadComponent: () => import('./pages/follow-up/follow-up-page').then((m) => m.FollowUpPage),
      },
      {
        path: 'pilotage/:submissionId',
        title: 'gestion.followUp.title',
        canActivate: [capabilityGuard('reviews.manage')],
        loadComponent: () =>
          import('./pages/follow-up/follow-up-detail-page').then((m) => m.FollowUpDetailPage),
      },
      {
        path: 'classement',
        title: 'gestion.ranking.title',
        canActivate: [capabilityGuard('reviews.read_all')],
        loadComponent: () => import('./pages/ranking/ranking-page').then((m) => m.RankingPage),
      },
      // Programme (plan L5, I15) : planificateur, sessions, salles, publication.
      {
        path: 'programme',
        title: 'gestion.program.planner.title',
        canActivate: [capabilityGuard('program.read')],
        loadComponent: () => import('./pages/program/planner-page').then((m) => m.PlannerPage),
      },
      {
        path: 'programme/sessions',
        title: 'gestion.program.sessions.title',
        canActivate: [capabilityGuard('program.read')],
        loadComponent: () => import('./pages/program/sessions-page').then((m) => m.SessionsPage),
      },
      {
        path: 'programme/salles',
        title: 'gestion.program.rooms.title',
        canActivate: [capabilityGuard('program.read')],
        loadComponent: () => import('./pages/program/rooms-page').then((m) => m.RoomsPage),
      },
      {
        path: 'programme/publication',
        title: 'gestion.program.publication.title',
        canActivate: [capabilityGuard('program.read')],
        loadComponent: () =>
          import('./pages/program/publication-page').then((m) => m.PublicationPage),
      },
      // Inscriptions et finances (plan L6, J12).
      {
        path: 'inscriptions',
        title: 'gestion.registrations.title',
        canActivate: [capabilityGuard('registrations.read')],
        loadComponent: () =>
          import('./pages/registrations/registrations-page').then((m) => m.RegistrationsPage),
      },
      {
        path: 'inscriptions/paiements',
        title: 'gestion.payments.title',
        canActivate: [capabilityGuard('finance.read')],
        loadComponent: () =>
          import('./pages/registrations/payments-page').then((m) => m.PaymentsPage),
      },
      {
        path: 'inscriptions/factures',
        title: 'gestion.billingDocuments.title',
        canActivate: [capabilityGuard('finance.read')],
        loadComponent: () =>
          import('./pages/registrations/billing-documents-page').then(
            (m) => m.BillingDocumentsPage,
          ),
      },
      {
        path: 'inscriptions/finances',
        title: 'gestion.finance.title',
        canActivate: [capabilityGuard('finance.read')],
        loadComponent: () =>
          import('./pages/registrations/finance-page').then((m) => m.FinancePage),
      },
      {
        path: 'inscriptions/:registrationId',
        title: 'gestion.registrations.detail.title',
        canActivate: [capabilityGuard('registrations.read')],
        loadComponent: () =>
          import('./pages/registrations/registration-detail-page').then(
            (m) => m.RegistrationDetailPage,
          ),
      },
      {
        path: 'parametrage/tarifs',
        title: 'gestion.settings.pricing.title',
        canActivate: [capabilityGuard('registrations.read')],
        loadComponent: () => import('./pages/settings/pricing-page').then((m) => m.PricingPage),
      },
      {
        path: 'parametrage/facturation',
        title: 'gestion.settings.billing.title',
        canActivate: [capabilityGuard('finance.read')],
        loadComponent: () =>
          import('./pages/settings/billing-profile-page').then((m) => m.BillingProfilePage),
      },
      {
        path: 'parametrage/programme',
        title: 'gestion.settings.program.title',
        canActivate: [capabilityGuard('program.read')],
        loadComponent: () =>
          import('./pages/settings/program-settings-page').then((m) => m.ProgramSettingsPage),
      },
      {
        path: 'parametrage/grilles',
        title: 'gestion.grids.title',
        canActivate: [capabilityGuard('edition.read')],
        loadComponent: () => import('./pages/settings/grids-page').then((m) => m.GridsPage),
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
