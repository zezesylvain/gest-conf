import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { Browser, expect, Page, test } from '@playwright/test';

import { command, literal, python } from '../django';
import { freshTotpCode } from '../totp';

/**
 * Parcours de bout en bout, en série (chaque étape part de l'état laissé par la précédente) :
 *
 * 1. auteur (plan L3 §7, F14 ; démo D) : inscription, vérification de l'adresse, profil,
 *    brouillon, co-auteur, PDF, déclarations, soumission, accusé de réception, modification
 *    (révision), clôture simulée, refus de modifier, recevabilité ;
 * 2. comité scientifique, dans la gestion (plan L4 §7 ; démo E) : affectation de deux
 *    relecteurs, recevabilité, évaluations en double aveugle (RG-04), passage automatique en
 *    « évaluée » (RG-07), décision provisoire, publication (RG-09) ;
 * 3. auteur : décision et commentaires sous pseudonymes, sans commentaire confidentiel
 *    (RG-10), dépôt de la version finale avec la lettre de réponse (H18) ;
 * 4. auteur : confirmation de présentation (plan L5, I5) ;
 * 5. programme, dans la gestion (plan L5 §7 ; démo F) : salle et session (CO « programme »),
 *    placement au clavier, dépassement signalé puis corrigé (RG-13), publication par le Chair
 *    (I6) et e-mail de passage (I16) ;
 * 6. auteure : « Mon passage », fichier iCal (I8), programme public (I7).
 */
test.describe.configure({ mode: 'serial' });

const EMAIL = 'awa.kone@e2e.example.org';
const PASSWORD = 'Une-phrase-assez-longue-2026';
const GESTION = 'http://localhost:4201/gestion';
const CONFIDENTIAL = 'Note confidentielle au comité E2E';

let seed: {
  code: string;
  edition: number;
  pdf: string;
  password: string;
  totp: string;
  chair: string;
  reviewer1: string;
  reviewer2: string;
  program: string;
  conference_chair: string;
};
let reference = '';

test.beforeAll(() => {
  seed = JSON.parse(python(readFileSync(resolve(__dirname, '../seed.py'), 'utf8')));
  reference = `${seed.code}-0001`;
});

function outbox(to: string): string[] {
  return python(
    'from apps.communications.models import OutboxEmail\n' +
      `print(",".join(OutboxEmail.objects.filter(to_email=${literal(to)})` +
      '.order_by("id").values_list("template_code", flat=True)))',
  ).split(',');
}

function submissionStatus(): string {
  return python(
    'from apps.submissions.models import Submission\n' +
      `print(Submission.objects.get(reference=${literal(reference)}).status)`,
  );
}

/** Connexion d'un membre du comité : mot de passe, puis code TOTP (2FA imposée, D3, H2). */
async function committeeLogin(browser: Browser, email: string): Promise<Page> {
  const context = await browser.newContext({
    baseURL: 'http://localhost:4200',
    locale: 'fr-FR',
    viewport: { width: 1280, height: 900 },
  });
  const page = await context.newPage();
  await page.goto('/compte/connexion');
  await page.getByLabel('Adresse e-mail').fill(email);
  await page.getByLabel('Mot de passe').fill(seed.password);
  await page.getByRole('button', { name: 'Se connecter' }).click();
  await expect(page).toHaveURL(/double-authentification/);
  await page.getByLabel('Code').fill(await freshTotpCode(seed.totp));
  await page.getByRole('button', { name: 'Vérifier' }).click();
  await expect(page).toHaveURL(/\/compte$/);
  return page;
}

