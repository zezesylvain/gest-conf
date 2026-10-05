# Lot L2 — Portail public : bilan et exploitation

Ce document résume ce que livre le lot L2 de GEST-CONF et comment l'exploiter. Le détail des
choix, des vérifications et des écarts est dans [`L2-portail-plan.md`](L2-portail-plan.md)
(décisions E1 à E14 au §2, bilans des étapes aux §11 à §18). L'étude est mise à jour en
conséquence (§18 « Mises à jour issues du lot L2 »).

## 1. Ce qui est livré

| Étape | Contenu | Commit |
|---|---|---|
| L2.0 | Vérifications : Pillow sur o2switch (contrôle V28), multipart du client généré, pré-rendu FR/EN alimenté par une API, redirection de `/` | `5151477` |
| L2.1 | Gestion : rail en catégories rétractables, recherche d'écran `⌘K`, guide `/gestion/aide` et aide contextuelle `?` pour tous les écrans | `c16016f` |
| L2.2 | CMS du portail côté serveur (`apps/portal`) : sections, pages, composition, menus, assainisseur HTML, API publique et de gestion, capacité `portal.write`, état de publication | `42b381f` |
| L2.3 | Écrans du CMS dans la gestion : sections (éditeur bilingue, aperçu), pages, composeur, menus, bandeau d'écart, fiches d'aide | `2456fa8` |
| L2.4 | Fichiers publics (documents, images, affiche) ; photo et liens du profil, consentement `photo_publication` | `210fdd5` |
| L2.5 | Portail public FR/EN pré-rendu : pages du site, rendu des sections, menus, pages personnalisées, contrôle de complétude du build | `62464fc` |
| L2.6 | Comités publics avec consentements ; référencement (canonique, `hreflang`, Open Graph, JSON-LD, plan du site) ; `deploy.sh --portal-only` ; test de fumée étendu | `313ff0a` |
| L2.7 | Recette locale, bilan du lot, étude (§18), `CLAUDE.md` | ce lot |

## 2. Parcours couverts

- **Visiteur** (`/fr/…`, `/en/…`, pré-rendu) :
  - accueil (édition, thème, dates, lieu, compte à rebours) ;
  - appel à communications (formats, échéances, modèles) ;
  - dates, thématiques, comités ;
  - pages « à venir » (programme, intervenants, inscription) ;
  - pages personnalisées `/fr/p/<slug>/` ;
  - documents téléchargeables.
- **Gestion**, rubrique « Portail » (`ADMIN`, `CHAIR`, CO « communication » ; lecture pour
  les autres rôles de gestion) :
  - sections, pages et composition, menus d'en-tête et de pied ;
  - documents et images, affiche ;
  - bandeau « N modifications non publiées ».
- **Gestion, pour tous** : rail, recherche d'écran, guide et aide contextuelle.
- **Compte** : photo et liens publics dans « Profil » ; consentements « annuaire » et « photo »
  dans « Confidentialité ».
- **Opérateur** :
  - `deploy/deploy.sh --portal-only` (publication du portail) ;
  - `manage.py seed_portal` (pages, sections et menu manquants) ;
  - `manage.py mark_portal_published` (appelée par le déploiement).

## 3. Sécurité et données personnelles, en bref

- HTML des contenus : liste blanche, assaini à l'écriture (serveur) **et** au rendu (portail),
  testé contre des charges XSS connues des deux côtés.
- Fichiers publics :
  - stockés hors racine web, sous un nom aléatoire ;
  - type vérifié par le contenu ; images réencodées sans EXIF ;
  - servis par Django seulement s'ils sont publiés et dans un contexte public, avec
    `nosniff`, une CSP `sandbox` et `attachment` pour les documents ;
  - un fichier encore utilisé ne se supprime pas.
- Comités publics :
  - seulement les membres actifs qui ont consenti à l'annuaire ;
  - photo avec un second consentement ;
  - jamais d'adresse ;
  - les autres membres sont comptés, pas nommés.
