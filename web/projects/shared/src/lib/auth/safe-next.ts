/** Chemins internes autorisés après la connexion (plan L1, D11). */
const ALLOWED_PREFIXES = ['/compte', '/gestion'];
export const DEFAULT_NEXT = '/compte';

// Caractères de contrôle (C0, DEL, C1), interdits dans une cible de redirection.
// eslint-disable-next-line no-control-regex
const CONTROL_CHARACTERS = /[\u0000-\u001f\u007f-\u009f]/;

/**
 * Valide le paramètre `next` : un chemin relatif sous `/compte` ou `/gestion`, rien
 * d'autre. Refuse `//hote`, `\\`, les schémas (`javascript:`, `https:`), les caractères de
 * contrôle et les remontées (`/compte/../`). Évite les redirections ouvertes.
 * Renvoie `fallback` si la valeur est refusée.
 */
export function safeNext(value: unknown, fallback: string = DEFAULT_NEXT): string {
  if (typeof value !== 'string' || value.length === 0 || value.length > 2048) {
    return fallback;
  }
  if (CONTROL_CHARACTERS.test(value) || value.includes('\\') || !value.startsWith('/')) {
    return fallback;
  }
  if (value.startsWith('//')) {
    return fallback;
  }
  let url: URL;
  try {
    url = new URL(value, 'https://gestconf.invalid');
  } catch {
    return fallback;
  }
  if (url.origin !== 'https://gestconf.invalid') {
    return fallback;
  }
  // Le chemin normalisé (après résolution de « .. » et décodage) doit rester autorisé.
  let decoded: string;
  try {
    decoded = decodeURIComponent(url.pathname);
  } catch {
    return fallback;
  }
  if (decoded.includes('..') || decoded.includes('//') || decoded.includes('\\')) {
    return fallback;
  }
  const allowed = ALLOWED_PREFIXES.some(
    (prefix) => url.pathname === prefix || url.pathname.startsWith(`${prefix}/`),
  );
  return allowed ? `${url.pathname}${url.search}${url.hash}` : fallback;
}

/** Vrai si la cible relève de l'application de gestion (autre application : page entière). */
export function isManagementUrl(url: string): boolean {
  return url === '/gestion' || url.startsWith('/gestion/');
}
