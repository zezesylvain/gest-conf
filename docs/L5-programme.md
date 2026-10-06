# Lot L5 — Programme : bilan et exploitation

Ce document résume ce que livre le lot L5 de GEST-CONF et comment l'exploiter. Le détail des
choix, des vérifications et des défauts trouvés est dans
[`L5-programme-plan.md`](L5-programme-plan.md) (décisions I1 à I18 au §2, bilans des étapes
aux §11 à §18). L'étude est mise à jour en conséquence (§21 « Mises à jour issues du lot L5 »).

## 1. Ce qui est livré

| Étape | Contenu | Commit |
|---|---|---|
| L5.0 | Vérifications : iCal écrit à la main, glisser-déposer au clavier, pré-rendu volumineux, changement d'heure | `bce058d` |
| L5.1 | Modèle `program`, capacités, paramètres de l'édition, matrice, registre des données personnelles | `aba4e4c` |
| L5.2 | Service de planification : créneaux, RG-12, RG-13, verrou, révision, journal, intégrité | `699b894` |
| L5.3 | Confirmation de présentation, retraits, rôles de séance, API de gestion | `728ace3` |
| L5.4 | Publication, programme public (API), « Mon passage », iCal | `439c460` |
| L5.5 | Écrans de la gestion : planificateur, sessions, salles, publication, paramétrage, tableau de bord, aide | `af1e540` |
| L5.6 | Portail : programme public pré-rendu, confirmation de présentation, « Mon passage » | `a29011a` |
| L5.7 | Parcours de bout en bout, rappel de confirmation, recette, bilan, étude (§21), `CLAUDE.md` | `51095a3` |

Intégration continue : L5.0 à L5.2 par la PR #8, L5.3 à L5.7 par la PR #9 (fusionnées, CI au
vert : backend 3.12 et 3.13 sur MariaDB, front, E2E, scripts de déploiement).

## 2. Parcours couverts (démo F)

- **CO « programme »** (et administrateur), dans la gestion, rubrique « Programme », 2FA
  imposée :
  - salles : capacité, équipements, accessibilité ; désactivation d'une salle utilisée ;
  - sessions : type (catalogue fermé), titres FR et EN, salle, horaires **à l'heure de
    l'édition**, consignes ; rôles de séance (président, discutant, modérateur, panéliste) ;
    éléments libres avec intervenant invité ;
  - **planificateur** : grille du jour par salle, liste « à programmer » filtrable,
    glisser-déposer **et équivalent au clavier** (« Placer dans… », monter, descendre,
    durée, retrait), annonces aux lecteurs d'écran, vue en liste sur mobile ;
  - conflits renvoyés à chaque écriture : salle occupée, personne à deux endroits (RG-12),
    session qui déborde (RG-13) ;
  - « Paramétrage › Programme » : tampon entre créneaux (0 à 30 minutes) et RG-11
    (désactivée, sans effet avant les inscriptions).
- **Chair** : publication confirmée, refusée tant qu'il reste un conflit ou sans
  modification ; historique des versions ; carte « Programme » du tableau de bord. Les
  autres profils de gestion consultent.
- **Auteur** (portail) :
  - après la version finale, désignation des présentateurs et confirmation de sa venue ;
  - créneau publié dans sa soumission ;
  - retrait possible jusqu'au programme publié, avec un motif ;
  - rappel par e-mail s'il n'a pas confirmé, trois puis dix jours après sa version finale.
- **Présentateur, intervenant invité, président de séance** : e-mail à chaque publication
  qui crée, modifie ou supprime son passage ; « Mon passage » (`/compte/mon-passage`) et
  fichier `.ics`.
- **Public** : programme pré-rendu en FR et EN :
  - accueil avec filtres (jour, salle, thématique, type) et recherche ;
  - une page par jour (liste détaillée ou grille par salle) ;
  - une page par session (salle et accès, présidents, communications, intervenants
    invités).

## 3. Sécurité et données personnelles, en bref

- **Brouillon jamais servi hors de la gestion** : le programme public, « Mon passage », le
  fichier iCal et le créneau de la soumission lisent le **dernier instantané publié**.
- **Instantané par liste blanche** : sessions, salles, créneaux, noms et institutions. Une
  clé de personne interne (compte ou adresse) sert à « Mon passage » ; les réponses
  publiques la retirent.
  - **Test à traceurs** : ni adresse, ni clé, ni consignes, ni identifiant de compte.
  - Le build pré-rendu a été contrôlé : aucune adresse dans les pages produites.
- **Intervenants invités** : biographie et photo publiées seulement avec les consentements
  de L2 (`directory_listing`, `photo_publication`).
- **Droits** : `program.read` (administrateur, Chair, président du CS, CO), `program.write`
  (administrateur, CO « programme »), `program.publish` (Chair seul). La matrice des droits
  couvre chaque route (1 524 cas au total).
