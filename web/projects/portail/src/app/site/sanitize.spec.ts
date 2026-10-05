import { safeHref, sanitizeHtml } from './sanitize';

describe('sanitizeHtml (portail, sans DOM)', () => {
  it.each([
    ['<p>Bonjour <strong>à tous</strong></p>', '<p>Bonjour <strong>à tous</strong></p>'],
    ['<b>gras</b> <i>it</i>', '<strong>gras</strong> <em>it</em>'],
    ['<p>a<br>b<br/>c</p>', '<p>a<br>b<br>c</p>'],
    ['<div><span>gardé</span></div>', 'gardé'],
    ['<ul><li>un<li>deux</ul>', '<ul><li>un</li><li>deux</li></ul>'],
    ['<p>non fermé', '<p>non fermé</p>'],
    ['</p>orphelin', 'orphelin'],
    ['<!-- c --><p>x</p>', '<p>x</p>'],
    ['<p>1 &lt; 2 &amp; 3</p>', '<p>1 &lt; 2 &amp; 3</p>'],
  ])('liste blanche : %s', (raw, expected) => {
    expect(sanitizeHtml(raw)).toBe(expected);
  });

  it.each([
    '<script>alert(1)</script>',
    '<img src=x onerror="alert(1)">',
    '<svg><script>alert(1)</script></svg>',
    '<svg onload=alert(1)>',
    '<iframe src="javascript:alert(1)"></iframe>',
    '<style>body{}</style>',
    '<p style="x" onclick="y()">t</p>',
    '<a href="javascript:alert(1)">x</a>',
    '<a href="  JaVaScRiPt:alert(1)">x</a>',
    '<a href="java&#x09;script:alert(1)">x</a>',
    '<a href="data:text/html;base64,PHNjcmlwdD4=">x</a>',
    '<a href="//evil.example/">x</a>',
    '<math><mtext><img src=x onerror=alert(1)></mtext></math>',
    '<a href="x" onmouseover="y()">x</a>',
    '<p title="a>b" onclick=z>t</p>',
  ])('aucun contenu actif : %s', (payload) => {
    const cleaned = sanitizeHtml(payload).toLowerCase();
    for (const needle of [
      '<script',
      'javascript:',
      'onerror',
      'onload',
      'onclick',
      'onmouseover',
      'style=',
      '<svg',
      '<iframe',
      '<img',
      'data:',
      '//evil',
      'src=',
    ]) {
      expect(cleaned).not.toContain(needle);
    }
  });

  it('liens : href sûr seulement, attributs retirés', () => {
    expect(sanitizeHtml('<a href="https://x.example/?a=1&amp;b=2" target="_blank">x</a>')).toBe(
      '<a href="https://x.example/?a=1&amp;b=2">x</a>',
    );
    expect(sanitizeHtml('<a href="/fr/appel/">a</a>')).toBe('<a href="/fr/appel/">a</a>');
    expect(sanitizeHtml('<a href="javascript:x">x</a>')).toBe('<a>x</a>');
  });

  it('sortie stable', () => {
    const once = sanitizeHtml('<ul><li>un<li>deux</ul><p>a & b <b>c</b>');
    expect(sanitizeHtml(once)).toBe(once);
  });

  it('safeHref', () => {
    expect(safeHref('mailto:contact@conf.example')).toBe('mailto:contact@conf.example');
    expect(safeHref('java\tscript:alert(1)')).toBeNull();
    expect(safeHref('ftp://x')).toBeNull();
  });
});
