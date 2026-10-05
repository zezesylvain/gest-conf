import { expect, test } from '@playwright/test';

// Fumée de l'infrastructure E2E (L3.0) : portail servi, API jointe par le mandataire /api.
test('l’API répond derrière le mandataire /api du portail', async ({ request }) => {
  const response = await request.get('/api/v1/health');
  expect(response.status()).toBe(200);
  expect(await response.json()).toMatchObject({ database: 'ok' });
});

test('la page de connexion du compte s’affiche', async ({ page }) => {
  await page.goto('/compte/connexion');
  await expect(page.getByRole('heading', { name: 'Connexion' })).toBeVisible();
  await expect(page.getByLabel('Adresse e-mail')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Se connecter' })).toBeVisible();
});
