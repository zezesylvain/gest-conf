import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { expect, test } from '@playwright/test';

import { command, literal, python } from '../django';

/**
 * Parcours auteur complet (plan L3 §7, F14 ; démo D côté auteur) : inscription, vérification
 * de l'adresse, profil, brouillon, co-auteur, PDF, déclarations, soumission, accusé de
 * réception, modification (révision), clôture simulée, refus de modifier, recevabilité.
 */
const EMAIL = 'awa.kone@e2e.example.org';
const PASSWORD = 'Une-phrase-assez-longue-2026';

let seed: { code: string; pdf: string };

test.beforeAll(() => {
  seed = JSON.parse(python(readFileSync(resolve(__dirname, '../seed.py'), 'utf8')));
});

test('parcours auteur : de l’inscription à la recevabilité', async ({ page }) => {
  test.setTimeout(120_000);

  // Inscription ; le lien de vérification part en console : sa clé est recalculée.
  await page.goto('/compte/inscription');
  await page.getByLabel('Adresse e-mail').fill(EMAIL);
  await page.getByLabel('Mot de passe', { exact: true }).fill(PASSWORD);
  await page.getByLabel('Confirmer le mot de passe').fill(PASSWORD);
  await page.getByRole('button', { name: 'Créer mon compte' }).click();
  await expect(page).toHaveURL(/verifier-email/);
  const key = python(
    'from allauth.account.models import EmailAddress, EmailConfirmationHMAC\n' +
      `print(EmailConfirmationHMAC(EmailAddress.objects.get(email=${literal(EMAIL)})).key)`,
  );
  // Chargement complet : sur la même page, seul le fragment changerait (pas de lecture).
  await page.goto('about:blank');
  await page.goto(`/compte/verifier-email#${key}`);
  await expect(page.getByText('Votre adresse est vérifiée.')).toBeVisible();

  // Connexion, profil complet (prérequis de la soumission).
  await page.goto('/compte/connexion');
  await page.getByLabel('Adresse e-mail').fill(EMAIL);
  await page.getByLabel('Mot de passe').fill(PASSWORD);
  await page.getByRole('button', { name: 'Se connecter' }).click();
  await expect(page).toHaveURL(/\/compte$/);
  await page.goto('/compte/profil');
  await page.getByLabel('Prénom').fill('Awa');
  await page.getByLabel('Nom', { exact: true }).fill('Koné');
  await page.getByLabel('Institution').fill('Université Félix Houphouët-Boigny');
  await page.getByLabel('Pays').click();
  await page.getByRole('option', { name: /^Côte d.Ivoire$/ }).click(); // apostrophe d'Intl
  await page.getByRole('button', { name: 'Enregistrer' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Enregistré' })).toBeVisible();

  // Brouillon : informations en sauvegarde automatique.
  await page.goto('/compte/soumissions');
  await page.getByRole('button', { name: `Nouvelle soumission (${seed.code})` }).click();
  await expect(page).toHaveURL(/\/compte\/soumissions\/\d+$/);
  const saved = page.waitForResponse((r) => r.request().method() === 'PATCH' && r.ok());
  await page.getByLabel('Titre').fill('Apprentissage profond et paludisme');
  await page.getByLabel('Résumé').fill('Un modèle appliqué aux frottis sanguins.');
  await page.getByLabel('Mots-clés').fill('apprentissage profond, paludisme');
  await page.getByLabel('Thématique').click();
  await page.getByRole('option', { name: 'Intelligence artificielle' }).click();
  await page.getByLabel('Type de communication').click();
  await page.getByRole('option', { name: 'Communication orale' }).click();
  await page.getByLabel('Langue de la communication').click();
  await page.getByRole('option', { name: 'Français' }).click();
  await saved;
  await expect(page.getByText(/Enregistré à/)).toBeVisible();

  // Co-auteur.
  await page.getByRole('button', { name: '2. Auteurs' }).click();
  await page.getByRole('button', { name: 'Ajouter un auteur' }).click();
  const coauthor = page.locator('fieldset').nth(1);
  await coauthor.getByLabel('Prénom').fill('Mariam');
  await coauthor.getByLabel('Nom', { exact: true }).fill('Traoré');
  await coauthor.getByLabel('Adresse e-mail').fill('mariam.traore@e2e.example.org');
  await page.getByRole('button', { name: 'Enregistrer les auteurs' }).click();
  await expect(page.getByText('Auteurs enregistrés.')).toBeVisible();

  // PDF : métadonnées retirées (double aveugle, défaut de l'édition).
  await page.getByRole('button', { name: '3. Fichier' }).click();
  await page.locator('input[type=file]').setInputFiles(seed.pdf);
  await expect(page.getByText('Fichier déposé.')).toBeVisible();
  await expect(page.getByText('métadonnées supprimées')).toBeVisible();

  // Récapitulatif : il manque les déclarations (RG-01).
  await page.getByRole('button', { name: '5. Récapitulatif' }).click();
  await expect(page.getByText('Acceptez toutes les déclarations.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Soumettre' })).toBeDisabled();

  // Déclarations, enregistrées automatiquement.
  await page.getByRole('button', { name: '4. Déclarations' }).click();
  await expect(page.getByRole('checkbox').first()).toBeVisible();
  const declared = page.waitForResponse((r) => r.request().method() === 'PATCH' && r.ok());
  for (const box of await page.getByRole('checkbox').all()) {
    await box.check();
  }
  await declared;

  // Soumission : référence et accusé de réception.
  await page.getByRole('button', { name: '5. Récapitulatif' }).click();
  await expect(page.getByText('Votre soumission est complète')).toBeVisible();
  await page.getByRole('button', { name: 'Soumettre' }).click();
  const reference = `${seed.code}-0001`;
  await expect(page.getByRole('heading', { name: `Soumission ${reference}` })).toBeVisible();
  const emails = python(
    'from apps.communications.models import OutboxEmail\n' +
      `print(",".join(sorted(OutboxEmail.objects.filter(to_email__in=[${literal(EMAIL)}, ` +
      `"mariam.traore@e2e.example.org"]).values_list("template_code", flat=True))))`,
  );
  expect(emails.split(',')).toEqual(
    expect.arrayContaining(['submission/email/received', 'submission/email/coauthor']),
  );

  // Modification avant la clôture : révision conservée.
  await page.getByRole('button', { name: '1. Informations' }).click();
  const revised = page.waitForResponse((r) => r.request().method() === 'PATCH' && r.ok());
  await page.getByLabel('Titre').fill('Apprentissage profond et paludisme : étude');
  await revised;
  await expect(page.getByText(/1 version\(s\) enregistrée\(s\) après la soumission/)).toBeVisible();

  // Clôture simulée : la modification est refusée (RG-02), puis la clôture passe la
  // soumission en recevabilité.
  python(
    'from datetime import timedelta\nfrom django.utils import timezone\n' +
      'from apps.conferences.models import KeyDate\n' +
      `KeyDate.objects.filter(edition__code=${literal(seed.code)}, code="call_close")` +
      '.update(at=timezone.now() - timedelta(minutes=1))',
  );
  await page.reload();
  await expect(page.getByText('lecture seule')).toBeVisible();
  await expect(page.getByLabel('Titre')).toBeDisabled();
  command('close_call');
  await page.reload();
  await expect(page.getByText('Vérification de recevabilité').first()).toBeVisible();
  await expect(page.getByText('Notifications')).toBeVisible();
});