/** Évaluation complète par un relecteur, depuis « Mes évaluations ». */
async function review(page: Page, recommendation: string, comment: string): Promise<void> {
  await page.goto(`${GESTION}/editions/${seed.edition}/evaluations`);
  await page.getByRole('link', { name: new RegExp(reference) }).click();
  const scores = page.locator('input[id^="score-"]');
  await expect(scores.first()).toBeVisible();
  // RG-04 : ni nom, ni adresse, ni institution des auteurs.
  for (const identity of ['Koné', 'Traoré', EMAIL, 'Houphouët']) {
    await expect(page.locator('main')).not.toContainText(identity);
  }
  for (const input of await scores.all()) {
    await input.fill('4');
  }
  await expect(page.locator('.score')).toContainText('80'); // 4 sur 5 : 80 / 100
  await page.getByLabel('Recommandation').click();
  await page.getByRole('option', { name: recommendation, exact: true }).click();
  await page.getByLabel('Confiance').click();
  await page.getByRole('option', { name: '4', exact: true }).click();
  await page.getByLabel('Commentaire aux auteurs').fill(comment);
  await page.getByLabel('Commentaire confidentiel au comité').fill(CONFIDENTIAL);
  await page.getByRole('button', { name: "Envoyer l'évaluation" }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Envoyer' }).click();
  await expect(page.getByText('Évaluation envoyée.')).toBeVisible();
}

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

test('comité : affectation, recevabilité, évaluations (RG-04, RG-07), décision, publication', async ({
  browser,
}) => {
  test.setTimeout(180_000);
  const chair = await committeeLogin(browser, seed.chair);
  const first = await committeeLogin(browser, seed.reviewer1);
  const second = await committeeLogin(browser, seed.reviewer2);

  // Pilotage : deux relecteurs affectés (H6), puis recevabilité (H10).
  await chair.goto(`${GESTION}/editions/${seed.edition}/pilotage`);
  await chair.getByRole('link', { name: reference }).first().click();
  await expect(chair.getByRole('heading', { name: 'Relecteurs disponibles' })).toBeVisible();
  for (const name of ['Aminata Diallo', 'Serge Ekra']) {
    const row = chair.locator('tr', { hasText: name });
    await row.getByRole('button', { name: 'Affecter…' }).click();
    await chair.getByRole('button', { name: 'Affecter', exact: true }).click();
    await expect(row.getByText('déjà affecté')).toBeVisible();
  }
  await chair.getByRole('button', { name: "Recevable : ouvrir l'évaluation" }).click();
  await chair.getByRole('dialog').getByRole('button', { name: 'Ouvrir' }).click();
  await expect(chair.getByText('Évaluation ouverte.')).toBeVisible();
  expect(submissionStatus()).toBe('under_review');
  expect(outbox(seed.reviewer1)).toContain('review/email/assigned');

  // Évaluations en double aveugle ; la seconde fait passer en « évaluée » (RG-07).
  await review(first, 'accepter avec corrections', 'Clarifier le protocole expérimental.');
  expect(submissionStatus()).toBe('under_review');
  await review(second, 'accepter', "Comparer avec l'état de l'art récent.");
  expect(submissionStatus()).toBe('reviewed');

  // Décision provisoire, invisible de l'auteur jusqu'à la publication (RG-09).
  await chair.reload();
  await chair.getByLabel('Issue').click();
  await chair.getByRole('option', { name: 'acceptée sous réserve de corrections' }).click();
  await chair
    .getByLabel('Message du comité aux auteurs')
    .fill('Félicitations ; merci de tenir compte des remarques.');
  await chair.getByRole('button', { name: 'Enregistrer la décision' }).click();
  await expect(chair.getByText('Décision provisoire enregistrée.')).toBeVisible();
  expect(submissionStatus()).toBe('reviewed');
  expect(outbox(EMAIL)).not.toContain('submission/email/decision');

  // Publication des résultats : transition et e-mail à ce moment seulement (RG-09).
  await chair.goto(`${GESTION}/editions/${seed.edition}/classement`);
  await chair.getByRole('button', { name: /Publier les résultats/ }).click();
  await chair.getByRole('dialog').getByRole('button', { name: 'Publier' }).click();
  await expect(chair.getByText('1 décision(s) publiée(s).')).toBeVisible();
  expect(submissionStatus()).toBe('accepted_minor');
  expect(outbox(EMAIL)).toContain('submission/email/decision');
});

test('auteur : décision sous pseudonymes (RG-10), puis version finale (H18)', async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto('/compte/connexion');
  await page.getByLabel('Adresse e-mail').fill(EMAIL);
  await page.getByLabel('Mot de passe').fill(PASSWORD);
  await page.getByRole('button', { name: 'Se connecter' }).click();
  await expect(page).toHaveURL(/\/compte$/);
  await page.goto('/compte/soumissions');
  const row = page.locator('tbody tr', { hasText: reference });
  await expect(row).toContainText('Acceptée sous réserve de corrections');
  await expect(row).toContainText('version finale avant le');
  await row.getByRole('link').click();

  // Décision, message du comité, commentaires sous pseudonymes ; rien de confidentiel.
  const decision = page.locator('section.decision');
  await expect(decision).toContainText('Acceptée sous réserve de corrections');
  await expect(decision).toContainText('Félicitations ; merci de tenir compte des remarques.');
  await expect(decision.locator('.review h4')).toHaveText(['Relecteur 1', 'Relecteur 2']);
  await expect(decision).toContainText('Clarifier le protocole expérimental.');
  await expect(decision).toContainText("Comparer avec l'état de l'art récent.");
  for (const hidden of [CONFIDENTIAL, 'Diallo', 'Ekra', '/ 100']) {
    await expect(page.locator('main')).not.toContainText(hidden);
  }

  // Version finale : la lettre de réponse est exigée pour une acceptation sous réserve.
  const final = page.locator('section.final');
  await final.locator('input[type=file]').setInputFiles(seed.pdf);
  await page.getByRole('button', { name: 'Déposer la version finale' }).click();
  await expect(final.getByRole('alert')).toContainText(
    'La lettre de réponse aux relecteurs est obligatoire.',
  );
  await page
    .getByLabel('Lettre de réponse aux relecteurs')
    .fill('Protocole précisé (section 3) ; comparaison ajoutée (tableau 2).');
  await page.getByRole('button', { name: 'Déposer la version finale' }).click();
  await expect(page.getByText('Version finale déposée.')).toBeVisible();
  await expect(page.getByText('Version finale reçue').first()).toBeVisible();
  expect(submissionStatus()).toBe('camera_ready_received');
  expect(outbox(EMAIL)).toContain('submission/email/final_received');
  const download = await page.request.get(
    `/api/v1/submissions/${page.url().split('/').pop()}/final-version/content`,
  );
  expect(download.status()).toBe(200);
  expect(download.headers()['content-type']).toBe('application/pdf');
});

