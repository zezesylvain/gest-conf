/**
 * Réassainissement du HTML des sections au rendu (E3, défense en profondeur), **sans DOM** :
 * il s'exécute aussi au pré-rendu (Node). Même liste blanche que le serveur
 * (``backend/apps/portal/sanitizer.py``) : toute modification se reporte des deux côtés.
 */

const ALLOWED = new Set([
  'p',
  'br',
  'strong',
  'em',
  'ul',
  'ol',
  'li',
  'a',
  'h3',
  'h4',
  'blockquote',
]);
const RENAMED: Record<string, string> = { b: 'strong', i: 'em' };
const VOID = new Set(['br']);
const DROPPED_WITH_CONTENT = new Set([
  'script',
  'style',
  'iframe',
  'object',
  'embed',
  'svg',
  'math',
  'template',
  'noscript',
  'textarea',
  'select',
  'title',
  'head',
]);
const SCHEMES = ['http:', 'https:', 'mailto:', 'tel:'];

const TOKEN =
  /<!--[\s\S]*?(?:-->|$)|<(\/?)([a-zA-Z][a-zA-Z0-9]*)\b((?:[^>"']|"[^"]*"|'[^']*')*)>|<!\[CDATA\[[\s\S]*?(?:\]\]>|$)|<[!?][^>]*>?/g;
const HREF = /\bhref\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/i;
const ENTITY = /&(#x[0-9a-f]+|#[0-9]+|amp|lt|gt|quot|apos);/gi;

function decodeEntities(value: string): string {
  return value.replace(ENTITY, (_match, entity: string) => {
    const lower = entity.toLowerCase();
    if (lower.startsWith('#x')) return String.fromCodePoint(parseInt(lower.slice(2), 16));
    if (lower.startsWith('#')) return String.fromCodePoint(parseInt(lower.slice(1), 10));
    return { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'" }[lower] ?? '';
  });
}

function escapeText(value: string): string {
  // Texte déjà échappé par le serveur : on n'échappe que ce qui pourrait ouvrir une balise
  // et les « & » qui ne commencent pas une entité.
  return value
    .replace(/&(?!(#x[0-9a-f]+|#[0-9]+|[a-z]+);)/gi, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function escapeAttribute(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

/** Lien accepté (http(s), mailto, tel, chemin interne sans « // »), sinon `null`. */
export function safeHref(raw: string): string | null {
  // eslint-disable-next-line no-control-regex
  const href = decodeEntities(raw).replace(/[\u0000- \u007f]+/g, '');
  if (!href) return null;
  const lower = href.toLowerCase();
  if (lower.startsWith('/')) {
    return !lower.startsWith('//') && !href.includes('\\') ? href : null;
  }
  return SCHEMES.some((scheme) => lower.startsWith(scheme)) ? href : null;
}

export function sanitizeHtml(input: string | null | undefined): string {
  if (!input) return '';
  const out: string[] = [];
  const stack: string[] = [];
  let dropping = 0;
  let last = 0;
  const text = (value: string) => {
    if (!dropping && value) out.push(escapeText(value));
  };
  for (const match of input.matchAll(TOKEN)) {
    text(input.slice(last, match.index));
    last = match.index + match[0].length;
    const [, closing, rawName, attributes] = match;
    if (!rawName) continue; // commentaire, déclaration, CDATA : supprimés
    const lower = rawName.toLowerCase();
    if (DROPPED_WITH_CONTENT.has(lower)) {
      dropping = closing
        ? Math.max(0, dropping - 1)
        : dropping + (attributes?.trim().endsWith('/') ? 0 : 1);
      continue;
    }
    if (dropping) continue;
    const name = RENAMED[lower] ?? lower;
    if (!ALLOWED.has(name)) continue;
    if (closing) {
      if (!stack.includes(name)) continue;
      while (stack.length) {
        const current = stack.pop()!;
        out.push(`</${current}>`);
        if (current === name) break;
      }
      continue;
    }
    if (VOID.has(name)) {
      out.push(`<${name}>`);
      continue;
    }
    if ((name === 'li' || name === 'p') && stack.at(-1) === name) {
      out.push(`</${stack.pop()}>`);
    }
    let attribute = '';
    if (name === 'a') {
      const found = HREF.exec(attributes ?? '');
      const href = found ? safeHref(found[1] ?? found[2] ?? found[3] ?? '') : null;
      if (href) attribute = ` href="${escapeAttribute(href)}"`;
    }
    out.push(`<${name}${attribute}>`);
    stack.push(name);
  }
  text(input.slice(last));
  while (stack.length) out.push(`</${stack.pop()}>`);
  return out.join('').trim();
}
