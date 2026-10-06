/*
 * API publique de la bibliothèque partagée @gestconf/shared.
 */

// Client de l'API généré depuis le schéma OpenAPI (npm run api:generate) : ne pas éditer.
export * from './lib/api';

export * from './lib/http/api-error';
export * from './lib/http/interceptors';
export * from './lib/http/provide-api';

export * from './lib/auth/active-context';
export * from './lib/auth/allauth';
export * from './lib/auth/auth-api';
export * from './lib/auth/auth.guard';
export * from './lib/auth/capability.guard';
export * from './lib/auth/login-navigation';
export * from './lib/auth/me.store';
export * from './lib/auth/reauthentication';
export * from './lib/auth/safe-next';
export * from './lib/auth/session.store';

export * from './lib/ui-kit/confirm-dialog';
export * from './lib/ui-kit/countries';
export * from './lib/ui-kit/date-format';
export * from './lib/ui-kit/error-summary';
export * from './lib/ui-kit/money-format';
export * from './lib/ui-kit/page-header';
export * from './lib/ui-kit/reauthentication-dialog';
export * from './lib/ui-kit/server-errors';

export * from './lib/i18n/languages';
export * from './lib/i18n/json-import-loader';
export * from './lib/i18n/language.service';
export * from './lib/i18n/translated-title.strategy';
export * from './lib/i18n/provide-i18n';
export * from './lib/i18n/language-switcher';

export * from './lib/api-status/api-status';
