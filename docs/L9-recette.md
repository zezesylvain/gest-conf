# Lot L9 — Recette, sécurité, charge et restauration : bilan (volet du dépôt)

Ce document résume ce que livre le lot L9 de GEST-CONF **dans le dépôt** et ce qui reste à faire
**sur l'hébergement**. Le détail des choix, des vérifications et des défauts trouvés est dans
[`L9-recette-plan.md`](L9-recette-plan.md) : décisions S1 à S16 au §2, hypothèses retenues au
§2.1 (les questions du §10 n'ayant pas reçu de réponse), bilans des étapes aux §11 à §18.
L'étude est mise à jour en conséquence (§25 « Mises à jour issues du lot L9 », version 1.9).

Le lot a deux volets (S1). **Le volet du dépôt (L9.0 à L9.7) est livré.** Le volet de
l'hébergement (L9.8 : le runbook, exécuté sur o2switch par un opérateur du commanditaire)
**n'a pas commencé** : cette session n'a pas accès à l'hébergement, et c'est voulu (les clés
restent chez le commanditaire). Le lot ne sera clos qu'avec lui.

## 1. Ce qui est livré

| Étape | Contenu | Commit |
|---|---|---|
| L9.0 | Plan validé (hypothèses), vérifications : sauvegarde et restauration MariaDB avec un compte limité, Locust, axe, règles `S` de `ruff`, ZAP | `453d3b6` |
| L9.1 | `backup_db` (manifeste, rotation, cron), sauvegarde avant `migrate` dans `deploy.sh`, `pull-backups.sh` (copie hors hébergement), `restore_db` et `restore.sh` | `80331f8` |
| L9.2 | Supervision : `backup` dans `/v1/health`, alertes sauvegarde et disque ; tests de fumée : en-têtes de sécurité, HSTS, redirection HTTPS | `c29cc39` |
| L9.3 | `seed_volume` (volume de l'étude) et garde-fous ; tests du nombre de requêtes ; N+1 corrigés (classement, export, planificateur) | `1e67b71` |
| L9.4 | Scénarios Locust et verdict, `loadtest_sessions`, essai local ; bandeau à 600 lectures par minute ; essai court en CI | `030c3a4` |
| L9.5 | Revue de sécurité (OWASP, ASVS) : 18 constats ; correctifs (taille des requêtes, `no-store`, empreinte des PDF, passeport, rotation des secrets) ; ZAP | `33c655a` |
| L9.6 | Audit axe dans le parcours (25 points), trois correctifs d'accessibilité ; seuil de couverture de 80 % par module critique en CI | `ee9ae15` |
| L9.7 | `seed_demo` ; cahier de recette ; guides ; exploitation ; runbook ; check-list de mise en production ; trame des pages légales | `c785482` |
| L9.9 | Ce bilan, étude (§25), `CLAUDE.md` | dernier commit du lot |
| L9.8 | **Sur l'hébergement, avec l'opérateur** : runbook complet | **à faire** |

## 2. Ce que le dépôt apporte, en bref

**Reprise après incident** (objectif : perte de 24 heures au plus, rétablissement sous 4 heures)
:

- sauvegarde quotidienne de la base (2 h 07), compressée, avec un manifeste (empreinte, migrations,
  inventaire des fichiers déposés), rotation 7/4/3, identifiants jamais sur une ligne de
  commande ; sauvegarde avant chaque migration ;
- copie **tirée** par l'opérateur depuis son poste, en instantanés datés : un effacement sur
  l'hébergement n'atteint pas les copies déjà prises ;
- restauration dans une base vide, vérifiée contre le manifeste puis par `check_integrity` ;
  mesurée au volume de l'étude : **6 secondes** en local.

**Performances** : listes chaudes en nombre de requêtes constant (tests) ; au volume de l'étude
(600 soumissions, 1 500 inscrits), médiane de chaque vue de gestion mesurée sous 230 ms en local ;
le test de charge sur l'hébergement fait foi (cible : 200 utilisateurs, p95 < 500 ms).

**Sécurité** : revue écrite ([`L9-revue-securite.md`](L9-revue-securite.md)), aucun constat
critique ni élevé ; neuf corrigés, sept acceptés par écrit, deux à vérifier sur l'hébergement.

**Accessibilité** : aucune violation grave ou critique sur les 25 écrans audités du parcours.

**Recette et exploitation** : édition de démonstration en une commande, cahier de recette de 107
scénarios, guides par rôle, guide d'exploitation, runbook en douze étapes, check-list de mise en
production, trame des pages légales.

## 3. Documents remis

| Document | Pour qui |
|---|---|
| [`L9-runbook-o2switch.md`](L9-runbook-o2switch.md) | l'opérateur, sur l'hébergement |
| [`exploitation.md`](exploitation.md), [`../deploy/README.md`](../deploy/README.md) | l'opérateur, au quotidien |
| [`L9-cahier-de-recette.md`](L9-cahier-de-recette.md) | le commanditaire et ses testeurs |
| [`L9-mise-en-production.md`](L9-mise-en-production.md) | le commanditaire (décision d'ouverture) |
| [`guides/`](guides/README.md) | les comités, les relecteurs, les bénévoles ; formateurs |
| [`guides/aide-portail.md`](guides/aide-portail.md) | le CO « communication » (texte de la page « Aide », à valider) |
| [`pages-legales-trame.md`](pages-legales-trame.md) | le commanditaire (texte définitif) |
| [`L9-revue-securite.md`](L9-revue-securite.md) | le commanditaire, un auditeur éventuel |
| [`../loadtest/README.md`](../loadtest/README.md) | l'opérateur (test de charge, depuis son poste) |

## 4. Ce qui reste à faire ou à décider

**Sur l'hébergement** (L9.8, opérateur à désigner, question 1 du plan) : le runbook entier, dans
l'ordre : vérifications et fiche o2switch, premier déploiement, cron surveillé 48 heures,
sauvegarde et **restauration chronométrée**, borne de taille des envois, **test de charge**
puis retour à la sauvegarde, ZAP passif, **recette** des démos A à I par le commanditaire,
retour à une base propre, surveillance externe, check-list de mise en production. Aucune des
démos A à I n'a encore été jouée sur o2switch, et aucune donnée réelle ne doit y entrer avant une
restauration testée (D18).

**À décider par le commanditaire** :

- les questions du §10 du plan L9, appliquées comme hypothèses (§2.1) ;
- les questions nées du lot (plan, §18) : catégories tarifaires réservées, désabonnement des
  annonces et invitations aux questionnaires (RG-22), écran « Sessions du jour » pour la
  présidence désignée au programme, Dependabot ;
- les points ouverts des lots précédents : Q7, Q8, Q14, Q17 ; `ACCEPTED_MINOR → WITHDRAWN` ;
- l'ouverture de l'appel, sur la check-list de mise en production.

**Écarts avec l'étude, sans écran aujourd'hui** (à arbitrer, aucun n'est P1) : page « Contact »,
« Mon programme » du participant (J15), indisponibilités des intervenants, connexion ORCID (P2),
accès des co-auteurs à la soumission.

**L10 et suivants** (P3) : non commencés ; ils attendent la livraison du P1, c'est-à-dire la fin
de L9.8.
