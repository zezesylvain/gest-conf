# Lot L3 — Soumission : bilan et exploitation

Ce document résume ce que livre le lot L3 de GEST-CONF et comment l'exploiter. Le détail des
choix, des vérifications et des défauts trouvés est dans
[`L3-soumission-plan.md`](L3-soumission-plan.md) (décisions F1 à F17 au §2, bilans des étapes
aux §11 à §17). L'étude est mise à jour en conséquence (§19 « Mises à jour issues du lot L3 »).

## 1. Ce qui est livré

| Étape | Contenu | Commit |
|---|---|---|
| L3.0 | Vérifications : nettoyage des PDF par `pypdf` sur un corpus porteur d'identité, Playwright en CI | `8c3828b` |
| L3.1 | Modèle des soumissions, compteur verrouillé, workflow `transition()`, RG-19, registre des données personnelles | `2d4f4b5` |
| L3.2 | API de l'espace auteur : brouillons, auteurs, PDF, `check`, soumission, révisions, retrait, RG-02, e-mails | `09bfffe` |
| L3.3 | Espace auteur du portail (`/compte/soumissions`) ; client généré en réexportations « étoile » | `52607cc` |
| L3.4 | Gestion des soumissions : API, liste, détail, export, dérogations, tableau de bord, RG-19 affiché ; `close_call` | `356ffd4`, `a1f1137` |
| L3.5 | Doublons (F15), rappels des brouillons, cloche de notifications | `4ba0e95` |
| L3.6 | Parcours auteur de bout en bout en CI, recette, bilan, étude (§19), `CLAUDE.md` | ce lot |

## 2. Parcours couverts

- **Auteur** (portail, `/compte/soumissions`) :
  - nouveau brouillon si l'appel est ouvert et le profil complet ;
  - assistant en cinq étapes, sauvegarde automatique, compteur de mots ;
  - co-auteurs (ordre, correspondant, présentateur) ;
  - PDF selon le type, métadonnées retirées en double aveugle ;
  - déclarations versionnées ;
  - récapitulatif (manques RG-01, doublons possibles) ;
  - soumission (référence `GC27-0001`, accusé de réception) ;
  - modification jusqu'à la clôture (révisions) ; retrait motivé ; historique ;
  - cloche et page `/compte/notifications`.
- **Gestion**, rubrique « Soumissions » (`ADMIN`, `CHAIR`, `SC_CHAIR`, CO en lecture) :
  - liste filtrée (statuts, thématique, type, langue, recherche, doublons) ;
  - détail avec les adresses des auteurs et les versions du PDF ;
  - dérogations (accorder, révoquer) ; export CSV ;
  - compteurs au tableau de bord.
- **Paramétrage** : politique de fichier et taille des types, langues des soumissions, gel RG-19
  du code et du double aveugle.
- **Opérateur** :
  - `close_call` : passage en recevabilité à la clôture ;
  - `remind_drafts` : rappels à J-7 et la veille.

## 3. Sécurité et données personnelles, en bref

- **Statuts** écrits par `transition()` seulement (méta-test) ; droits vérifiés par le serveur
  (matrice étendue : 7 routes, une case par profil) ; un auteur ne voit que ses soumissions (404).
- **Fichiers des auteurs** :
  - règle n° 8 sans adaptation : stockage privé, nom aléatoire, type vérifié par le contenu ;
  - servis par des endpoints authentifiés seulement ;
  - en double aveugle, réécrits sans `/Info` ni XMP.
- **Export CSV** : journalisé (RG-17) ; cellules neutralisées contre l'injection de formules.
- **Données de tiers** (co-auteurs) :
  - information par e-mail ; jamais d'adresse dans le journal ni dans une notification ;
  - export et anonymisation par le registre.
- **Anonymisation d'un auteur** : refusée tant qu'une soumission active existe (F16).
- **Double aveugle (RG-04)** : la vue relecteur, sans identité, sera écrite en L4 avec le premier
  endpoint relecteur. Les sérialiseurs sont déjà séparés par rôle.

## 4. Exploitation

- **Variable** `GESTCONF_PRIVATE_FILES_DIR` : fichiers des auteurs, hors racine web, à
  sauvegarder avec la base.
- **Cron**, à ajouter dans cPanel (voir [`deploy/README.md`](../deploy/README.md)) :

  ```text
  11 * * * *   $HOME/gestconf-app/deploy/cron.sh close_call
  13 * * * *   $HOME/gestconf-app/deploy/cron.sh remind_drafts
  ```

  - `cleanup` purge aussi les fichiers privés orphelins et les vieilles notifications (en
    simulation tant que les durées D15 ne sont pas validées) ;
  - `check_integrity` signale les fichiers manquants et les incohérences de références.
- **Clôture de l'appel** : à l'heure de l'édition. Une dérogation, accordée dans la gestion,
  rouvre la modification d'une soumission jusqu'à son échéance.
- **Client de l'API** : `npm run api:generate` réécrit l'index en réexportations « étoile »
  (`web/scripts/api-barrel.mjs`). Sans cela, toute fonction d'API utilisée entre dans le bundle
  initial.

## 5. Tests

- **Backend** : 1 524 tests sous SQLite, 1 531 sous MariaDB. Ils couvrent notamment :
  - workflow (table complète, gardes, méta-test), RG-01, RG-02, RG-19, numérotation
    concurrente ;
  - PDF (corpus, chiffré, faux PDF, taille) ;
  - API auteur et gestion, matrice des droits ;
  - export et injection de formules, clôture idempotente, rappels idempotents ;
  - cloche, registre des données personnelles.
- **Front (Vitest)** : 274 tests (portail 110, gestion 88, shared 76) et 11 tests des scripts
  de build.
- **Bout en bout (Playwright, CI)** : parcours auteur complet, sur une base créée pour la série.
  - Étapes : inscription, vérification de l'adresse, profil, brouillon, co-auteur, PDF,
    déclarations, soumission, accusé, révision, clôture simulée, refus de modifier,
    recevabilité.
  - La base est préparée par les services, comme le ferait un opérateur (`web/e2e/seed.py`).
- **Recette locale dans Chromium** :
  - auteur : parcours complet, conflit entre deux onglets, 375 px ;
  - gestion : liste, filtre, export, PDF, dérogation accordée puis révoquée, gel RG-19 ;
  - cloche et doublons ;
  - aucune erreur dans la console.

## 6. Ce qui reste à faire ou à décider

**Avant l'ouverture réelle de l'appel** :

- textes définitifs des déclarations et de la notice d'information (Q14) ;
- fournisseur d'e-mails de production (D10) ;
- décision sur le déploiement continu (D18) ;
- démo D sur o2switch, avec les deux lignes de cron.

**Décisions du commanditaire** :

- durées de conservation des notifications (D15) ;
- budget du bundle initial du portail : 367,7 kB pour un avertissement à 365 kB ;
- Q3 (double aveugle par défaut), Q5 (formats et limites), Q6 (langues).

**Pour L4** :

- vue relecteur sans identité (RG-04) et ses tests ;
- transitions de recevabilité et d'évaluation ;
- écart `REVISION_REQUESTED` du §5.1 à préciser ;
- plan L4 (H1 à H19) en attente de validation.
