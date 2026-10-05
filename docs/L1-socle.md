# Lot L1 — Socle : bilan et exploitation

Ce document résume ce que livre le lot L1 de GEST-CONF et comment l'exploiter. Le détail des
choix, des vérifications et des écarts est dans [`L1-socle-plan.md`](L1-socle-plan.md)
(décisions D1 à D18 au §2, écarts au §16) ; l'étude est mise à jour en conséquence
(§17 « Mises à jour issues du lot L1 »).

## 1. Ce qui est livré

| Étape | Contenu | Commit |
|---|---|---|
| L1.0, L1.1 | Vérifications o2switch (script `deploy/check-o2switch.sh`), socle transverse : erreurs normalisées, CSRF, limites de débit, cache en base, schéma OpenAPI et client TypeScript, i18n FR/EN | `1136f4b` |
| L1.2 | Journal d'audit en ajout seul (RG-17), file de tâches (`Job`, `run_jobs`), e-mails en file avec voie rapide, `deploy/cron.sh`, `cleanup` | `9b28b62` |
| L1.3 | Comptes : allauth *headless* (client `browser`), sessions de 12 h absolues, réauthentification, profil, consentements, anti-énumération | `f8b9195` |
| L1.4 | Socle Angular (`shared` : façade d'authentification, intercepteurs, stores, kit UI, thème Material) ; espace compte du portail | `ab4c89b` |
| L1.5 | Éditions et paramétrage, rôles par édition et capacités, invitations (RG-20), permissions (ordre 401 → 404 → 403), matrice des droits testée | `9e139f6` |
| L1.6 | Double authentification (`allauth.mfa`) imposée aux rôles de gestion, secrets chiffrés, QR code, `reset_mfa`, `rotate_mfa_keys` ; pages sécurité et 2FA | `ea6717b` |
| L1.7 | Application de gestion (coque, sélecteurs, tableau de bord, paramétrage, membres, invitations, journal) ; `/compte/invitation` | `4f8cc03` |
| L1.8 | Données personnelles : registre, export, anonymisation (RG-18), durées de conservation (D15), `check_integrity` ; pages « Confidentialité » et « Mes données » ; mise à jour de l'étude | ce lot |

## 2. Parcours couverts

- **Visiteur** : portail public, édition courante publiée (`/api/v1/public/editions/current`).
- **Compte** (`/compte/…`) : inscription, vérification de l'adresse, connexion (avec étape 2FA),
  mot de passe oublié, profil et langue, sécurité (2FA, mot de passe, adresses), confidentialité
  (notice, consentements), mes données (export, anonymisation), invitation (consultation,
  acceptation, refus, liaison d'adresse).
- **Gestion** (`/gestion/…`) : sélection de l'édition, tableau de bord et publication,
  paramétrage bilingue (informations générales, thématiques, types, calendrier à l'heure de
  l'édition, confidentialité), membres et rôles, invitations, journal.
- **Opérateur** (commandes `manage.py`, toutes auditées) : `create_conference`,
  `create_edition --admin-email`, `set_current_edition`, `set_edition_status`, `grant_role`,
  `revoke_role`, `deactivate_user`, `reactivate_user`, `reset_mfa`, `rotate_mfa_keys`,
  `export_user_data`, `anonymize_user`, `audit_query`, `outbox`, `send_test_email`,
  `sync_email_addresses`.

## 3. Sécurité, en bref

- Aucun rôle global : les droits sont des capacités dans une édition, vérifiées par le serveur à
  chaque requête ; les gardes Angular ne sont que de l'ergonomie.
- 2FA obligatoire pour `ADMIN`, `CHAIR`, `SC_CHAIR`, `OC_MEMBER`, vérifiée à chaque requête de
  gestion ; réauthentification de moins de 5 min pour les opérations sensibles.
- Sessions par cookie `HttpOnly` (pas de jeton dans le navigateur), 12 h au plus ; CSRF sur
  allauth, DRF connecté et DRF anonyme.
- Invitations : le jeton seul ne donne jamais de rôle (RG-20).
- Journal d'audit sans adresse en clair ; données personnelles exportables et anonymisables ;
  balayage automatique après anonymisation (aucune colonne ni session ne garde l'adresse ou le
  nom).

## 4. Exploitation

- Variables d'environnement : `backend/.env.example` (dont `GESTCONF_PUBLIC_URL`,
  `GESTCONF_MFA_ENCRYPTION_KEYS`, fournisseur d'e-mails, `GESTCONF_OPERATORS`,
  `GESTCONF_TRUSTED_PROXY_COUNT`, `GESTCONF_RETENTION_ENFORCED`).
- Déploiement, cron (trois lignes : `run_jobs`, `cleanup`, `check_integrity`), clés de la 2FA,
  demandes relatives aux données personnelles : [`deploy/README.md`](../deploy/README.md).
- Tests de fumée : `deploy/smoke-test.sh` (portail, gestion, API, CSP, allauth, édition
  publique, diagnostic désactivé).

## 5. Tests

- Backend (pytest, SQLite et MariaDB) : matrice des droits par route et par rôle, ordre des
  réponses, double contrôle 2FA, flux allauth réels, contrats d'allauth figés, règles
  RG-17, RG-18, RG-20, introspection du registre des données personnelles, balayage après
  anonymisation, commandes, méta-tests de plateforme (pas d'admin Django, vues anonymes en
  liste blanche, CSRF, énumérations nommées).
- Frontend (Vitest) : façade d'authentification, intercepteurs, gardes, pages du compte et de
  la gestion ; parité des traductions FR/EN.
- Démos A et B rejouées en local dans Chromium (Playwright, script hors dépôt). Le test E2E
  automatisé dans le dépôt est prévu à partir de L3.

## 6. Ce qui reste à faire ou à décider

**Sur o2switch** (accès au compte nécessaire) : vérifications V01 à V27 et jalon J-tech
(`docs/L1-verifications-o2switch.md`), démos A et B en conditions réelles, tests de fumée en
production, cron actifs depuis 48 h sans battement de cœur en retard.

**Décisions du commanditaire** (plan §16, points marqués « à valider ») :

- durées de conservation de D15 (aujourd'hui en simulation) et texte définitif de la notice ;
- budget du bundle initial du portail (365 kB) ;
- émetteur affiché dans les applications TOTP (Q15) ;
- critère de fin de L1.1, cache en deux tables, `/health` (`jobs: late`), empreinte de commit
  dans la réponse publique ;
- 2FA des relecteurs (`SC_MEMBER`) avant L4 ;
- procédure de vérification d'identité avant `reset_mfa`.

**Propositions pour la suite** (plan §16) : exposer dans `/me` les rôles qu'un compte peut
attribuer (supprimer la table recopiée côté Angular) ; décrire dans le schéma OpenAPI la
variante sans adresse de la liste des membres.
