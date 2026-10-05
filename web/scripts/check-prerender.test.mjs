import assert from 'node:assert/strict';
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

import { pageFile, problems } from './check-prerender.mjs';

async function site(pages) {
  const directory = await mkdtemp(join(tmpdir(), 'prerender-'));
  for (const [route, html] of Object.entries(pages)) {
    const file = pageFile(directory, route);
    await mkdir(join(file, '..'), { recursive: true });
    await writeFile(file, html);
  }
  return directory;
}

const COMPLETE = '<article data-gc-rendered="fr:home"></article>';

test('portail complet : aucun problème', async () => {
  const directory = await site({
    '/fr/': COMPLETE,
    '/en/p/infos/': COMPLETE.replace('fr:home', 'en:infos'),
  });
  assert.deepEqual(
    await problems(directory, { routes: ['/fr/', '/en/p/infos/'], expected: 2 }),
    [],
  );
});

test('page absente, page sans marqueur, compte inférieur à l’attendu : refus', async () => {
  const directory = await site({ '/fr/': '<article></article>' });
  const found = await problems(directory, { routes: ['/fr/', '/en/'], expected: 3 });
  assert.equal(found.length, 3);
  assert.match(found.join(' '), /2 routes reçues, 3 attendues/);
  assert.match(found.join(' '), /\/fr\/ : page pré-rendue incomplète/);
  assert.match(found.join(' '), /\/en\/ : page absente/);
});
