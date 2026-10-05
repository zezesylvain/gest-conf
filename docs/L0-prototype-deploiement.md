# Lot L0 — Squelette et prototype de déploiement

Objectif (étude §14.1) : disposer d'un squelette Django + deux applications Angular
déployable sur o2switch, pour lever **avant tout développement lourd** les risques
d'hébergement identifiés au §11 (Passenger, `.htaccess`, pré-rendu, mono-domaine).

## 1. Ce qui est livré

| Élément | Contenu |
|---|---|
| API Django | Django 5.2 LTS, DRF, drf-spectacular, PyMySQL ; **sans `django.contrib.admin`** ; réglages `base/dev/test/prod` par variables d'environnement ; `GET /api/v1/health` ; erreurs normalisées `{code, message, fields}` (y compris 404/500 hors DRF) ; modèle `User` minimal identifié par e-mail |
| Montage `/api` | `config/mount.py` : les URL Django sont déclarées sans préfixe (`v1/...`), que Passenger place `/api` dans `SCRIPT_NAME` ou non |
| Angular | Workspace Angular 22 : `portail` (**pré-rendu statique**, aucun serveur Node), `gestion` (servie sous `/gestion/`), bibliothèque `@gestconf/shared` |
| Client API | Généré depuis `backend/schema.yml` par `ng-openapi-gen` (`npm run api:generate`), jamais édité à la main |
| Session + CSRF | Client HTTP configuré pour le cookie `csrftoken` / en-tête `X-CSRFToken` de Django |
| i18n | FR/EN avec `@ngx-translate`, aucune chaîne en dur ; traductions intégrées au build (fonctionne au pré-rendu) ; titres de page traduits ; langue mémorisée |
| Accessibilité | Lien d'évitement, `lang` du document synchronisé, règles ESLint d'accessibilité des gabarits |
| Sécurité HTTP | CSP à empreintes SHA-256 des scripts en ligne (post-build) + en-têtes Apache (CSP, `frame-ancestors`, HSTS, `nosniff`…) ; cookies `Secure`/`HttpOnly`/`SameSite` en production |
| Déploiement | `deploy/deploy.sh` (rsync/SSH), fusion sûre du `.htaccess` racine, `deploy/smoke-test.sh` |
| CI | GitHub Actions : ruff, pytest sur **MariaDB** (Python 3.12 et 3.13), `check --deploy`, schéma et client à jour, prettier, ESLint, tests Vitest, build, `pip-audit`, `npm audit`, ShellCheck |

## 2. Comment c'est vérifié

- **Backend** : 31 tests pytest (SQLite et MariaDB 10.11), dont des garde-fous sur
  les règles non négociables (pas d'admin, pas de rôle global, API fermée par défaut) ;
  6 tests du script de fusion du `.htaccess`.
- **Frontend** : 16 tests Vitest + 5 tests du script CSP ; lint et builds au vert.
- **Simulation de production** : Apache 2.4 avec les `.htaccess` réels (et un bloc
  Passenger factice à préserver), Django chargé par `passenger_wsgi.py` en
  configuration `prod` sur MariaDB, builds de production. Résultats :
  - les 9 tests de fumée passent ;
  - dans Chromium : hydratation, styles, changement de langue, replis 404 du portail
    et de la gestion, focus clavier sur le lien d'évitement — **aucune erreur
    console ni violation CSP** ;
  - contre-épreuve : un script injecté dans la page et une image vers un domaine
    tiers sont **bloqués** par la CSP.

La validation sur l'hébergement réel reste à faire : voir la liste de
[`deploy/README.md`](../deploy/README.md#4-points-à-valider-sur-lhébergement-réel-lot-l0).

## 3. Décisions techniques prises (et pourquoi)

| Décision | Raison |
|---|---|
| Django **5.2** | LTS en cours (support jusqu'en avril 2028) ; 6.x n'est pas LTS |
| PyMySQL sans contournement | La version 1.2.3 se déclare compatible `mysqlclient` 2.2.8 : vérifié dans le code de Django |
| Modèle `User` personnalisé dès L0 | Django impose de le définir avant la première migration ; le changer ensuite est très coûteux |
| `User` **sans** `PermissionsMixin` | Son champ `is_superuser` serait un rôle global implicite (règle n° 5) |
| Tables nommées à la Django (`accounts_user`) | Lisibilité par application ; les noms de l'étude §8 sont conceptuels |
| Pas de barre oblique finale dans les URL | Conforme à l'étude §9.2 (`/auth/login`…) ; `APPEND_SLASH=False` |
| CSP par script post-build plutôt que `autoCsp` d'Angular | `autoCsp` est expérimental et **refuse de fonctionner avec le pré-rendu** |
| Redirection HTTPS par cPanel, pas par `.htaccess` | Évite une boucle de redirection si Apache est derrière un proxy (non vérifié) |
| Aucun kit UI installé | Le choix Angular Material / PrimeNG reste ouvert (étude §7.2) |
| Node 24 pour les builds | Angular 22 exige Node ≥ 22.22.3 ; les builds se font en CI, pas sur o2switch |

## 4. Écarts avec l'étude — mises à jour proposées

1. **§11.2** : ajouter « MariaDB ≥ 10.5 » (exigence de Django 5.2) aux points à vérifier.
2. **§8.2, table `user`** : `email_verified_at` et `totp_enabled` sont gérés par
   `django-allauth` (adresse vérifiée) et `allauth.mfa` (2FA, décision D2 du lot L1) dans leurs
   propres tables ; proposer de les retirer de `user` pour éviter les doublons.
3. **§3.1 / §3.2** : l'« administrateur technique » a un périmètre global
   (paramétrage, comptes, audit) alors que tous les rôles sont rattachés à une
   édition. Il faut décider qui crée la première édition et gère les comptes
   (rôle de plateforme explicite et audité ? commande `manage.py` uniquement ?).
4. **§9.3, limitation de débit** : le cache par défaut de Django est propre à chaque
   processus ; sous Passenger (plusieurs processus) le *throttling* serait inopérant.
   Proposer un cache en base (`DatabaseCache`) au lot L1.
5. **§10.4, pré-rendu et bilinguisme** : seules les pages françaises sont
   pré-rendues ; la version anglaise est produite dans le navigateur, donc moins
   bien référencée. Si le référencement en anglais compte, pré-rendre des routes
   `/en/...` au lot L2.
6. **§9.1, codes HTTP** : avec l'authentification par session seule, DRF répond
   **403** (et non 401) à un utilisateur non connecté ; le client distingue les cas
   par le champ `code` (`not_authenticated` / `permission_denied`).

## 5. Prochaine étape : lot L1 (socle) — à valider avant de commencer

Le lot L1 touche au modèle de données et aux permissions : conformément à
`CLAUDE.md`, son plan sera soumis pour validation avant implémentation. Il couvrira :
comptes (`django-allauth` en mode *headless*, vérification d'e-mail), profil,
conférences/éditions, `UserRole(user, edition, role)`, 2FA TOTP, journal d'audit,
file de tâches `job` + `run_jobs`, cache en base, i18n complète et kit UI.