- Écritures du CMS auditées, adresses masquées dans le journal ; droits vérifiés par le
  serveur (matrice étendue au profil « CO communication »).
- CSP à empreintes inchangée : le JSON-LD n'est pas exécutable, il n'a pas besoin
  d'empreinte.

## 4. Exploitation

- **Publier le portail** :
  - commande : `deploy/deploy.sh --portal-only`, avec `DEPLOY_BASE_URL` (voir
    [`deploy/README.md`](../deploy/README.md), « Publier le portail ») ;
  - le déploiement complet l'enchaîne ;
  - une modification faite dans la gestion n'apparaît qu'à la publication suivante (pré-rendu
    au build).
- **Variables** : `GESTCONF_FILES_DIR` (fichiers publics, à sauvegarder avec la base),
  `GESTCONF_PUBLIC_URL` (adresses canoniques, Open Graph, plan du site) ;
  `GESTCONF_PRERENDER_API_ORIGIN` au build seulement.
- **Cron inchangé** :
  - `cleanup` purge les fichiers publics orphelins ;
  - `check_integrity` signale les fichiers manquants sur le disque.
- **Test de fumée** :
  - redirection de `/` ; pages pré-rendues, canonique, Open Graph ;
  - `sitemap.xml` et `robots.txt` ;
  - fichier public servi, fichier inconnu en 404.

## 5. Tests

- **Backend** : 1 345 tests sous SQLite, 1 351 sous MariaDB.
  - Assainisseur et composition (ordre en liste complète, relue).
  - Pages du site, menus, routes à pré-rendre.
  - Fichiers (signatures, contenus déguisés, bombes, EXIF, repli sans Pillow, orphelins).
  - Comités et consentements (tests `rg_e5`), écart de publication.
  - Matrice des droits (`portal.write`), garde-fous des scripts de déploiement.
- **Frontend (Vitest)** : 234 tests.
  - Portail (84) : routes, assainisseur, sections, comités, référencement.
  - Gestion (74) : navigation, recherche, cohérence des fiches d'aide, écrans du CMS.
  - Shared (76).
  - Plus 8 tests des scripts de build : contrôle de complétude, plan du site, CSP.
- **Recette locale dans Chromium** (démo C, sans o2switch) :
  - le bandeau compte 78 modifications non publiées ;
  - publication simulée (pré-rendu contre l'API locale, 30 routes, puis
    `mark_portal_published --built-at`) : le bandeau passe à « Le portail est à jour » ;
  - `Ctrl+K` « affiche » trouve « Documents et images », et `?` ouvre sa fiche ;
  - page « Comités » sans le membre non consentant ;
  - modèle téléchargé (200, `attachment`) ;
  - pages personnalisées dans le plan du site ;
  - aucune erreur dans la console.
- Les étapes L2.3 à L2.6 ont chacune été vérifiées dans le navigateur : composition, menus,
  fichiers, photo, FR/EN, 375 px, hydratation sans nouvel appel d'API.

## 6. Ce qui reste à faire ou à décider

**Sur o2switch** (accès au compte nécessaire) :

- contrôle V28 (Pillow) ;
- **démo C en conditions réelles** ;
- premier `--portal-only` ;
- aperçu Open Graph réel (Facebook, LinkedIn) ;
- tests de fumée en production.

**Décisions du commanditaire** :

- budget du bundle initial du portail : 371,4 kB pour un avertissement à 365 kB (relever le
  seuil, ou optimiser) ;
- cadence de publication du portail et déploiement continu (D18) ;
- textes définitifs des consentements « annuaire » et « photo » (Q14) ;
- liste des titres affichés (`ProfileTitle`) ;
- écart E6 : programme public en L5 au lieu de L2.

**Pour la suite** :

- les pages « à venir » (programme, intervenants, inscription) deviennent de vraies pages
  dans leur lot (L5, L6), sans changer leurs adresses ;
- tout nouvel écran de gestion s'inscrit dans la table de navigation et reçoit sa fiche
  d'aide.