- **Publication** : réauthentification récente, journal `program.published` (RG-17).
- **Concurrence** : toutes les écritures sont mises en série par un verrou (état du
  programme de l'édition) et portent la révision lue (412 si elle a changé).
- **Données personnelles** :
  - rôles de séance, créneaux d'intervenant et confirmations figurent à l'export ;
  - l'anonymisation est refusée tant que la personne figure au programme d'une édition non
    archivée ; ensuite, son nom est retiré des instantanés publiés.

## 4. Exploitation

- **Cron**, à ajouter dans cPanel (voir [`deploy/README.md`](../deploy/README.md)) :

  ```text
  23 * * * *   $HOME/gestconf-app/deploy/cron.sh remind_presentations
  ```

- **Après chaque publication du programme** : remettre le portail en ligne
  (`deploy/deploy.sh --portal-only`). Le programme public est pré-rendu ; le bandeau du
  Portail compte la publication parmi les modifications à mettre en ligne. Le contrôle
  après build exige les pages des jours et des sessions publiés, et le plan du site les
  reprend.
- **Avant de programmer** : salles, sessions et tampon ; les auteurs confirment leur
  présentation (la liste « à programmer » ne contient que les communications confirmées).
  Pour un président de séance ou un intervenant extérieur, l'inviter d'abord avec le rôle
  « Président de session » ou « Intervenant ».
- **Liens des e-mails** :
  - équipe du programme : `/gestion/editions/{id}/programme` ;
  - passages : `/compte/mon-passage` ;
  - rappel de confirmation : `/compte/soumissions/{id}`.
- **Contrôles d'intégrité** (`check_integrity`) :
  - `program.slots` : créneaux contigus et cohérents avec leur session et le tampon ;
    communications placées confirmées ou programmées ;
  - `program.publication` : communications programmées présentes au programme publié, et
    inversement.
- **À vérifier sur o2switch** : compression HTTP des pages statiques (`mod_deflate`). Une
  journée chargée pèse quelques centaines de ko non compressés (mesure de L5.0).

## 5. Tests

- **Backend** : 2 471 tests sous SQLite et 2 479 sous MariaDB (suite complète). Ils
  couvrent notamment :
  - créneaux, tampon et RG-13, y compris le recalcul quand le tampon change ;
  - conflits de salle et de personne (RG-12), y compris pour un auteur sans compte ;
  - heures locales et changement d'heure ;
  - concurrence sur MariaDB (placements simultanés mis en série) et révision périmée ;
  - workflow : confirmation, retraits, `SCHEDULED` et retour à `CONFIRMED` ;
  - publication : refus en présence de conflits, instantané, différences, e-mails
    idempotents ;
  - programme public par traceurs, routes annoncées au pré-rendu, iCal (échappement,
    pliage, UTC) ;
  - rappels de confirmation (idempotents, passage manqué) ;
  - matrice des droits.
- **Front (Vitest)** : 345 tests (shared 76, portail 131, gestion 138) et 11 tests des
  scripts de build. Ils couvrent le planificateur, y compris le parcours au clavier, les
  écrans de gestion, le programme public, « Mon passage » et la confirmation de
  présentation.
- **Bout en bout (Playwright, CI)** : le parcours en série de L4 se prolonge :
  - l'auteure confirme sa présentation ;
  - le CO « programme », connecté avec sa 2FA, crée une salle et une session trop courte,
    puis place la communication **au clavier** ;
  - le dépassement est signalé (RG-13), puis corrigé par la durée du créneau ;
  - le Chair publie : la communication est programmée et l'auteure prévenue ;
  - l'auteure voit « Mon passage », télécharge le fichier iCal, retrouve le créneau dans sa
    soumission et la session au programme public (sans son adresse).
- **Recette locale dans Chromium** :
  - écrans de la gestion sur une base de démonstration (3 salles, 7 sessions, 12
    communications) ;
  - build pré-rendu servi comme sous Apache : pages complètes sans JavaScript, aucun appel
    d'API pour le programme au chargement ;
  - à 375 px, aucun débordement.

## 6. Ce qui reste à faire ou à décider

**Avant la mise en ligne du programme** :

- démo F sur o2switch, avec la ligne de cron `remind_presentations` ;
- compression HTTP des pages statiques à vérifier ;
- fournisseur d'e-mails de production (D10).

**Décisions du commanditaire** :

- **Q14** : la déclaration « publication » couvre-t-elle les noms et institutions des auteurs
  au programme public ? Le programme les affiche (I7).
- **`ACCEPTED_MINOR → WITHDRAWN`** n'existe pas : un auteur accepté sous réserve ne peut se
  retirer qu'après sa version finale. Transition à ajouter ?
- **Budget du bundle initial du portail** : 367,8 ko pour un avertissement à 365 ko
  (erreur à 380 ko). L5 n'y ajoute que 0,1 ko ; 96 % du bundle est le framework. Relever le
  seuil d'avertissement à 370 ko, ou le garder comme simple avertissement ?

**Reporté (P2 et lots suivants)** :

- indisponibilités déclarées, « Mon programme » du participant et notification des
  inscrits (après L6) ;
- PDF du programme, fiche intervenant complète (M10, la page « Intervenants » reste « à
  venir »), minuterie du président de séance ;
- proposition automatique de planning (P3), sessions hybrides (Q10, P3) ;
- RG-11 effective (présentateur inscrit) : branchée en L6.

**Pour L6 (inscriptions)** : RG-11, tarifs et agrégateur de paiement (Q7), entité de
facturation (Q8). Plan L6 validé le 6 octobre 2026 : `docs/L6-inscriptions-plan.md`.
