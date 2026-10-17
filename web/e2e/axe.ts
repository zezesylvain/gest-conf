import AxeBuilder from '@axe-core/playwright';
import { expect, type Page } from '@playwright/test';

/**
 * Audit d'accessibilité automatique (plan L9, S8 ; WCAG 2.1 AA, CLAUDE.md « Angular »).
 *
 * Lance axe-core sur la page telle qu'elle est à cet instant du parcours et fait échouer le
 * test sur toute violation **grave** ou **critique** des règles WCAG 2.0 et 2.1 A et AA. Les
 * violations mineures ou modérées sont listées dans la sortie, sans échec : elles se
 * traitent au fil de l'eau. Un audit automatique ne remplace pas la revue manuelle (clavier,
 * lecteur d'écran) : il en attrape la part mécanique (contrastes, noms accessibles,
 * structure).
 */
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];
const BLOCKING = new Set(['serious', 'critical']);

export async function expectAccessible(page: Page, label: string): Promise<void> {
  const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  const describe = (violation: (typeof results.violations)[number]) =>
    `${violation.id} (${violation.impact}) : ${violation.help} — ` +
    violation.nodes
      .slice(0, 3)
      .map((node) => node.target.join(' '))
      .join(' | ');
  const minor = results.violations.filter((violation) => !BLOCKING.has(violation.impact ?? ''));
  if (minor.length) {
    console.log(`[axe] ${label} : ${minor.map(describe).join(' ; ')}`);
  }
  const blocking = results.violations.filter((violation) => BLOCKING.has(violation.impact ?? ''));
  expect(blocking.map(describe), `axe, ${label}`).toEqual([]);
}
