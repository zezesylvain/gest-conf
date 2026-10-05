import { RenderMode, ServerRoute } from '@angular/ssr';

/**
 * Pré-rendu statique (SSG) des pages publiques au moment du build : aucun serveur
 * Node en production (étude §10.4). Les URL non pré-rendues sont servies par
 * index.csr.html (rendu dans le navigateur), via la règle de repli du .htaccess.
 */
export const serverRoutes: ServerRoute[] = [
  { path: '', renderMode: RenderMode.Prerender },
  // Espace compte : jamais pré-rendu (lecture des jetons du fragment, état de session).
  { path: 'compte/**', renderMode: RenderMode.Client },
  { path: '**', renderMode: RenderMode.Client },
];
