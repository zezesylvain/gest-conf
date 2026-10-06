import { defineConfig, devices } from '@playwright/test';

import { BACKEND_ENV, PYTHON } from './django';

/**
 * Tests de bout en bout (CLAUDE.md, « Tests » ; plan L3 F14).
 *
 * Playwright lance lui-même l'API Django (base SQLite dédiée, recréée à chaque série), le
 * portail et la gestion (`ng serve`, mandataire `/api` → :8000 ; la gestion sert sous
 * `/gestion/`, sur :4201). Variables utiles :
 * - `GESTCONF_E2E_PYTHON` : interpréteur Python du backend (défaut : `python`) ;
 * - `GESTCONF_E2E_CHROMIUM` : Chromium déjà installé (poste sans téléchargement de
 *   navigateurs) ; en CI, `npx playwright install --with-deps chromium`.
 */
const python = PYTHON;
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
      env: BACKEND_ENV,
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
    {
      // Plan L4 (L4.7) : recevabilité, évaluation et décision passent par la gestion.
      command: 'npx ng serve gestion --port 4201',
      cwd: '..',
      url: 'http://localhost:4201/gestion/',
      timeout: 240_000,
      reuseExistingServer: false,
    },
  ],
});