/** Connexion de l'auteure (sans 2FA : aucun rôle de gestion). */
async function authorLogin(page: Page): Promise<void> {
  await page.goto('/compte/connexion');
  await page.getByLabel('Adresse e-mail').fill(EMAIL);
  await page.getByLabel('Mot de passe').fill(PASSWORD);
  await page.getByRole('button', { name: 'Se connecter' }).click();
  await expect(page).toHaveURL(/\/compte$/);
}

test('auteur : confirmation de présentation (I5)', async ({ page }) => {
  await authorLogin(page);
  await page.goto('/compte/soumissions');
  await page.locator('tbody tr', { hasText: reference }).getByRole('link').click();
  const section = page.locator('section.presentation');
  await expect(section).toContainText('Désignez qui présentera la communication');
  await section.getByRole('checkbox', { name: /Awa Koné/ }).check();
  await section.getByRole('button', { name: 'Confirmer ma présentation' }).click();
  await expect(page.getByText('Présentation confirmée.')).toBeVisible();
  await expect(section).toContainText('présentateurs : Awa Koné');
  expect(submissionStatus()).toBe('confirmed');
});

test('programme : salle, session, placement au clavier, dépassement corrigé, publication', async ({
  browser,
}) => {
  test.setTimeout(180_000);
  const planner = await committeeLogin(browser, seed.program);
  const chair = await committeeLogin(browser, seed.conference_chair);
  const base = `${GESTION}/editions/${seed.edition}`;

  // Salle (I9).
  await planner.goto(`${base}/programme/salles`);
  await planner.getByRole('button', { name: 'Ajouter une salle' }).click();
  await planner.getByLabel('Nom').fill('Amphi A');
  await planner.getByLabel('Capacité').fill('120');
  await planner.getByRole('checkbox', { name: 'Vidéoprojecteur' }).check();
  await planner.getByRole('button', { name: 'Enregistrer' }).click();
  await expect(planner.locator('tbody')).toContainText('Amphi A');

  // Session trop courte pour une communication de 20 minutes (RG-13), à l'heure de l'édition.
  await planner.goto(`${base}/programme/sessions`);
  await planner.getByRole('button', { name: 'Ajouter une session' }).click();
  await planner.getByLabel('Salle').click();
  await planner.getByRole('option', { name: 'Amphi A' }).click();
  await planner.getByLabel('Titre (français)').first().fill('Santé et IA');
  await planner.getByLabel('Début').fill('2027-03-01T09:00');
  await planner.getByLabel('Fin').fill('2027-03-01T09:15');
  await planner.getByRole('button', { name: 'Enregistrer' }).first().click();
  await expect(planner.getByText('Session créée')).toBeVisible();

  // Planificateur, au clavier : « Placer dans… », choix de la session, « Placer ».
  await planner.goto(`${base}/programme`);
  const paper = planner.locator('#pool li', { hasText: reference });
  await paper.getByRole('button', { name: /Placer dans/ }).press('Enter');
  await planner
    .getByLabel('Session', { exact: true })
    .selectOption({ label: '09:00 · Santé et IA · Amphi A' });
  await paper.getByRole('button', { name: 'Placer', exact: true }).click();
  await expect(planner.getByRole('status')).toContainText('placée dans « Santé et IA »');
  await expect(planner.locator('#conflicts')).toContainText('déborde de 5 min (RG-13)');

  // Publication refusée tant que le conflit demeure (I6) : on corrige la durée.
  const slot = planner.locator('li.slot', { hasText: reference });
  await slot.getByRole('button', { name: /Actions/ }).click();
  await slot.getByLabel('Durée (min)').fill('15');
  await slot.getByRole('button', { name: 'Appliquer la durée' }).click();
  await expect(planner.locator('#conflicts')).toContainText('Aucun conflit.');

  // Publication par le Chair : la communication est programmée, l'auteure prévenue (I16).
  await chair.goto(`${base}/programme/publication`);
  await chair.getByRole('button', { name: 'Publier le programme' }).click();
  await chair.getByRole('dialog').getByRole('button', { name: 'Publier' }).click();
  await expect(chair.getByText('Programme publié (version 1).')).toBeVisible();
  await expect(chair.locator('tbody')).toContainText('Yao Kouassi');
  expect(submissionStatus()).toBe('scheduled');
  expect(outbox(EMAIL)).toContain('program/email/passage');
});

