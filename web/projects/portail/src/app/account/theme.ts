/** Feuille du thème Angular Material, produite non injectée (angular.json, « gc-theme »). */
export const THEME_STYLESHEET = 'gc-theme.css';
const THEME_LINK_ID = 'gc-theme';

/**
 * Charge la feuille du thème au premier affichage de /compte (plan L1 §10.5) : les pages
 * publiques pré-rendues ne la paient pas. `style-src 'self'` autorise ce lien (CSP).
 */
export function ensureThemeStylesheet(document: Document): void {
  if (document.getElementById(THEME_LINK_ID)) {
    return;
  }
  const link = document.createElement('link');
  link.id = THEME_LINK_ID;
  link.rel = 'stylesheet';
  link.href = THEME_STYLESHEET;
  document.head.appendChild(link);
}
