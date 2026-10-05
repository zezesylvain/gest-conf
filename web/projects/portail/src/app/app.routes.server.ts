import { PrerenderFallback, RenderMode, ServerRoute } from '@angular/ssr';

import { PRERENDER_API_ORIGIN } from './server-api-backend';
import { SITE_LANGUAGES, SITE_PAGES } from './site/site-pages';

/**
 * Pré-rendu statique (SSG) au build, jamais de serveur Node en production (étude §10.4, E1).
 *
 * Les pages publiques sont pré-rendues **à partir de l'API** désignée par
 * `GESTCONF_PRERENDER_API_ORIGIN` (`deploy.sh --portal-only`). Sans elle (CI, poste de
 * développement), elles sont rendues dans le navigateur : le build reste possible, et
 * `scripts/check-prerender.mjs` ne contrôle rien. Les adresses non pré-rendues sont servies
 * par index.csr.html (repli du .htaccess).
 */
async function customPages(): Promise<{ slug: string }[]> {
  const response = await fetch(`${PRERENDER_API_ORIGIN}/api/v1/public/portal/routes`);
  if (!response.ok) {
    // Échec du build voulu : livrer un portail incomplet serait pire (plan L2 §9).
    throw new Error(`Routes du portail : HTTP ${response.status}`);
  }
  const body = (await response.json()) as { pages: { slug: string; is_system: boolean }[] };
  return body.pages.filter((page) => !page.is_system).map(({ slug }) => ({ slug }));
}

function sitePageRoute(path: string): ServerRoute {
  return PRERENDER_API_ORIGIN
    ? { path, renderMode: RenderMode.Prerender }
    : { path, renderMode: RenderMode.Client };
}

function customPageRoute(path: string): ServerRoute {
  return PRERENDER_API_ORIGIN
    ? {
        path,
        renderMode: RenderMode.Prerender,
        getPrerenderParams: customPages,
        fallback: PrerenderFallback.Client,
      }
    : { path, renderMode: RenderMode.Client };
}

const sitePageRoutes: ServerRoute[] = SITE_LANGUAGES.flatMap((lang) => [
  ...SITE_PAGES.map((page) => sitePageRoute(page[lang] ? `${lang}/${page[lang]}` : lang)),
  customPageRoute(`${lang}/p/:slug`),
]);

export const serverRoutes: ServerRoute[] = [
  // « / » : page de redirection vers /fr/ (repli ; le .htaccess redirige en 302).
  { path: '', renderMode: RenderMode.Prerender },
  ...sitePageRoutes,
  // Espace compte : jamais pré-rendu (lecture des jetons du fragment, état de session).
  { path: 'compte/**', renderMode: RenderMode.Client },
  { path: '**', renderMode: RenderMode.Client },
];
