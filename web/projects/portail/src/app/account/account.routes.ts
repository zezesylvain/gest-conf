import { Routes } from '@angular/router';
import { authGuard } from '@gestconf/shared';

import { AccountShell } from './account-shell';

/**
 * Espace compte /compte/* (plan L1 §10.2) : chargé à la demande, rendu dans le navigateur
 * (les pages lisent des jetons dans le fragment), marqué noindex par la coque.
 * La propriété « title » contient une clé de traduction (TranslatedTitleStrategy).
 */
export const accountRoutes: Routes = [
  {
    path: '',
    component: AccountShell,
    children: [
      {
        path: '',
        pathMatch: 'full',
        title: 'portail.account.home.title',
        canMatch: [authGuard],
        loadComponent: () => import('./pages/account-home-page').then((m) => m.AccountHomePage),
      },
      {
        path: 'connexion',
        title: 'portail.account.login.title',
        loadComponent: () => import('./pages/login-page').then((m) => m.LoginPage),
      },
      {
        path: 'inscription',
        title: 'portail.account.signup.title',
        loadComponent: () => import('./pages/signup-page').then((m) => m.SignupPage),
      },
      {
        path: 'verifier-email',
        title: 'portail.account.verify.title',
        loadComponent: () => import('./pages/verify-email-page').then((m) => m.VerifyEmailPage),
      },
      {
        path: 'mot-de-passe-oublie',
        title: 'portail.account.forgot.title',
        loadComponent: () =>
          import('./pages/forgot-password-page').then((m) => m.ForgotPasswordPage),
      },
      {
        path: 'reinitialiser',
        title: 'portail.account.reset.title',
        loadComponent: () => import('./pages/reset-password-page').then((m) => m.ResetPasswordPage),
      },
      {
        path: 'double-authentification',
        title: 'portail.account.mfa.title',
        loadComponent: () => import('./pages/mfa-page').then((m) => m.MfaPage),
      },
      {
        path: 'securite',
        title: 'portail.account.security.title',
        canMatch: [authGuard],
        loadComponent: () => import('./pages/security/security-page').then((m) => m.SecurityPage),
      },
      {
        path: 'invitation',
        title: 'portail.account.invitation.title',
        loadComponent: () => import('./pages/invitation-page').then((m) => m.InvitationPage),
      },
      {
        path: 'confidentialite',
        title: 'portail.account.privacy.title',
        canMatch: [authGuard],
        loadComponent: () => import('./pages/privacy-page').then((m) => m.PrivacyPage),
      },
      {
        path: 'mes-donnees',
        title: 'portail.account.myData.title',
        canMatch: [authGuard],
        loadComponent: () => import('./pages/my-data-page').then((m) => m.MyDataPage),
      },
      {
        path: 'soumissions',
        canMatch: [authGuard],
        loadChildren: () =>
          import('./submissions/submissions.routes').then((m) => m.submissionRoutes),
      },
      {
        path: 'notifications',
        title: 'portail.notifications.title',
        canMatch: [authGuard],
        loadComponent: () =>
          import('./notifications/notifications-page').then((m) => m.NotificationsPage),
      },
      {
        path: 'profil',
        title: 'portail.account.profile.title',
        canMatch: [authGuard],
        loadComponent: () => import('./pages/profile-page').then((m) => m.ProfilePage),
      },
    ],
  },
];
