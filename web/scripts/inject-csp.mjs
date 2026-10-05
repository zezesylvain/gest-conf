#!/usr/bin/env node
/**
 * Ajoute une politique CSP à empreintes (balise <meta>) dans chaque page HTML du build.
 *
 * Le pré-rendu et l'hydratation d'Angular insèrent des scripts en ligne (relecture
 * d'événements, chargement différé des styles). Plutôt que d'autoriser tout script en
 * ligne ('unsafe-inline'), on n'autorise que ceux-là, par leur empreinte SHA-256.
 * L'option autoCsp d'Angular ferait la même chose mais est incompatible avec le pré-rendu.
 *
 * Les autres directives (frame-ancestors, img-src…) sont posées par l'en-tête HTTP
 * (deploy/apache/public_html.htaccess).
 *
 * Usage : node scripts/inject-csp.mjs <dossier_build> [<dossier_build> ...]
 */
import { createHash } from 'node:crypto';
import { readdir, readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const INLINE_SCRIPT = /<script\b(?![^>]*\bsrc\s*=)([^>]*)>([\s\S]*?)<\/script>/gi;
const EXECUTABLE_TYPES = new Set(['', 'text/javascript', 'application/javascript', 'module']);
const INLINE_HANDLER = /<[^>]+\son[a-z]+\s*=/i;

export function inlineScriptHashes(html) {
  const hashes = new Set();
  for (const [, attributes, body] of html.matchAll(INLINE_SCRIPT)) {
    const type = /\btype\s*=\s*["']?([^"'\s>]+)/i.exec(attributes)?.[1]?.toLowerCase() ?? '';
    if (!EXECUTABLE_TYPES.has(type)) {
      continue; // ex. <script type="application/json" id="ng-state"> : données, jamais exécutées
    }
    hashes.add(`'sha256-${createHash('sha256').update(body, 'utf8').digest('base64')}'`);
  }
  return [...hashes];
}

export function injectCsp(html) {
  if (/http-equiv=["']?Content-Security-Policy/i.test(html)) {
    throw new Error('La page contient déjà une CSP.');
  }
  if (INLINE_HANDLER.test(html)) {
    throw new Error('Gestionnaire d’événement en ligne (on…=) : non autorisé par la CSP.');
  }
  const scriptSrc = ["'self'", ...inlineScriptHashes(html)].join(' ');
  const policy = `script-src ${scriptSrc}; object-src 'none'; base-uri 'self'`;
  // Insérée en tête de <head> : une CSP en <meta> ne s'applique qu'au contenu qui la suit.
  const result = html.replace(
    /<head\b([^>]*)>/i,
    `<head$1><meta http-equiv="Content-Security-Policy" content="${policy}">`,
  );
  if (result === html) {
    throw new Error('Balise <head> introuvable.');
  }
  return result;
}

async function htmlFiles(directory) {
  const entries = await readdir(directory, { recursive: true, withFileTypes: true });
  return entries
    .filter((entry) => entry.isFile() && entry.name.endsWith('.html'))
    .map((entry) => join(entry.parentPath, entry.name));
}

async function main(directories) {
  if (directories.length === 0) {
    throw new Error('Usage : node scripts/inject-csp.mjs <dossier_build> [...]');
  }
  for (const directory of directories) {
    for (const file of await htmlFiles(directory)) {
      await writeFile(file, injectCsp(await readFile(file, 'utf8')));
      console.log(`CSP ajoutée : ${file}`);
    }
  }
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  main(process.argv.slice(2)).catch((error) => {
    console.error(error.message);
    process.exit(1);
  });
}
