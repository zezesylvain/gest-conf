#!/usr/bin/env node
/**
 * Contrôle après build du service worker de l'accueil (plan L7, K5).
 *
 * Le service worker d'Angular refuse une version dont un fichier ne correspond pas à son
 * empreinte SHA-1 de `ngsw.json`. L'écran d'accueil ne marcherait alors plus sans réseau.
 * Or `inject-csp.mjs` réécrit `index.html` après le build : `ngsw.json` est régénéré
 * ensuite (`ngsw-config`, script `build`). Ce contrôle refuse de livrer si une empreinte
 * est fausse, par exemple après un traitement ajouté plus tard.
 *
 * Usage : node scripts/check-ngsw.mjs <dossier browser de la gestion>
 */
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

/** Fichiers dont l'empreinte ne correspond pas (liste vide : manifeste cohérent). */
export async function mismatches(directory) {
  const manifest = JSON.parse(await readFile(join(directory, 'ngsw.json'), 'utf8'));
  const base = new URL(manifest.index, 'https://x').pathname.replace(/[^/]*$/, '');
  const found = [];
  for (const [url, expected] of Object.entries(manifest.hashTable)) {
    const file = join(directory, url.startsWith(base) ? url.slice(base.length) : url);
    let actual = null;
    try {
      actual = createHash('sha1')
        .update(await readFile(file))
        .digest('hex');
    } catch {
      // Fichier absent : signalé comme une empreinte fausse.
    }
    if (actual !== expected) {
      found.push(url);
    }
  }
  return found;
}

async function main(directory) {
  if (!directory) {
    throw new Error('Usage : node scripts/check-ngsw.mjs <dossier>');
  }
  const found = await mismatches(directory);
  if (found.length) {
    throw new Error(`Empreintes fausses dans ngsw.json : ${found.join(', ')}`);
  }
  console.log('ngsw.json : empreintes conformes.');
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  main(process.argv[2]).catch((error) => {
    console.error(error.message);
    process.exit(1);
  });
}
