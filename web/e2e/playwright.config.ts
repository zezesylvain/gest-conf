import { defineConfig, devices } from '@playwright/test';

/**
 * Tests de bout en bout (CLAUDE.md, « Tests » ; plan L3 F14).
 *
 * Playwright lance lui-même l'API Django (base SQLite dédiée, recréée à chaque série) et le
 * portail (`ng serve`, mandataire `/api` → :8000). Variables utiles :
 * - `GESTCONF_E2E_PYTHON` : interpréteur Python du backend (défaut : `python`) ;
 * - `GESTCONF_E2E_CHROMIUM` : Chromium déjà installé (poste sans téléchargement de
 *   navigateurs) ; en CI, `npx playwright install --with-deps chromium`.
 */
const python = process.env['GESTCONF_E2E_PYTHON'] ?? 'python';
const database = 'sqlite:////tmp/gestconf-e2e.sqlite3';
const chromium = process.env['GESTCONF_E2E_CHROMIUM'];

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env['CI'],
  retries: 0,
  reporter: process.env['CI'] ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: 'http://localhost:4200',
    locale: 'fr-FR',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        ...(chromium ? { launchOptions: { executablePath: chromium } } : {}),
      },
    },
  ],
  webServer: [
    {
      // Base recréée : chaque série part d'un état connu.
      command:
        `rm -f /tmp/gestconf-e2e.sqlite3 && ${python} manage.py migrate --noinput -v0 ` +
        `&& ${python} manage.py createcachetable && ${python} manage.py runserver 127.0.0.1:8000 --noreload`,
      cwd: '../../backend',
      env: { DATABASE_URL: database, DJANGO_SETTINGS_MODULE: 'config.settings.dev' },
      url: 'http://127.0.0.1:8000/v1/health',
      timeout: 120_000,
      reuseExistingServer: false,
    },
    {
      command: 'npx ng serve portail --port 4200',
      cwd: '..',
      url: 'http://localhost:4200/compte/connexion',
      timeout: 240_000,
      reuseExistingServer: false,
    },
  ],
});
