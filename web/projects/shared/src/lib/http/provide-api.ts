import { EnvironmentProviders } from '@angular/core';
import { provideHttpClient, withFetch, withXsrfConfiguration } from '@angular/common/http';

/**
 * Client HTTP de l'API GEST-CONF.
 *
 * Authentification par session Django + jeton CSRF (pas de JWT dans le navigateur) :
 * Angular lit le cookie « csrftoken » posé par Django et le renvoie dans l'en-tête
 * « X-CSRFToken » sur les requêtes modifiantes (POST, PUT, PATCH, DELETE).
 * L'URL racine (/api) provient du schéma OpenAPI (ApiConfiguration générée).
 */
export function provideGestconfApi(): EnvironmentProviders {
  return provideHttpClient(
    withFetch(),
    withXsrfConfiguration({ cookieName: 'csrftoken', headerName: 'X-CSRFToken' }),
  );
}
