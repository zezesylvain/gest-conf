import { FetchBackend, HttpBackend, HttpEvent, HttpRequest } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';

/** Origine de l'API lue au pré-rendu (`https://conf.example`, sans `/api`), sinon vide. */
export const PRERENDER_API_ORIGIN = (process.env['GESTCONF_PRERENDER_API_ORIGIN'] ?? '').replace(
  /\/+$/,
  '',
);

/**
 * Au pré-rendu (Node), envoie les requêtes `/api/…` à l'API de `GESTCONF_PRERENDER_API_ORIGIN`.
 * Placé au niveau du `HttpBackend`, **après** le cache de transfert : la clé du cache reste
 * l'adresse relative que demandera le navigateur, qui réutilise la réponse sans la redemander
 * (vérifié en L2.0 : un intercepteur faisait redemander chaque composition).
 */
@Injectable()
export class ServerApiBackend implements HttpBackend {
  private readonly fetchBackend = inject(FetchBackend);

  handle(request: HttpRequest<unknown>): Observable<HttpEvent<unknown>> {
    const url = new URL(request.url, 'http://prerender.invalid');
    if (!PRERENDER_API_ORIGIN || !url.pathname.startsWith('/api/')) {
      return this.fetchBackend.handle(request);
    }
    return this.fetchBackend.handle(
      request.clone({ url: PRERENDER_API_ORIGIN + url.pathname + url.search }),
    );
  }
}
