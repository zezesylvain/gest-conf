#!/usr/bin/env node
/**
 * Contrôle après build du portail pré-rendu (plan L2 §2.2 et §9 ; E1).
 *
 * Une API injoignable ou en erreur pendant le pré-rendu donnerait un build vert avec des pages
 * vides ou manquantes (constaté en L2.0). Ce contrôle refuse de livrer : chaque route
 * annoncée par l'API (`/api/v1/public/portal/routes`, avec son nombre attendu) doit avoir sa
 * page `index.html`, portant le marqueur de rendu complet `data-gc-rendered`.
 *
 * Sans `GESTCONF_PRERENDER_API_ORIGIN` (CI, développement), le portail public est rendu dans
 * le navigateur : rien à contrôler.
 *
 * Usage : node scripts/check-prerender.mjs <dossier browser du portail>
 */
import { access, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

export const MARKER = /data-gc-rendered="(fr|en):[^"]+"/;

/** Fichier attendu pour une adresse publique (`/fr/appel/` → `fr/appel/index.html`). */
export function pageFile(directory, route) {
  const segments = route.split('/').filter(Boolean);
  return join(directory, ...segments, 'index.html');
}

/** Problèmes trouvés (liste vide : portail complet). */
export async function problems(directory, { routes, expected }) {
  const found = [];
  if (routes.length !== expected) {
    found.push(`${routes.length} routes reçues, ${expected} attendues.`);
  }
  for (const route of routes) {
    const file = pageFile(directory, route);
    try {
      await access(file);
    } catch {
      found.push(`${route} : page absente (${file}).`);
      continue;
    }
    if (!MARKER.test(await readFile(file, 'utf8'))) {
      found.push(`${route} : page pré-rendue incomplète (marqueur data-gc-rendered absent).`);
    }
  }
  return found;
}

async function main() {
  const [directory] = process.argv.slice(2);
  if (!directory) {
    console.error('Usage : node scripts/check-prerender.mjs <dossier browser du portail>');
    process.exit(2);
  }
  const origin = (process.env.GESTCONF_PRERENDER_API_ORIGIN ?? '').replace(/\/+$/, '');
  if (!origin) {
    console.log(
      'Pré-rendu du portail : GESTCONF_PRERENDER_API_ORIGIN absent, rendu navigateur, rien à contrôler.',
    );
    return;
  }
  const response = await fetch(`${origin}/api/v1/public/portal/routes`);
  if (!response.ok) {
    console.error(`Pré-rendu du portail : routes illisibles (HTTP ${response.status}).`);
    process.exit(1);
  }
  const body = await response.json();
  const found = await problems(directory, body);
  if (found.length) {
    console.error(`Pré-rendu du portail REFUSÉ :\n- ${found.join('\n- ')}`);
    process.exit(1);
  }
  console.log(`Pré-rendu du portail : complet (${body.routes.length} routes).`);
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) {
  await main();
}
