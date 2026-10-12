# Lot L9 — Recette, sécurité, charge : plan d'implémentation

> **Statut : validé le 12 octobre 2026, en cours** (décisions S1 à S16 telles que proposées ;
> les questions du §10 restent sans réponse : les propositions valent hypothèses, §2.1).
> L8 est livré et fusionné (PR #13 ; bilan : `docs/L8-logistique.md`). Les décisions de
> ce lot sont numérotées S : O se confond avec zéro, et P, Q et R désignent déjà les
> priorités, les questions et les risques.
>
> Sources :
> - étude §9.3 (sécurité), §11.2 (points non vérifiés), §11.4 à §11.7 (déploiement, cron,
>   sauvegarde et reprise, supervision), §12 (exigences non fonctionnelles), §14 (L9 : « tests
>   E2E, revue OWASP, test de charge, restauration, formation », P1, 10 à 14 j-h ; risques),
>   §15 (Q13 : volumes), annexes A5 (check-list de mise en production) et A6 (stratégie de
>   tests : « k6 / Lighthouse / axe / ZAP ») ;
> - mises à jour §17 à §24 : tout ce qui y est marqué « à vérifier sur o2switch », « non
>   vérifié » ou « démo … sur o2switch » ; plan L1, D17 (Sentry reporté en L9), D18 (aucune
>   donnée réelle avant une restauration testée), R13, R14 (coût de PBKDF2 au pic de
>   connexions : test de charge en L9) ; plan L3 (pic de clôture de l'appel : test de charge
>   en L9) ;
> - `docs/L1-verifications-o2switch.md` : **aucune ligne n'est encore remplie** ;
> - bilans `docs/L1-socle.md` à `docs/L8-logistique.md` : démos A à I à jouer sur o2switch ;
> - CLAUDE.md, règles n° 9 (cron idempotent et verrouillé), n° 10 (pas de dépendance système
>   lourde sur le serveur), n° 11 (secrets).

## En bref

| | |
|---|---|
| **Objectif** | Rendre la plateforme **prête pour sa première utilisation réelle** : sauvegarde automatique et **restauration testée**, supervision, revue de sécurité (OWASP Top 10), audit d'accessibilité automatisé, données de volume et **test de charge**, recette guidée des parcours (démos A à I), guides et formation, puis **premier déploiement réel sur o2switch** et check-list de mise en production (A5). |
| **Point dur** | **Rien n'a encore été vérifié sur o2switch** (fiche L1 vide, aucune démo). Cette session n'a pas accès à l'hébergement, et ne doit pas l'avoir : les clés SSH et les secrets de production restent chez vous. Le lot se fait donc en **deux volets** : ce qui se construit et se teste dans le dépôt (scripts, commandes, tests, correctifs, documents), puis ce qu'un **opérateur** exécute sur l'hébergement avec ces scripts, en rapportant leurs sorties (S1). Le lot n'est livré qu'avec le second volet. |
| **Hors périmètre** | Test d'intrusion par un tiers (sauf décision, question 6) ; déploiement continu depuis la CI (question 11) ; nouvelles fonctions (`ACCEPTED_MINOR → WITHDRAWN`, « Mon programme » J15, actes de L10) ; migration vers un VPS (seulement si le test de charge l'impose, étude §14.4) ; signature qualifiée (Q17). |
| **Charge** | **16,5 à 22,5 j-h** (étude : 10 à 14), dont 12,5 à 16,5 dans le dépôt et 4 à 6 sur l'hébergement, ces derniers dépendant de la disponibilité de l'opérateur. Détail au §8. |
| **Démo J** | Sur o2switch : la fiche de vérification est remplie ; `backup_db` tourne chaque nuit, la copie hors hébergement est rapatriée, et une **restauration** dans une base vide redonne une plateforme qui passe `check_integrity` et les tests de fumée, en moins de 4 heures. Le test de charge tient 200 utilisateurs simultanés avec moins de 500 ms au 95ᵉ centile. Les démos A à I se jouent sur l'édition de démonstration. La check-list A5 est cochée, pièce par pièce, sauf les points qui attendent une décision du commanditaire. |

## 1. Périmètre

| Fonction (étude) | Priorité | Dans L9 |
|---|---|---|
| Sauvegarde quotidienne, rotation 7/4/3, copie hors hébergement (§11.5, §11.6) | P1 | Oui (S2, S3) |
| Restauration testée et documentée, RPO 24 h, RTO 4 h (§11.6, A5, D18) | P1 | Oui (S3) |
| Supervision : disponibilité externe, erreurs, heartbeat, espace disque (§11.7) | P1 | Oui (S4) ; Sentry selon la question 7 |
| Revue OWASP Top 10 avant l'ouverture (§9.3, §12) | P1 | Oui (S7) ; test d'intrusion tiers selon la question 6 |
| Accessibilité WCAG 2.1 AA « vérifiée en intégration continue » (§7.4, §10.3) | P1 | Oui (S8) : audit axe promis en L3, jamais ajouté |
| Test de charge, 200 utilisateurs, p95 < 500 ms (§12, §14.4, R14) | P1 | Oui (S5, S6) |
| Couverture ≥ 80 % sur la logique critique (§12) | P1 | Oui (S9) : mesurée, puis seuil en CI |
| Recette des parcours, démos A à I sur o2switch (bilans L1 à L8) | P1 | Oui (S10, S12) |
| Formation, documentation d'exploitation remise (§14.1, A5) | P1 | Oui (S11) |
| Mise en production : check-list A5 | P1 | Oui (S13) |
| Anti-robots sur les formulaires publics (§9.3) | — | Selon la question 8 (non proposé) |
| Antivirus des dépôts (§9.3, §11.2) | — | Selon la question 9 (vérification, pas d'intégration proposée) |

**Écarts avec l'étude, à valider** :

- la copie hors hébergement est **rapatriée** par l'opérateur (`deploy/pull-backups.sh`, SSH
  et `rsync` depuis son poste ou son serveur), au lieu d'être **poussée** par l'hébergement
  vers un stockage tiers : aucune clé d'un tiers n'est stockée sur le serveur (S2, question 2) ;
- outil de charge : **Locust** (Python, dépendance de développement, scénarios dans le dépôt)
  plutôt que k6, qu'A6 cite (binaire Go à installer à part) ; il ne tourne jamais sur le
  serveur (S5) ;
- ZAP en **analyse passive** seulement (« baseline »), lancée par l'opérateur contre la
  plateforme avant toute donnée réelle, et non en CI (S7) ;
- Lighthouse : mesure ponctuelle des pages publiques, consignée dans le bilan, pas en CI ;
- la charge du lot dépasse l'estimation de l'étude, comme les lots précédents (§8).

## 2. Décisions (validées)

