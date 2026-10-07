# Lot L9 — Recette, sécurité, charge : plan d'implémentation

> **Statut : proposé le 7 octobre 2026, à valider** (décisions S1 à S16, questions du §10).
> L8 est livré en code et testé en local (bilan : `docs/L8-logistique.md`). Les décisions de
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

## 2. Décisions (proposées)

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
