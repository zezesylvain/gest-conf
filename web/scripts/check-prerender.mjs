#!/usr/bin/env node
/**
 * Contrôle après build du portail pré-rendu (plan L2 §2.2 et §9 ; E1).
 *
 * Une API injoignable ou en erreur pendant le pré-rendu donnerait un build vert avec des pages
 * vides ou manquantes (constaté en L2.0). Ce contrôle refuse de livrer : chaque route
 * annoncée par l'API (`/api/v1/public/portal/routes`, avec son nombre attendu) doit avoir sa
 * page `index.html`, portant le marqueur de rendu complet `data-gc-rendered`.
 *
 * Le portail complet, il écrit le plan du site `sitemap.xml` (variantes de langue `hreflang`)
 * et ajoute sa ligne `Sitemap:` à `robots.txt` (E7) : le plan décrit exactement ce qui est
 * publié.
 *
 * Sans `GESTCONF_PRERENDER_API_ORIGIN` (CI, développement), le portail public est rendu dans
 * le navigateur : rien à contrôler, pas de plan du site.
 *
 * Usage : node scripts/check-prerender.mjs <dossier browser du portail>
 */
import { access, appendFile, readFile, writeFile } from 'node:fs/promises';
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

const xml = (text) =>
  text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

/** Plan du site : une entrée par adresse, avec ses variantes FR/EN et `x-default` (FR). */
export function sitemap(siteUrl, pages) {
  const entries = [];
  for (const page of pages) {
    const alternates = [
      ['fr', page.paths.fr],
      ['en', page.paths.en],
      ['x-default', page.paths.fr],
    ]
      .map(
        ([lang, path]) =>
          `    <xhtml:link rel="alternate" hreflang="${lang}" href="${xml(siteUrl + path)}"/>`,
      )
      .join('\n');
    for (const path of new Set([page.paths.fr, page.paths.en])) {
      entries.push(`  <url>\n    <loc>${xml(siteUrl + path)}</loc>\n${alternates}\n  </url>`);
    }
  }
  return (
    '<?xml version="1.0" encoding="UTF-8"?>\n' +
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" ' +
    'xmlns:xhtml="http://www.w3.org/1999/xhtml">\n' +
    `${entries.join('\n')}\n</urlset>\n`
  );
}

async function readJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    console.error(`Pré-rendu du portail : ${url} illisible (HTTP ${response.status}).`);
    process.exit(1);
  }
  return response.json();
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
  const body = await readJson(`${origin}/api/v1/public/portal/routes`);
  const found = await problems(directory, body);
  if (found.length) {
    console.error(`Pré-rendu du portail REFUSÉ :\n- ${found.join('\n- ')}`);
    process.exit(1);
  }
  console.log(`Pré-rendu du portail : complet (${body.routes.length} routes).`);
  const { site_url: siteUrl } = await readJson(`${origin}/api/v1/public/portal/site`);
  // Pages du CMS, puis adresses des autres fournisseurs (programme publié, plan L5, I7).
  const entries = [...body.pages, ...(body.alternates ?? [])];
  await writeFile(join(directory, 'sitemap.xml'), sitemap(siteUrl, entries));
  await appendFile(join(directory, 'robots.txt'), `\nSitemap: ${siteUrl}/sitemap.xml\n`);
  console.log(`Plan du site écrit (${siteUrl}/sitemap.xml).`);
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) {
  await main();
}