test('auteure : « Mon passage », fichier iCal (I8) et programme public (I7)', async ({ page }) => {
  await authorLogin(page);
  await page.getByRole('link', { name: 'Mon passage' }).first().click();
  const passage = page.locator('.passages li').first();
  await expect(passage).toContainText('09:00 – 09:15');
  await expect(passage).toContainText('Présentation');
  await expect(passage).toContainText('Santé et IA');
  await expect(passage).toContainText('Amphi A');
  const ics = await page.request.get('/api/v1/me/agenda.ics');
  expect(ics.status()).toBe(200);
  expect(ics.headers()['content-type']).toContain('text/calendar');
  const calendar = await ics.text();
  expect(calendar).toContain('DTSTART:20270301T090000Z');
  expect(calendar).toContain('LOCATION:Amphi A');

  // Créneau publié dans la soumission.
  await page.goto('/compte/soumissions');
  await page.locator('tbody tr', { hasText: reference }).getByRole('link').click();
  await expect(page.locator('section.presentation')).toContainText('Programmée :');

  // Programme public (rendu dans le navigateur en E2E ; pré-rendu au build en production).
  await page.goto('/fr/programme/');
  await expect(page.getByRole('link', { name: 'Santé et IA' })).toBeVisible();
  await page.getByRole('link', { name: 'Santé et IA' }).click();
  await expect(page.locator('h1')).toHaveText('Santé et IA');
  await expect(page.locator('main')).toContainText('Awa Koné');
  await expect(page.locator('main')).not.toContainText(EMAIL);
});
