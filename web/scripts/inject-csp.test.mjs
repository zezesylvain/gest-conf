import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { describe, it } from 'node:test';

import { injectCsp, inlineScriptHashes } from './inject-csp.mjs';

const sha = (text) => `'sha256-${createHash('sha256').update(text, 'utf8').digest('base64')}'`;

describe('inlineScriptHashes', () => {
  it('calcule l’empreinte des seuls scripts en ligne exécutables (ni état, ni JSON-LD : E7)', () => {
    const html = `
      <script src="main.js" type="module"></script>
      <script>window.boot();</script>
      <script type="text/javascript" id="contract">(()=>{})()</script>
      <script id="ng-state" type="application/json">{"a":1}</script>
      <script type="application/ld+json">{"@type":"Event"}</script>`;
    assert.deepEqual(inlineScriptHashes(html), [sha('window.boot();'), sha('(()=>{})()')]);
  });

  it('dédoublonne les scripts identiques', () => {
    assert.equal(inlineScriptHashes('<script>a()</script><script>a()</script>').length, 1);
  });
});

describe('injectCsp', () => {
  it('insère la balise en tête de <head>, avant tout script', () => {
    const result = injectCsp('<html><head lang="fr"><script>a()</script></head></html>');
    assert.match(
      result,
      /^<html><head lang="fr"><meta http-equiv="Content-Security-Policy" content="script-src 'self' 'sha256-[^']+'; object-src 'none'; base-uri 'self'">/,
    );
  });

  it('refuse les gestionnaires d’événement en ligne', () => {
    assert.throws(() => injectCsp('<head></head><link onload="x()">'), /en ligne/);
  });

  it('refuse de traiter deux fois la même page', () => {
    const once = injectCsp('<head></head>');
    assert.throws(() => injectCsp(once), /déjà une CSP/);
  });
});
