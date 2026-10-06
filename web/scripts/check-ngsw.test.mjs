import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, it } from 'node:test';

import { mismatches } from './check-ngsw.mjs';

const sha1 = (text) => createHash('sha1').update(text).digest('hex');

async function build(files, hashTable) {
  const directory = await mkdtemp(join(tmpdir(), 'ngsw-'));
  for (const [name, content] of Object.entries(files)) {
    await writeFile(join(directory, name), content);
  }
  await writeFile(
    join(directory, 'ngsw.json'),
    JSON.stringify({ index: '/gestion/index.html', hashTable }),
  );
  return directory;
}

describe('mismatches', () => {
  it('manifeste cohérent : rien à signaler', async () => {
    const directory = await build(
      { 'index.html': '<html>', 'main.js': 'a()' },
      { '/gestion/index.html': sha1('<html>'), '/gestion/main.js': sha1('a()') },
    );
    assert.deepEqual(await mismatches(directory), []);
  });

  it('index.html réécrit après le build (CSP) ou fichier absent : signalés', async () => {
    const directory = await build(
      { 'index.html': '<html><meta csp>' },
      { '/gestion/index.html': sha1('<html>'), '/gestion/main.js': sha1('a()') },
    );
    assert.deepEqual(await mismatches(directory), ['/gestion/index.html', '/gestion/main.js']);
  });
});