| # | Sujet | Proposition |
|---|---|---|
| S1 | Organisation du lot | **Deux volets.** *Dans le dépôt* : chaque outil (sauvegarde, restauration, charge, analyse, audit, données de démonstration) est écrit, testé en local sur MariaDB et en CI, et documenté avec la commande exacte à lancer. *Sur l'hébergement* : l'opérateur exécute ces commandes dans l'ordre d'un **runbook** (`docs/L9-runbook-o2switch.md`) et colle leurs sorties dans la fiche `docs/L1-verifications-o2switch.md` et dans le bilan ; chaque sortie est lisible, sans secret, et se termine par un verdict. Aucun secret de production ne transite par cette session ni par le dépôt (règle n° 11). |
| S2 | Sauvegarde | Commande **`backup_db`** (`LockedCommand`, idempotente, battement de cœur `CronHeartbeat`) : <br>— `mariadb-dump --single-transaction --quick --routines --default-character-set=utf8mb4`, avec les identifiants dans un fichier d'options temporaire en mode 0600, **jamais sur la ligne de commande** (visible par `ps`), compressée en flux (`gzip`), écrite d'abord sous un nom temporaire, puis renommée ; <br>— **manifeste** JSON à côté : date, version de l'application, dernière migration de chaque application, taille et empreinte SHA-256 du dump, liste des fichiers privés et publics attendus (nom de stockage, taille, empreinte lue en base), pour vérifier la complétude d'une restauration ; <br>— rotation **7 quotidiennes, 4 hebdomadaires, 3 mensuelles** dans `gestconf-private/backups/` (hors racine web, droits 0700) ; <br>— ligne de cron quotidienne (nuit) ; alerte à l'opérateur en cas d'échec (`alerts.py`). <br>Les fichiers privés ne sont pas recopiés sur le même disque (cela ne protège pas d'une perte de l'hébergement) : ils sont rapatriés avec les dumps (S3). Sur `mysqldump` absent, la commande échoue avec un message clair (V18 de la fiche). |
| S3 | Copie hors hébergement et restauration | **`deploy/pull-backups.sh`** (poste ou serveur de l'opérateur, cron de son côté) : `rsync` en SSH des dumps et des dossiers de fichiers privés et publics (incrémental : les fichiers déposés ne changent jamais de contenu), vérification des empreintes du dernier manifeste, rapport. **`deploy/restore.sh`** : restauration d'un dump et des fichiers dans une base et un dossier **vides** (refus si la base cible contient des tables), puis `migrate --check`, `check_integrity`, comparaison avec le manifeste. **Test de restauration documenté** (§11.6) : en local à partir d'une copie rapatriée, puis sur l'hébergement dans une seconde base si l'offre le permet (M08), chronométré pour le RTO de 4 heures. **`deploy.sh` sauvegarde avant `migrate`** (promis en L1, jamais fait), et s'arrête si la sauvegarde échoue. Retour arrière documenté : redéployer le commit précédent et restaurer la sauvegarde d'avant migration. |
| S4 | Supervision | `/v1/health` : âge de la dernière sauvegarde réussie (`backup` : ok, en retard au-delà de 26 heures, inconnue), sans autre détail public. `check_integrity` signale aussi l'espace disque libre sous un seuil (`GESTCONF_DISK_FREE_MIN_MB`), la taille de la base et une sauvegarde en retard, par alerte e-mail (D17). Surveillance externe (`/` et `/api/v1/health`, toutes les 5 minutes) par un service gratuit (UptimeRobot, Better Stack…) que l'opérateur configure ; procédure écrite dans le runbook. Remontée d'erreurs : **e-mail minimal** maintenu (D17) ; Sentry seulement sur décision (question 7), car il transfère des données personnelles à un tiers. |
| S5 | Test de charge | **Locust** (dépendance de développement ; scénarios versionnés dans `loadtest/`) : <br>— *visiteurs* : pages pré-rendues du portail, bandeau, programme (pic d'ouverture des inscriptions : 200 visiteurs) ; <br>— *auteurs* : liste et brouillon de soumission, dépôt de PDF, envoi (pic de clôture de l'appel) ; <br>— *relecteurs* : liste des évaluations, enregistrement d'une évaluation ; <br>— *participants* : devis, inscription, « Mon inscription » ; <br>— *comité* : listes paginées de 600 soumissions et de 1 500 inscriptions, tableau de bord. <br>Sessions **pré-établies** pour les comptes de charge (commande `loadtest_sessions`, fichier de cookies hors dépôt), sinon les limites de débit par IP de la connexion (allauth) arrêteraient le test au bout de quelques secondes ; le coût de PBKDF2 (R14) est mesuré à part, par quelques connexions réelles chronométrées. **Cibles** (§12) : 200 utilisateurs simultanés, p95 < 500 ms hors exports et PDF, moins de 1 % d'erreurs ; montée progressive, palier de 10 minutes. Lancé depuis le poste de l'opérateur, **jamais** depuis le serveur ; o2switch prévenu au préalable (question 5). |
| S6 | Données de volume | Commande **`seed_volume`** : une édition dédiée (`LOADTEST-…`) avec 600 soumissions, 100 relecteurs, 1 500 inscrits et leurs évaluations, adresses en `.invalid`, **aucun e-mail** (la file refuse le domaine réservé `.invalid`, test). Garde-fous : refus si l'édition existe déjà, et refus en production si la base contient le moindre compte qui n'est pas de charge ou de démonstration ; commande **`purge_volume`**, journalisée. Elle sert aussi aux **tests de nombre de requêtes** : les listes chaudes (soumissions, évaluations, inscriptions, programme, rapports) gardent un nombre de requêtes constant quand le volume décuple (`django_assert_max_num_queries`), cinq endpoints seulement le vérifiant aujourd'hui. Le test de charge sur l'hébergement a lieu **avant toute donnée réelle** (D18) ; la base est ensuite purgée, ou réinstallée. |
| S7 | Revue de sécurité | Document **`docs/L9-revue-securite.md`** : chaque catégorie de l'OWASP Top 10 (2021) et une sélection de contrôles de l'ASVS niveau 2 (authentification, session, contrôle d'accès, validation, fichiers, journalisation, configuration), avec la preuve (test, fichier, commande) et le statut ; chaque constat est corrigé dans le lot ou accepté par écrit. **Automatisé** : règles `S` de `ruff` (flake8-bandit) en CI, exceptions justifiées une à une ; **ZAP baseline** (passif) lancé par l'opérateur. **Correctifs déjà repérés** : <br>— les en-têtes de sécurité du `.htaccess` sont dans `<IfModule mod_headers.c>` : sans le module, ils disparaissent sans bruit ; les tests de fumée vérifient désormais HSTS, `X-Frame-Options`, `Referrer-Policy`, `nosniff` et l'en-tête CSP, et échouent sinon ; <br>— la CSP de l'en-tête n'a pas de `default-src` : `default-src 'self'` ajouté, après vérification des pages ; <br>— redirection HTTP vers HTTPS : le commentaire de `prod.py` (« par le `.htaccess` ») contredit le README (« par cPanel ») ; une seule voie retenue, vérifiée par les tests de fumée (301 vers `https://`) ; <br>— rotation des secrets (`SECRET_KEY`, clés 2FA, clés de signature, clés de paiement) documentée. |
| S8 | Accessibilité | **axe-core** dans le parcours de bout en bout (`@axe-core/playwright`) : audit des pages clés de chaque étape (accueil et programme du portail, connexion, formulaire de soumission, « Mon inscription », tableau de bord de la gestion, formulaire d'évaluation, planificateur, accueil du jour J, rapports) ; échec sur toute violation **sérieuse ou critique** des règles WCAG 2.1 A et AA. Les violations trouvées sont corrigées dans le lot. L'audit ne remplace pas un contrôle manuel au clavier et au lecteur d'écran (NVDA, VoiceOver), fait sur les parcours de la recette et consigné. |
| S9 | Couverture | Couverture mesurée par module ; seuil **80 %** imposé en CI (`fail_under`) sur la logique critique : `reviews` (notation, décisions), `program` (planification, conflits), `payments`, `registrations` (tarifs, workflow), `submissions` (workflow). Les modules sous le seuil reçoivent des tests ciblés. |
| S10 | Recette | **Édition de démonstration** par une commande `seed_demo` (même garde-fous que S6) : un compte par rôle (Chair, CS, relecteurs, CO de chaque fonction, bénévole, signataire, intervenant invité, auteurs, participants), secrets TOTP affichés une seule fois. **Cahier de recette** `docs/L9-recette.md` : les démos A à I des bilans, découpées en scénarios numérotés (préalable, étapes, résultat attendu, règle de gestion vérifiée), à cocher sur l'hébergement ; une anomalie = une ligne (gravité, correctif, commit). La recette fonctionnelle est faite par le commanditaire ; je prépare, j'assiste et je corrige. |
| S11 | Formation et documentation | **Guide d'exploitation** (`docs/exploitation.md`, qui reprend et complète `deploy/README.md`) : déploiement, cron, sauvegarde, restauration, supervision, incidents, rotation des secrets, publication du portail. **Guides par rôle** (`docs/guides/` : présidence et administration, comité scientifique, relecteur, comité d'organisation, bénévole et accueil), courts et illustrés, renvoyant aux 53 fiches d'aide de la gestion. **Aide du portail** pour les auteurs et les participants : page « Aide » (FAQ) du CMS de L2, dont je propose le texte. **Support de formation** : déroulé d'atelier sur l'édition de démonstration (une demi-journée par public). |
| S12 | Premier déploiement réel | Ordre du runbook : `check-o2switch.sh` (V00 à V29) et contrôles manuels (M01 à M10) consignés dans la fiche ; décisions H-1 à H-11 ; déploiement (`deploy.sh`), tests de fumée ; cron (dont `backup_db`), surveillé 48 heures ; sauvegarde, copie rapatriée, **restauration testée** ; `seed_demo` et démos A à I ; `seed_volume`, test de charge, `purge_volume` ; ZAP baseline ; check-list A5. Chaque étape a son critère de passage ; un échec arrête la suite. |
| S13 | Mise en production | `docs/L9-mise-en-production.md` : la check-list A5, chaque ligne avec sa preuve (sortie de commande, capture, date) ; les points qui dépendent du commanditaire (pages légales, SPF/DKIM/DMARC du domaine, clés de paiement de production, paiement réel de petit montant) sont listés avec leur responsable. L'**ouverture de l'appel** reste une décision du commanditaire, prise sur cette check-list. |
| S14 | Pages légales | Mentions légales, politique de confidentialité, cookies : pages du CMS (L2). Je propose une **trame** fondée sur ce que la plateforme traite réellement (registre des traitements de L1, durées de conservation, sous-traitants : hébergeur, e-mails, paiement) ; le texte définitif revient au commanditaire (loi n° 2013-450, ARTCI ; RGPD si des participants européens sont concernés). |
| S15 | Correctifs | Les défauts trouvés par la recette, la revue, l'audit ou la charge sont corrigés dans le lot, chacun avec un test. Aucune fonction nouvelle n'entre en L9 ; une demande de fonction issue de la recette est notée pour un lot ultérieur. |
| S16 | Ordre | L9.0 vérifications ; L9.1 sauvegarde et restauration ; L9.2 supervision et en-têtes ; L9.3 données de volume et requêtes ; L9.4 test de charge ; L9.5 revue de sécurité ; L9.6 accessibilité et couverture ; L9.7 recette, démonstration et documentation ; L9.8 sur l'hébergement (runbook) ; L9.9 bilan, étude §25, `CLAUDE.md`. |

### 2.1 Validation (12 octobre 2026) et hypothèses retenues

Le commanditaire a demandé de « terminer tout ce qui reste », sans répondre aux questions du
§10. Le plan est donc validé tel que proposé, et ses propositions s'appliquent comme
hypothèses révisables :

| Question (§10) | Hypothèse retenue |
|---|---|
| 1. Opérateur | Inconnu : le volet du dépôt avance seul ; L9.8 attend un opérateur désigné |
| 2. Copie hors hébergement | Rapatriement par `pull-backups.sh` chez l'opérateur ; pas de chiffrement propre à la copie (disque chiffré conseillé) |
| 3. Reprise | Perte maximale 24 h, rétablissement sous 4 h |
| 4. Recette | Sur la production avant toute donnée réelle, puis base réinitialisée |
| 5. Charge | 200 utilisateurs simultanés ; o2switch prévenu avant le test et ZAP |
| 6. Sécurité | Revue interne (OWASP Top 10, ASVS, ZAP passif) |
| 7. Erreurs | E-mail minimal aux opérateurs (D17), pas de Sentry |
| 8. Anti-robots | Non : limites de débit existantes |
| 9. Antivirus | Absence acceptée si o2switch n'en fournit pas (à vérifier sur place) |
| 10. Formation | Guides écrits et déroulé d'atelier ; dates et publics à fixer par le commanditaire |
| 11. Déploiement continu | Non : `deploy.sh` lancé à la main |
| 12. Pages légales | Trame proposée ; texte définitif au commanditaire |
| 13. Bundle du portail | Seuil d'avertissement relevé à 375 ko, l'écart venant de fonctions voulues |

## 3. Modèle de données

Aucun modèle nouveau. `CronHeartbeat` (L1) reçoit les passages de `backup_db`. Les éditions
de charge et de démonstration sont des éditions ordinaires, marquées par leur code
(`LOADTEST-…`, `DEMO-…`) et par un indicateur posé par les commandes, que les garde-fous
lisent.

## 4. Commandes, scripts et API

- **Commandes** (`manage.py`) : `backup_db`, `seed_demo`, `seed_volume`, `purge_volume`,
  `loadtest_sessions` ; toutes sauf `backup_db` exigent l'option `--confirm-fictitious` et
  sont refusées dès que la base contient un compte réel (S6).
- **Scripts** (`deploy/`) : `pull-backups.sh`, `restore.sh` ; `deploy.sh` (sauvegarde avant
  `migrate`) ; `smoke-test.sh` (en-têtes de sécurité, redirection HTTPS) ; `cron.sh`
  (`backup_db`).
- **Charge** : `loadtest/locustfile.py` et ses scénarios, `loadtest/README.md` (commande
  exacte, paliers, lecture du rapport).
- **API** : `/v1/health` gagne l'état de la sauvegarde (S4) ; rien d'autre.

## 5. Frontend

- Audit axe dans le parcours de bout en bout (S8) ; correctifs d'accessibilité.
- Page « Aide » du portail (contenu du CMS, aucun code) ; liens vers les guides.
- Aucun écran nouveau dans la gestion.

## 6. Sécurité

- Les commandes de données fictives ne peuvent pas toucher une base réelle (garde-fous de S6,
  testés), et leurs comptes ne reçoivent aucun e-mail.
- `backup_db` ne met aucun mot de passe sur une ligne de commande ; les sauvegardes sont hors
  racine web, en 0700 ; elles contiennent des données personnelles : leur copie rapatriée
  hérite des obligations de conservation (§12), et leur effacement suit la rotation.
- Les sessions de charge sont créées pour les seuls comptes de charge, et expirent avec la
  purge.
- Le test de charge et ZAP visent une plateforme **sans donnée réelle**, après accord
  d'o2switch (question 5).
- Chaque constat de la revue est corrigé ou accepté par écrit (S7).

## 7. Tests

- **Sauvegarde et restauration** : dump puis restauration dans une base vide sous MariaDB
  (CI), manifeste vérifié, rotation (dates simulées), refus d'une base cible non vide,
  identifiants absents de la ligne de commande, échec propre sans `mysqldump`.
- **Garde-fous** : `seed_volume`, `seed_demo` et `loadtest_sessions` refusés sur une base qui
  contient un compte réel ; aucun e-mail vers `.invalid`.
- **Requêtes** : nombre constant sur les listes chaudes quand le volume décuple.
- **Supervision** : état de la sauvegarde dans `/v1/health` ; alertes de `check_integrity`.
- **Fumée** : en-têtes de sécurité et redirection HTTPS (tests des scripts, comme en L1).
- **Accessibilité** : axe dans le parcours ; **sécurité** : `ruff` règles `S` ; **couverture** :
  seuil en CI.
- **Charge** : un essai court de Locust contre la pile locale du parcours (CI ou local), pour
  que les scénarios ne pourrissent pas.

## 8. Étapes

| Étape | Contenu | Critère de fin | Charge |
|---|---|---|---|
| L9.0 | Vérifications : `mariadb-dump` et options sur MariaDB 10.11, durée d'un dump et d'une restauration pour le volume de §12, Locust (licence, installation, sessions), `@axe-core/playwright` avec la version de Playwright, bruit des règles `S` de `ruff`, couverture actuelle par module, ZAP baseline en local | Choix consignés | 1 – 1,5 |
| L9.1 | `backup_db`, rotation, manifeste ; `pull-backups.sh`, `restore.sh` ; sauvegarde avant `migrate` dans `deploy.sh` ; cron ; restauration testée en local | Tests au vert, restauration locale chronométrée | 2 – 2,5 |
| L9.2 | Supervision (`/health`, alertes de `check_integrity`) ; tests de fumée (en-têtes, HTTPS) ; `default-src` | Tests au vert | 1 – 1,5 |
| L9.3 | `seed_volume`, `purge_volume`, garde-fous ; tests de nombre de requêtes ; correctifs N+1 | Tests au vert | 1,5 – 2 |
| L9.4 | Scénarios Locust, `loadtest_sessions`, essai local sur MariaDB (référence) | Rapport local | 1,5 – 2 |
| L9.5 | Revue OWASP et ASVS, règles `S` de `ruff`, ZAP local, correctifs, rotation des secrets | Aucun constat élevé ouvert | 2 – 2,5 |
| L9.6 | Audit axe dans le parcours, correctifs ; couverture et seuil en CI | Audit et seuil au vert | 1,5 – 2 |
| L9.7 | `seed_demo`, cahier de recette, guides par rôle, guide d'exploitation, aide du portail, trame des pages légales, runbook | Documents relus | 1,5 – 2 |
| L9.8 | Sur l'hébergement, avec l'opérateur : runbook complet (S12) | Démo J | 4 – 6 |
| L9.9 | Bilan, étude (§25), `CLAUDE.md` | — | 0,5 |
| **Total L9** | | | **16,5 – 22,5** |

L9.0 à L9.7 et L9.9 se font dans le dépôt et peuvent avancer sans l'hébergement ; L9.8
attend l'opérateur. Si l'accès à o2switch tarde, les étapes du dépôt sont livrées et
poussées, et L9.8 reste ouverte.

## 9. Risques et hypothèses non vérifiées

- **Accès à l'hébergement** : sans opérateur disponible, le lot ne peut pas être livré
  (démo J). C'est le premier risque du projet depuis L1 : aucune des huit démos n'a été
  jouée sur o2switch.
- **Limites de CloudLinux** (processus, mémoire, entrées et sorties) inconnues (M07) : le test
  de charge peut échouer bien avant 200 utilisateurs. Repli de l'étude (§14.4) : VPS, ce qui
  remettrait en cause plusieurs choix d'exploitation.
- **Conditions d'o2switch** : un test de charge ou une analyse ZAP non annoncés peuvent être
  pris pour une attaque (blocage d'IP, pare-feu applicatif). À annoncer au support
  (question 5).
- **`mysqldump`** et un second schéma de base (pour la restauration sur place) : présence et
  droits **non vérifiés** (V18, M08).
- **Rapatriement** : suppose un poste ou un serveur de l'opérateur allumé chaque jour, avec
  l'accès SSH ; sinon, la copie hors hébergement dépend des sauvegardes d'o2switch (M06),
  dont la restauration n'est pas sous notre contrôle.
- **Taille des fichiers privés** : 600 soumissions avec leurs versions peuvent peser plusieurs
  gigaoctets ; le premier rapatriement est long, les suivants incrémentaux. Quota disque de
  l'offre **non vérifié**.
- **Accessibilité** : l'audit automatique ne trouve qu'une partie des défauts ; le contrôle
  manuel reste indispensable.
- **Charge du lot** : comme L2 à L8, elle dépasse l'estimation de l'étude.

## 10. Questions au commanditaire

1. **Opérateur** : qui exécute le runbook sur o2switch (vous, un prestataire) et à partir de
   quand ? Je n'ai pas accès à l'hébergement depuis cette session, et c'est voulu : les clés
   restent chez vous.
2. **Copie hors hébergement** : rapatriement par `pull-backups.sh` sur votre poste ou votre
   serveur (proposé), stockage objet chez un tiers (clé sur le serveur), ou sauvegardes
   d'o2switch seules ? Faut-il chiffrer la copie rapatriée ?
3. **Reprise** : perte maximale de 24 heures et rétablissement sous 4 heures (étude §11.6) :
   validés ?
4. **Recette** : un sous-domaine de recette (`recette.…`) est-il autorisé par l'offre ? Sinon,
   la recette et le test de charge se font sur la production **avant toute donnée réelle**,
   puis la base est réinitialisée (proposé).
5. **Test de charge** : 200 utilisateurs simultanés reste-t-il la cible (Q13, volumes
   attendus) ? Acceptez-vous de prévenir o2switch avant le test et l'analyse ZAP ?
6. **Sécurité** : revue interne (OWASP Top 10, ASVS, ZAP passif ; proposée) ou test
   d'intrusion par un prestataire (coût, délai) ?
7. **Erreurs** : e-mail minimal aux opérateurs (actuel) ou Sentry (tiers, données
   personnelles, accord à formaliser) ?
8. **Anti-robots** (Turnstile, hCaptcha) sur l'inscription : non (proposé : limites de débit
   existantes, pas de script tiers ni de cookie), ou oui ?
9. **Antivirus** des PDF déposés : accepter son absence si o2switch n'en fournit pas (type
   vérifié par contenu, PDF réécrit en double aveugle, téléchargement authentifié), ou
   l'exiger ?
10. **Formation** : publics (comité, relecteurs, bénévoles), format (atelier, vidéo, guides),
    langue, dates ?
11. **Déploiement continu** : rester sur `deploy.sh` lancé à la main (proposé), ou déployer
    depuis la CI (clé SSH de production confiée à GitHub) ?
12. **Pages légales** : qui rédige le texte définitif ? La trame proposée (S14) vous
    convient-elle comme point de départ ?
13. **Bundle du portail** : 369,8 ko pour un avertissement à 365 ko depuis L5 ; relever le
    seuil à 375 ko (proposé, l'écart venant de fonctions voulues), ou chercher à réduire ?

## 11. Bilan de L9.0 (12 octobre 2026)

**Validation** : consignée au §2.1 (demande du commanditaire du 12 octobre 2026 ; questions du
§10 sans réponse, propositions retenues comme hypothèses).

**Sauvegarde par `mariadb-dump`** (MariaDB 10.11.14 locale) :

- vérifiée avec un compte **limité à sa base** (aucun privilège global, comme sur un
  hébergement mutualisé) : `--single-transaction --quick --hex-blob --no-tablespaces
  --skip-lock-tables --default-character-set=utf8mb4` passe sans `PROCESS` ni `LOCK TABLES` ;
- identifiants dans un fichier d'options passé par `--defaults-extra-file` (toujours la
  **première** option), jamais sur la ligne de commande ;
- restauration dans une base vide par le client `mariadb`, puis `migrate --check` : conforme ;
  `createcachetable` recrée les deux tables du cache, exclues du dump ;
- la ligne finale `-- Dump completed` permet de reconnaître un dump tronqué ;
- **piège vérifié** : `mariadb-dump` récent (10.5.25, 10.6.18, 10.11.8 et suivants) écrit en
  première ligne `/*M!999999\- enable the sandbox mode */`, qu'un client plus ancien ou celui
  de MySQL refuse : restaurer avec un client `mariadb` récent ;
- **piège vérifié** : le `mysqldump` de MySQL 8 (celui des runners Ubuntu de la CI)
  interroge `COLUMN_STATISTICS`, absente de MariaDB : `--column-statistics=0` quand l'outil
  n'est pas celui de MariaDB ; la CI installe le client MariaDB pour le test de sauvegarde
  réelle ;
- durées locales sur la base de développement (98 tables) : dump 0,7 s, restauration 0,5 s ;
  mesures au volume de l'étude (§12) avec `seed_volume` (L9.3).

**Locust** : 2.46.7, licence MIT, 40 paquets en roues seules pour Python 3.12 (dont
`gevent`). **Précision de S5** : fichier verrouillé à part (`requirements/loadtest.in` et
`.txt`), installé dans un environnement séparé par l'opérateur ; ni la CI du backend ni
l'hébergement n'en dépendent.

**axe** : `@axe-core/playwright` 4.13.0 (licence MPL-2.0, dépendance de développement du
front, jamais livrée), compatible avec Playwright 1.63 du dépôt.

**`ruff`, règles `S` (bandit)** : **déjà actives depuis L1** (correction de S7 et du §8,
qui les annonçaient comme nouvelles) ; aucun constat ouvert. Exceptions hors tests, toutes
justifiées sur leur ligne : deux noms de clé pris pour des mots de passe (`S105`), deux
requêtes sur un nom de table cité par `quote_name` (`S608`), la clé de test des réglages de
test. Les appels de `subprocess` ajoutés en L9.1 suivent la même règle.

**Couverture** : mesurée par module avec la suite complète ; résultats et seuil en L9.6
(**précision** : la mesure rejoint l'étape qui pose le seuil).

**ZAP** : pas de démon Docker dans cet environnement ; Java 21 est présent. **Précision de
S7** : essai du paquet multiplateforme de ZAP avec un plan d'automatisation passif en L9.5 ;
sur le poste de l'opérateur, l'image `zaproxy/zap-stable` et `zap-baseline.py` suffisent.

**CSP, `default-src`** : **écarté** (précision de S7). L'en-tête du `.htaccess` ne porte pas
`script-src`, que la balise `<meta>` de chaque page fixe par empreintes (`inject-csp.mjs`) ;
avec `default-src 'self'` dans l'en-tête, le navigateur l'appliquerait aussi aux scripts et
bloquerait les scripts en ligne autorisés par la balise : tout le portail cesserait de
fonctionner. L'en-tête énumère déjà chaque autre directive de chargement ; un test le
vérifiera (L9.2).

**Critère de fin** (« Choix consignés ») : atteint.

## 12. Bilan de L9.1 (12 octobre 2026)

**Sauvegarde** (S2 ; `apps/core/backups.py`, commande `backup_db`) :

- `LockedCommand` (verrou, battement de cœur, alerte aux opérateurs en cas d'échec) ; cron
  quotidien à 2 h 07 (`deploy/cron.sh`, liste fermée étendue) ;
- dump MariaDB en flux compressé, sous un nom temporaire puis renommé, en 0600, dans
  `GESTCONF_BACKUP_DIR` (défaut `var/backups`, créé en 0700) ; outil détecté (`mariadb-dump`,
  sinon `mysqldump`, avec `--column-statistics=0` si ce n'est pas celui de MariaDB) ;
- tables du cache exclues ; **précision de S2** : `django_session` est sauvegardée **sans ses
  lignes** (second appel en `--no-data`) : une session est un titre d'accès, une sauvegarde
  volée n'en livre aucune, et la table existe après restauration ;
- dump refusé s'il échoue ou s'il est tronqué (ligne finale absente) : aucun fichier laissé ;
- **manifeste** : date, version, dernière migration de chaque application, taille et
  empreinte SHA-256 du dump, tables exclues, inventaire des fichiers déposés. **Précision de
  S2** : l'inventaire liste les fichiers présents sur le disque (chemin relatif, taille), sans
  empreinte : en calculer chaque nuit sur des gigaoctets coûterait cher, et la cohérence
  entre la base et les fichiers (empreintes comprises, quand le modèle en garde une) est déjà
  contrôlée par `check_integrity` après restauration ;
- rotation : 7 quotidiennes, 4 hebdomadaires, 3 mensuelles (`GESTCONF_BACKUP_KEEP_*`),
  restes d'une exécution interrompue supprimés, autres fichiers du dossier jamais touchés ;
- SQLite (développement) : dump SQL par `iterdump()`. **Défaut évité** : l'API `backup()` de
  `sqlite3` attendait sans fin, dans les tests, le verrou d'une base en mémoire à cache
  partagé tenue par la transaction du test ;
- premier déploiement : base vide, `backup_db` ne fait rien et le dit ;
- journal `backup.created`.

**Restauration** (S3 ; commande `restore_db`, script `deploy/restore.sh`) :

- empreinte du dump comparée au manifeste (copie altérée refusée) ; base cible **vide**
  exigée (refus sinon, vérifié par une connexion PyMySQL) ; chargement par le client
  `mariadb` ;
- fichiers rapatriés recopiés dans des dossiers vides, puis comparés au manifeste (absents,
  tailles différentes) ; tables du cache recréées ; migrations en attente **signalées**, jamais
  appliquées d'office ; journal `backup.restored` ; puis `check_integrity` ;
- `restore.sh` fonctionne sur le poste de l'opérateur (dépôt) comme sur l'hébergement (livré
  par `deploy.sh`) et affiche la durée, à comparer aux 4 heures de l'étude.

**Copie hors hébergement** (`deploy/pull-backups.sh`, chez l'opérateur) : dumps copiés sans
suppression ; fichiers en instantanés datés liés par `--link-dest` (un effacement sur le
serveur n'atteint pas les copies prises), le dernier désigné par `latest` ; conservation
locale de 30 jours ; empreinte du dernier dump et complétude de l'instantané vérifiées.
Essayé en local avec un `ssh` simulé (`RSYNC_RSH`) : deux passages, mêmes inodes d'un
instantané à l'autre, vérification conforme ; puis `restore.sh` à partir de cette copie :
base et fichiers restaurés, `check_integrity` sans anomalie, en 4 secondes.

**Déploiement** : `backup_db --required` avant `migrate` (promis en L1, jamais fait) : si une
sauvegarde du cron tourne au même moment, le déploiement s'arrête au lieu de migrer sans
sauvegarde fraîche (point d'extension `lock_busy` ajouté à `LockedCommand`).

**Défaut trouvé, antérieur à L9 et grave** : `backend/var/` est ignoré par git, donc absent de
l'archive envoyée ; le `rsync --delete` de `deploy.sh` l'aurait **effacé à chaque
déploiement**, emportant les fichiers déposés (emplacement par défaut de
`GESTCONF_FILES_DIR`) et désormais les sauvegardes. Aucune donnée réelle n'existait encore.
`--exclude '/var/'` ajouté, avec un test.

**CI** : le job du backend installe le client MariaDB (`mariadb-dump`, `mariadb`) pour le test
de sauvegarde réelle, qui charge le dump dans une base neuve et vérifie une ligne témoin et
la table des sessions vide.

**Exploitation** : `deploy/README.md`, section « Sauvegarde et restauration » (cron, copie,
restauration, test documenté, données personnelles des copies), et retour arrière après une
migration fautive.

**Tests** : `apps/core/tests/test_backups.py` (13 tests : rotation, nettoyage, fichier
d'options, arguments du dump sans mot de passe, sessions en structure seule, client MySQL,
dump en échec ou tronqué, sauvegarde SQLite avec manifeste, battement de cœur et journal,
`--required`, manifeste altéré, recopie et vérification des fichiers, refus hors MariaDB, base
vide ; sous MariaDB, dump réel puis chargement dans une base neuve et refus d'une base non
vide) ; `tests/test_deploy_scripts.py` (sauvegarde avant `migrate`, `var/` protégé, copie
sans suppression et à instantanés, restauration puis contrôle d'intégrité, cron) ;
`shellcheck` des scripts.

**Critère de fin** (« Tests au vert, restauration locale chronométrée ») : atteint.

## 13. Bilan de L9.2 (12 octobre 2026)

**Supervision** (S4) :

- `/v1/health` gagne `backup` (`ok`, `late`, `unknown`), lu dans le battement de cœur de
  `backup_db` : `late` au-delà de `GESTCONF_BACKUP_MAX_AGE_HOURS` (26 h). Comme `jobs`, il ne
  rend pas l'API indisponible ; aucune autre information n'est exposée ;
- `check_integrity` signale par e-mail aux opérateurs (D17) une sauvegarde absente ou en
  retard (`core.backup_age`) et un espace libre sous `GESTCONF_DISK_FREE_MIN_MB` (1 024 Mio)
  sur le disque des fichiers ou des sauvegardes (`core.disk_space`). **Limite** : la mesure
  est celle du système de fichiers ; un quota propre au compte (CloudLinux) n'y apparaît pas
  (**non vérifié**, M07) ;
- ces deux contrôles dépendent de `GESTCONF_STORAGE_MONITORING` (actif par défaut, désactivé
  dans les réglages de test sauf pour leurs propres tests) ;
- la surveillance externe (disponibilité de `/` et de `/api/v1/health`) reste à configurer par
  l'opérateur (runbook, L9.7).

**Tests de fumée** (S7) :

- en-têtes `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` et, en HTTPS,
  `Strict-Transport-Security` : ils sont dans `<IfModule mod_headers.c>` et disparaîtraient
  sans bruit si le module manquait ;
- redirection `http://` vers `https://` (301 ou 308) ;
- état de la sauvegarde : `ok` exigé, `unknown` signalé sans échec (premier déploiement).

**Redirection HTTPS** : une seule voie, **cPanel** (« Forcer la redirection HTTPS »), comme le
dit le README ; le commentaire de `config/settings/prod.py`, qui parlait du `.htaccess`, est
corrigé.

**CSP** : `default-src` écarté (bilan de L9.0) ; un test vérifie que l'en-tête du portail
énumère chaque directive de chargement hors scripts, sans `default-src` ni `script-src`.

**Schéma et client** : `Health.backup` (énumération `JobsStatus`), schéma validé sous
MariaDB, client TypeScript régénéré ; vérification des types des trois projets du front.

**Tests** : `apps/core/tests/test_monitoring.py` (sauvegarde absente, en retard, à jour,
surveillance désactivée ; espace disque bas sur un dossier encore absent) ;
`test_health.py` (état de la sauvegarde) ; `test_deploy_scripts.py` (en-têtes et redirection
dans les tests de fumée, directives de la CSP) ; `shellcheck`.

**Critère de fin** (« Tests au vert ») : atteint.

## 14. Bilan de L9.3 (12 octobre 2026)

**Données de volume** (S6 ; application `apps/qa`, commande `seed_volume`) :

- une conférence fictive dédiée (`gestconf-fictif`) et deux éditions : `FICTIFEVAL` (appel
  clos, 600 soumissions en évaluation, 100 relecteurs, 1 200 affectations, 800 évaluations
  envoyées) et `FICTIFAPPEL` (appel ouvert, 300 brouillons, 1 500 inscrits dont 1 000 payés
  par virement enregistré, factures et pro forma émises), édition courante de l'API publique
  pendant le test ;
- **tout passe par les services métier** : statuts écrits par les workflows (règle n° 4),
  règles de gestion appliquées, pièces numérotées ; seuls les comptes sont créés en masse,
  avec un hachage de mot de passe unique ; mot de passe et secret TOTP tirés au hasard et
  affichés une seule fois ; commande journalisée (`qa.volume_seeded`) ;
- **aucun e-mail** : adresses en `@fictif.invalid` (domaine réservé, RFC 2606) ; la tâche
  d'envoi annule tout message vers `.invalid` (test) ;
- **garde-fous** : `--confirm-fictitious` exigé ; refus dès que la base contient un compte
  hors du domaine fictif, une soumission ou une inscription hors de la conférence fictive
  (les opérateurs n'ont pas besoin de compte, D1) ; refus si la conférence fictive existe ;
- durée au volume de l'étude, MariaDB 10.11 locale : **528 s** (dont la génération des
  2 500 pièces PDF ; 179 s sans elles) ; base de 29 Mio, 2 500 fichiers privés (60 Mio).

**Précisions de S6** :

- **pas de `purge_volume`** : une purge supprimerait des pièces comptables numérotées sans
  trou et en ajout seul (RG-14) et des entrées du journal, et se heurterait aux clés
  `RESTRICT`. Le retour à l'état antérieur se fait par la **sauvegarde prise juste avant**
  (`backup_db`), restaurée dans une base neuve (`deploy/restore.sh`), ou par une base
  réinstallée ; le runbook (L9.7) le décrit ;
- les éditions sont repérées par leur conférence dédiée et non par un indicateur en base :
  **aucun modèle nouveau** (§3).

**Sauvegarde et restauration au volume** (S2, S3) : `backup_db` en **2,0 s** (dump compressé
de 1,2 Mio, manifeste de 2 500 fichiers) ; `deploy/restore.sh` (dump, fichiers, comparaison
au manifeste, tables du cache, `check_integrity`) en **6 s** dans une base vide, sans
anomalie. L'objectif de rétablissement de 4 heures (§11.6) est loin ; la mesure sur
l'hébergement reste à faire (L9.8).

**Nombre de requêtes** (`tests/test_query_counts.py`, données de `seed_volume` à petite
échelle) : les listes paginées (soumissions, évaluations par soumission, inscriptions,
paiements, pièces) font le même nombre de requêtes pour 2 et pour 100 lignes ; les vues non
paginées (affectations du relecteur, avancement, classement, statistiques, rapports,
tableau de bord financier, liste hors ligne de l'accueil) restent sous un plafond inférieur
au nombre de lignes lues ; le tableau du planificateur garde le même nombre de requêtes
quand le programme triple (`apps/program/tests/test_api.py`).

**Correctifs N+1** :

- **classement** (`ranking`) : trois requêtes par soumission (77 pour 24 soumissions ;
  1 800 au volume de l'étude) ; notes désormais calculées en une fois (`summaries`), sans
  profil des relecteurs ni notes par critère, et sans les colonnes longues de la
  soumission : **6 requêtes**, et au volume **436 ms → 102 ms** ;
- **export des évaluations** : même calcul par soumission, remplacé par les évaluations déjà
  chargées ;
- **tableau du planificateur** : édition de chaque session et thématique de chaque
  communication placée lues une à une (`program_sessions`) ; jointes à la requête.

**Temps de réponse au volume** (MariaDB locale, réglages de développement, médiane de cinq
appels) : soumissions (page de 100) 55 ms ; évaluations par soumission 42 ms ; avancement
41 ms ; classement 102 ms ; rapport de relecture 170 ms ; affectations d'un relecteur 23 ms ;
inscriptions (page de 100) 57 ms ; pièces 55 ms ; tableau de bord financier 37 ms ; liste
hors ligne de l'accueil (1 000 inscrits confirmés) 227 ms. Mesures locales, **non
transposables** à l'hébergement : le test de charge (L9.4, L9.8) fait foi.

**Critère de fin** (« Tests au vert ») : atteint.

## 15. Bilan de L9.4 (12 octobre 2026)

**Scénarios** (`loadtest/locustfile.py`, S5) : visiteurs (pages pré-rendues, bandeau et
édition courante gardés le temps de leur cache, comme un navigateur ; tarifs), auteurs
(liste, sauvegarde automatique, dépôt d'un PDF valide, vérification puis envoi), relecteurs
(affectations, brouillon d'une évaluation non envoyée, parfois l'envoi), participants (« Mon
inscription », devis), nouveaux inscrits (devis puis commande par virement), comité (une page
au hasard des 600 soumissions et des 1 500 inscriptions, évaluations par soumission,
avancement, classement, statistiques, rapports, tableau de bord financier). **Verdict** à la
fin, code de sortie non nul si l'objectif n'est pas atteint : p95 et taux d'erreurs sur
toutes les requêtes hors « (PDF) » (commande, qui émet la pro forma), rapportées à part.

**Sessions pré-établies** (commande `loadtest_sessions`) : une session par compte fictif,
telle qu'une connexion réussie la laisse (2FA validée pour le comité et les relecteurs),
jeton CSRF compris ; fichier JSON en 0600, jamais écrasé ; `--revoke` supprime les sessions
qu'il liste ; mêmes garde-fous que `seed_volume` ; journalisée. Tests : sessions utilisables
sur une route soumise à la 2FA, écriture protégée par le CSRF, refus sans confirmation ou
sans données de volume, révocation.

**Dépendance** : `locust==2.46.7` verrouillé à empreintes dans
`backend/requirements/loadtest.txt` (37 paquets, compilé sous Linux et Python 3.12), installé
dans un environnement séparé ; ni l'hébergement ni la CI du backend n'en dépendent. **Limite**
: sous Windows, `pywin32` manque au verrou (WSL conseillé). `ruff` vérifie `loadtest/`
(exception `S311` justifiée : tirages non cryptographiques).

**Essai local** (MariaDB 10.11, base au volume de l'étude, serveur de développement) :

- 50 utilisateurs, 2 minutes : deux défauts révélés et corrigés : le **bandeau** était limité
  à 60 requêtes par minute et par adresse IP (55 % de refus) ; un relecteur ne peut pas
  enregistrer de brouillon sur une évaluation **déjà envoyée** (RG-06 : on la renvoie), le
  scénario le faisait ;
- 200 utilisateurs, 3 minutes : **0 erreur** sur 4 548 requêtes ; p95 de 3 s, le serveur de
  développement (un seul processus) plafonnant vers 25 requêtes par seconde : **aucune valeur
  de mesure**, le test sur l'hébergement fait foi (L9.8) ;
- essai identique au job de CI (base neuve réduite, 30 utilisateurs, 90 s) : objectif atteint,
  0 erreur, après correction d'un troisième défaut du scénario (pages tirées au-delà de la
  liste quand le volume est réduit : le comité lit d'abord le nombre de lignes).

**Correctifs** :

- **bandeau** : 600 requêtes par minute et par adresse IP (au lieu de 60) : au lieu de la
  conférence, des centaines de participants sortent par la même adresse et chaque navigateur
  relit le bandeau au plus une fois par minute ; à 60, il aurait disparu au moment où il sert
  le plus ;
- **rapport de relecture** : lecture restreinte aux colonnes utiles (1 200 affectations sans
  les résumés ni les commentaires) : **170 ms → 79 ms** au volume ; test du contenu de la
  section ajouté (aucun ne le vérifiait).

**CI** : job « Scénarios de charge (essai court) » : base MariaDB neuve, `seed_volume` réduit,
`loadtest_sessions`, serveur de développement, 30 utilisateurs pendant 90 s ; il échoue au
moindre taux d'erreurs de 1 % (cible du p95 relâchée à 5 s : le serveur de développement ne
mesure rien). Les scénarios ne peuvent plus pourrir sans bruit (§7).

**Critère de fin** (« Essai local concluant ») : atteint ; la mesure de référence reste celle
de l'hébergement (L9.8, runbook).

## 16. Bilan de L9.5 (12 octobre 2026)

**Revue** : `docs/L9-revue-securite.md` : OWASP Top 10 (2021) et ASVS 4.0 niveau 2 (sélection),
preuve par contrôle, **18 constats** (aucun critique ni élevé) : 9 corrigés dans le lot,
7 acceptés par écrit, 2 à vérifier sur l'hébergement (runbook).

**Correctifs** :

- **taille des requêtes** : `RequestSizeLimitMiddleware` refuse (413) un corps annoncé de plus
  de `GESTCONF_MAX_REQUEST_MB` (55 Mio) avant toute lecture ; la mise en tampon par Passenger
  reste à vérifier sur l'hébergement ;
- **cache** : `DefaultNoStoreMiddleware` pose `Cache-Control: no-store` sur toute réponse qui
  n'en fixe pas (les vues publiques et les fichiers gardent le leur) ;
- **PDF figés** : attestations et lettres servies seulement si leur empreinte est intacte
  (`PrivateStore.read_verified`, 404 sinon), comme les factures ;
- **passeport** : l'effacement de K14 et l'anonymisation suppriment aussi le PDF émis de la
  lettre, qui porte le numéro ; la lettre reste vérifiable par son code ;
- **rotation des secrets** : commande `rotate_signing_keys` ; `DJANGO_SECRET_KEY_FALLBACKS` ;
  procédures pour chaque secret dans `deploy/README.md` ;
- tests ajoutés : longueur minimale du mot de passe, objet d'e-mail sans retour à la ligne,
  PDF falsifié ou absent refusé, effacement du PDF de la lettre, rotation des clés, borne de
  taille, `no-store` ;
- rappel de L9.4 : bandeau à 600 requêtes par minute et par adresse (disponibilité).

**ZAP** : paquet multiplateforme 2.16.1 (Java 21, empreinte SHA-256 `e90ca63b…071415`),
essai local contre l'API en réglages de production (import OpenAPI de 359 adresses,
exploration, analyse passive) : une seule alerte faible, l'en-tête `Server` du serveur de
développement. Plan de l'opérateur, **passif seulement** : `deploy/zap/baseline.yaml`
(vérifié : il s'exécute ; dossier des rapports explicite, sans quoi ils s'écrivaient à côté du
plan, dans le dépôt). **Précision de S7** : Apache n'a pas pu servir le portail localement
(il refuse de tourner en root, et l'espace de travail ne lui est pas lisible) ; les en-têtes
du `.htaccess` restent couverts par les tests de fumée et par l'analyse de l'opérateur.

**Acceptés par écrit** (R10 à R15, R17) : actions de la CI par version majeure, pas de
Dependabot (proposé au commanditaire : il ouvrirait des PR automatiques), jeton du QR en clair
(par conception), numéro de passeport en clair (masqué, effacé), HSTS sans sous-domaines, CSP
`style-src 'unsafe-inline'`, pas d'antivirus (question 9).

**Critère de fin** (« Revue écrite, constats traités ») : atteint pour le volet du dépôt.

## 17. Bilan de L9.6 (12 octobre 2026)

**Audit d'accessibilité** (S8) : `@axe-core/playwright` 4.13.0 (dépendance de développement,
jamais livrée) ; assistant `web/e2e/axe.ts` : règles WCAG 2.0 et 2.1 A et AA, échec sur toute
violation **grave ou critique**, les autres listées sans échec. **25 points d'audit** dans le
parcours de bout en bout, aux écrans où il passe : création de compte, profil, brouillon et
récapitulatif de soumission, évaluation (deux fois), affectations, classement, mes
soumissions, programme public, planificateur, mentions de facturation, page « Inscription »,
inscriptions, pièces, accueil du jour J, présences, mes documents, vérification publique,
budget, mon planning, accueil du portail avec le bandeau, questionnaire, résultats du
questionnaire, rapports. Vérifié : l'assistant échoue bien sur une page piégée (image sans
texte, bouton sans nom).

**Constats et correctifs** (trois, tous corrigés ; le parcours passe ensuite 19 sur 19) :

- **bandeau du portail** : texte foncé sur orange, contraste 3,0:1 (WCAG 1.4.3 exige 4,5:1) ;
  texte blanc (5,0:1, jeton `--gc-on-warning`), lien souligné de la même couleur ;
- **questionnaire** : `aria-required` sur des `fieldset` (attribut interdit sur un groupe,
  WCAG 4.1.2) ; groupes de boutons radio en `role="radiogroup"` (seul rôle de groupe qui le
  porte), `aria-required` sur le champ libre, mention « obligatoire » de la légende ailleurs ;
  test unitaire ;
- **tableaux défilants** de la gestion (48 `.table-wrap` dans 40 écrans) : zone de défilement
  inatteignable au clavier (WCAG 2.1.1) ; directive partagée `ScrollRegion`, qui s'applique à
  la classe : `tabindex="0"`, `role="region"`, nom traduit ; test unitaire.

En passant : les fiches d'aide « Premiers pas » et « Sécurité » manquaient au profil des
relecteurs, à qui la 2FA est imposée (constat de la rédaction des guides, L9.7) ; ajoutées.

**Limite** : un audit automatique n'attrape que la part mécanique (environ un tiers des
critères WCAG) ; la revue manuelle (clavier, lecteur d'écran, zoom à 200 %) reste à faire
pendant la recette (cahier de recette, L9.7).

**Couverture** (S9) : mesurée sous SQLite (la CI la mesure sur MariaDB), avec les tests des
cinq modules critiques et les tests transverses (5 909 tests ; la suite complète ne peut que
l'augmenter) : `reviews` 96 %, `submissions` 93 %, `program` 93 %,
`registrations` 94 %, `payments` 93 % ; aucun module sous le seuil, aucun test ciblé à écrire.
**Seuil en CI** : 80 % par module sur ces cinq modules, après les tests MariaDB
(`coverage report --include … --fail-under=80`), boucle vérifiée localement (y compris
l'échec sous le seuil). **Précision de S9** : seuil par module plutôt que `fail_under` global
de `pyproject.toml`, qui mêlerait la logique critique au reste.

**Budget du portail** (hypothèse 13) : seuil d'avertissement du bundle initial porté de 365 à
375 ko (erreur inchangée à 380 ko) ; build vert à 369,8 ko, sans avertissement.

**Tests** : unitaires du front verts (shared 83, gestion 263, portail 173), lint et formatage
verts, E2E 19 sur 19 avec les audits.

**Critère de fin** (« Aucune violation grave ; seuil de couverture en CI ») : atteint.
