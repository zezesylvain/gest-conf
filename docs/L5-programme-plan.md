# Lot L5 — Programme : plan d'implémentation

> **Statut : validé le 6 octobre 2026** (décisions I1 à I18 telles que proposées, sans
> correction ; propositions du §10 retenues, dont la lecture seule des autres fonctions du CO
> et le rappel de la confirmation de présentation). Reste ouverte la question Q14 : la
> déclaration « publication » couvre-t-elle les noms des auteurs au programme public ?
> L4 est clos (bilan : `docs/L4-evaluation.md`).
>
> Sources :
> - étude §3.3 (matrice), §4 M7 (et M10 pour les salles), §5.1, §5.4, §6 (RG-11, RG-12,
>   RG-13, RG-17), §8.2 (« Programme »), §8.3, §9.2, §10, §14 (L5 : 16 à 22 j-h), §15 (Q10,
>   Q12) ;
> - mises à jour §17 à §20 ;
> - plan L1 : reports vers L5 (RG-11 désactivable, tampons RG-13, rôles `SPEAKER` et
>   `SESSION_CHAIR`, écritures du CO « programme ») ;
> - plan L2, E6 (programme public reporté en L5) ; plan L4, H16 (`accepted_minor`).

## En bref

| | |
|---|---|
| **Objectif** | Le CO (fonction « programme ») crée les salles et les sessions de chaque jour, puis place les communications confirmées dans les sessions. Un moteur de contrôle signale les conflits pendant la saisie (RG-12, RG-13). Le Chair publie le programme : les intervenants et les présidents de séance concernés sont prévenus. Le portail affiche le programme public. Chacun voit « Mon passage » et l'ajoute à son agenda (`.ics`). |
| **Point dur** | **RG-12 sans contrainte d'exclusion** (MariaDB) : tous les contrôles passent par un service unique, sous verrou de l'édition, doublés d'un contrôle d'intégrité. Heures saisies à l'heure de l'édition (D13), y compris aux changements d'heure. Planificateur accessible au clavier (WCAG 2.1 AA), pas seulement au glisser-déposer. |
| **Hors périmètre** | Proposition automatique de planning (P3) ; « Mon programme » du participant et notification des inscrits (P2, après L6) ; indisponibilités déclarées (P2) ; PDF du programme (P2) ; sessions hybrides (Q10, P3) ; fiche intervenant complète, voyage et besoins (M10, P2, L8) ; minuterie du président de séance (P2) ; grille de service du CO et des bénévoles (L8). |
| **Charge** | **21,5 à 27 j-h** (étude : 16 à 22). Détail au §8. |
| **Démo F** | Le CO crée trois salles et huit sessions sur deux jours, dont une plénière et une pause. Les auteurs confirment leur présentation. Le responsable du programme place douze communications à la souris et au clavier. Le moteur signale un président de séance à deux endroits et une session qui déborde ; on corrige. Le Chair publie : les intervenants et présidents reçoivent un e-mail. Le portail, republié, affiche le programme (liste, grille par salle, recherche). Un auteur voit « Mon passage » et télécharge le `.ics`. Un changement d'horaire après publication ne prévient que l'intervenant concerné. |

## 1. Périmètre

| Fonction (étude M7, §5.4) | Priorité | Dans L5 |
|---|---|---|
| Salles (capacité, équipements, accessibilité) | P1 | Oui (I9) |
| Sessions : type, salle, horaires, président de séance | P1 | Oui (I2, I10) |
| Placement des communications acceptées (glisser-déposer) | P1 | Oui, avec une alternative au clavier (I15) |
| Détection des conflits : salle, personne, chevauchement, dépassement | P1 | Oui (I4, I5) ; indisponibilités : P2 |
| « Mon passage » de chaque acteur | P1 | Oui pour les intervenants et les présidents de séance (I8) |
| Programme brouillon / publié, journal des modifications | P1 | Oui (I6, I13) |
| Programme public : liste, grille par salle, recherche, fiche session | P1 | Oui (I7) |
| Export iCal individuel | P2 | Oui : la charge est faible et l'étude le cite pour L5 (I8) |
| Notification d'un changement | P2 | Intervenants et présidents : oui (I16) ; inscrits : après L6 |
| Indisponibilités, « Mon programme », PDF, hybride, proposition automatique | P2, P3 | Non |

**Écarts avec l'étude, à valider** :

- `CAMERA_READY_RECEIVED → CONFIRMED` par l'auteur, et non par le système en L6 (I5) ;
- retraits et déprogrammation ajoutés au §5.1 (I5, I6) ;
- types de session en catalogue fermé (I2) ;
- programme public pré-rendu, donc visible après republication du portail (I7).

## 2. Décisions à valider

| # | Sujet | Proposition |
|---|---|---|
| I1 | Droits (Q12, matrice §3.3) | Nouvelles capacités. **`program.read`** : `ADMIN`, `CHAIR`, `SC_CHAIR`, `OC_MEMBER` (toutes fonctions). **`program.write`** : `ADMIN` et `OC_MEMBER` de fonction « programme » (réponse partielle à Q12, par `FUNCTION_CAPABILITIES`). **`program.publish`** : `CHAIR` (« le Chair valide », §5.4). Comme pour les décisions (H19), l'administrateur ne publie pas. La 2FA s'applique déjà à ces rôles (D3) |
| I2 | Structure | Édition → **jours** (dates de l'édition, sans table) → **sessions** → **créneaux**. Session : type, titre FR/EN, description, thématique facultative, salle, début et fin (heure de l'édition), consignes techniques. **Types en catalogue fermé** (ouverture, plénière, parallèle, posters, atelier, tutoriel, table ronde, assemblée, pause, repas, social, clôture), libellés traduits ; liste paramétrable par édition : P2 |
| I3 | Créneaux | Un créneau porte une **position** et une **durée**. Début et fin sont **calculés** par le service : début de la session, durées et tampons. Ils sont stockés pour les recherches. Un créneau contient une communication, ou un élément libre (titre FR/EN, intervenant invité facultatif). Durée par défaut : celle du type de communication (`default_duration_min`), modifiable. Une communication n'occupe qu'**un** créneau |
| I4 | RG-12 | **Conflits bloquants** : deux sessions dans la même salle au même moment ; une personne à deux endroits au même moment (présentateur, intervenant invité, président de séance, discutant). Le chevauchement de deux créneaux d'une session est impossible par construction (I3). Une personne s'identifie par son compte, ou à défaut par l'adresse normalisée d'un auteur |
| I5 | RG-13 et statut des communications | **RG-13** : la somme des durées et des tampons ne dépasse pas la durée de la session. Le tampon est un paramètre de l'édition, de 0 à 30 minutes (défaut 0). **Programmables** : les communications `CONFIRMED` (§5.4). **Confirmation de présentation** par le soumissionnaire, dans le portail : il désigne le ou les présentateurs parmi les auteurs et confirme sa venue. Transition `CAMERA_READY_RECEIVED → CONFIRMED`, par le soumissionnaire (**écart** : l'étude la donne au système, en L6). **RG-11** devient un paramètre de l'édition, désactivé par défaut ; L6 y branchera la garde « présentateur inscrit ». **Retraits** ajoutés : `CAMERA_READY_RECEIVED`, `CONFIRMED` ou `SCHEDULED → WITHDRAWN`, par le soumissionnaire, avec motif ; le créneau est libéré et le CO prévenu |
| I6 | Brouillon et publication | Les sessions et créneaux se modifient en **brouillon**. La **publication** (`program.publish`, réauthentification récente, journal) fige un **instantané** numéroté, en ajout seul : il sert au portail et à « Mon passage ». Le brouillon peut contenir des conflits, signalés ; **la publication est refusée tant qu'il en reste** (RG-12, RG-13). À la publication, les communications placées passent `CONFIRMED → SCHEDULED` ; une communication retirée du programme publié repasse `SCHEDULED → CONFIRMED` (**écart** : transition ajoutée). La gestion affiche le nombre de modifications non publiées |
| I7 | Programme public | Page du portail **pré-rendue au build** à partir du dernier instantané publié (règle de L2, E1), en FR et EN. Vues : liste par jour, grille par salle, filtres (jour, salle, thématique, type de session), recherche dans la page, fiche de session. **Visible après republication du portail** (`deploy.sh --portal-only`, D18) : la gestion le signale. Les pages « à venir » de L2 (E6) sont remplacées. Contenu : titres, horaires, salles, noms et affiliations des auteurs, présidents de séance ; **jamais d'adresse** |
| I8 | « Mon passage » et iCal | Espace compte du portail, `/compte/mon-passage`, d'après l'instantané publié. Pour un présentateur, un intervenant invité ou un président de séance : date, heure (fuseau de l'édition), salle, durée, rôle, co-intervenants, consignes. **`GET /v1/me/agenda.ics`** : RFC 5545, heures en UTC, authentifié. Générateur écrit à la main et testé, sans dépendance ; autre choix : bibliothèque `icalendar`, pur Python, à vérifier en L5.0 |
| I9 | Salles | Nom, capacité, équipements (liste fermée et note libre), accessibilité, indications d'accès. Une salle utilisée ne se supprime pas (409 `in_use`) : elle se désactive |
| I10 | Rôles de séance | Président de séance, discutant, modérateur, panéliste : des **comptes**, car ils ont besoin de « Mon passage ». Les rôles `SESSION_CHAIR` et `SPEAKER` sont **activés** : invitation par les détenteurs de `members.manage` (`ADMIN`, `CHAIR`), par le parcours d'invitation de L1 (RG-20). Désigner comme président de séance un membre déjà présent dans l'édition ne demande pas d'invitation |
| I11 | Intervenants invités | Créneau libre avec un compte `SPEAKER` et un titre. Ils figurent au programme public. Leur photo et leur biographie n'y paraissent qu'avec les consentements de L2 (`directory_listing`, `photo_publication`). Fiche M10 complète : P2 |
| I12 | Heures | Saisie à l'heure de l'édition, stockage en UTC (D13). Une heure inexistante ou ambiguë est refusée (`local_to_utc`). Les sessions doivent tenir dans les dates de l'édition. L'affichage se fait dans le fuseau de l'édition, qui est indiqué |
| I13 | Journal | Chaque écriture est journalisée (`program.*`, avant et après). L'historique des publications donne la version, la date, l'auteur et un résumé des différences. Le « journal des modifications » de l'étude est cette liste, plus le journal d'audit filtré sur `program.*` |
| I14 | Concurrence | Toutes les écritures verrouillent l'édition (`select_for_update`), ce qui met en série les contrôles. Une **révision du programme** part en `If-Match` : 412 si un autre membre a modifié le programme entre-temps, et l'interface recharge (même règle qu'en L3) |
| I15 | Planificateur (gestion) | Grille jours × salles. Liste « à programmer » (communications `CONFIRMED` non placées), filtrable par thématique et par type. Glisser-déposer par le CDK d'Angular, avec un **équivalent au clavier** : menu « Placer dans… », boutons monter et descendre. Alertes de conflit en direct, renvoyées par le serveur à chaque écriture. Sous 768 px : vue en liste |
| I16 | Notifications | À la publication, un e-mail à chaque présentateur, intervenant invité ou président de séance dont le passage est **nouveau, modifié ou supprimé**, calculé par différence entre deux instantanés. Clé d'idempotence par version. Lien vers « Mon passage ». Inscrits : après L6 |
| I17 | Paramètres de l'édition | `session_buffer_minutes` (0 à 30, défaut 0), `presenter_registration_required` (RG-11, défaut non ; sans effet avant L6). Écran « Paramétrage › Programme » |
| I18 | Ordre | L5.0 vérifications ; L5.1 à L5.4 serveur ; L5.5 et L5.6 écrans ; L5.7 E2E et documentation. Le programme précède les inscriptions (L6), comme le prévoit l'étude (§14.2) |

## 3. Modèle de données (nouvelle application `program`, additif)

- `program_room` : édition, nom, capacité, équipements (JSON, liste fermée), note,
  accessibilité, active, position.
- `program_session` : édition, type, titre FR/EN, description FR/EN, thématique (nulle),
  salle (nulle pour un événement hors salle), début et fin (UTC), consignes, position.
  - Index `(room, starts_at)` et `(edition, starts_at)` (§8.3).
- `program_slot` : session, position, durée, début et fin calculés, communication (nulle,
  **unique**), titre FR/EN libre, intervenant invité (nul).
- `program_session_role` : session, compte, rôle (`chair`, `discussant`, `moderator`,
  `panelist`) ; unique par session, compte et rôle.
- `program_publication` : édition, version, publiée le, par, instantané (JSON), résumé des
  différences (JSON). En ajout seul.
- `presentation_confirmation` : soumission (unique), présentateurs (positions des auteurs),
  confirmée le, par.
- Édition : `program_revision`, `session_buffer_minutes`, `presenter_registration_required`.
- **Registre des données personnelles** : rôles de séance et confirmations, avec export et
  anonymisation. L'anonymisation est refusée tant que la personne figure au programme publié
  d'une édition non archivée (règle F16).
- **Contrôles d'intégrité** : pas de chevauchement de salle ni de personne dans le dernier
  instantané ; créneaux contigus et cohérents avec leur session ; communications placées
  `CONFIRMED` ou `SCHEDULED`.

## 4. API

**Gestion** (`…/manage/editions/{id}/program/…`, 2FA) :

- `rooms` : CRUD (`program.write` ; lecture `program.read`).
- `sessions` : CRUD, avec les rôles de séance et les conflits de chaque session ;
  `POST sessions/{s}/slots` (placer une communication ou un élément libre) ;
  `PATCH slots/{c}` (durée, position, autre session) ; `DELETE slots/{c}`.
- `to-schedule` : communications `CONFIRMED` non placées, avec présentateurs, type et durée
  par défaut.
- `conflicts` : analyse complète du brouillon (RG-12, RG-13).
- `publish` (`program.publish`, réauthentification récente) ; `publications` (historique et
  différences).
- Paramètres de l'édition (I17), dans `…/settings`.
- Toute écriture porte `If-Match: <révision>` (I14).

**Public** : `GET /v1/public/program` (dernier instantané publié de l'édition courante), lu au
build du portail.

**Auteur** : `POST /v1/submissions/{id}/confirm-presentation` (présentateurs) ; retrait
étendu (I5) ; `presentation` (session, salle, créneau) dans `/v1/submissions/{id}` après
publication.

**Compte** : `GET /v1/me/agenda` ; `GET /v1/me/agenda.ics`.

## 5. Frontend

**Gestion**, rubrique « Programme » :

- salles ;
- sessions (formulaire, rôles de séance) ;
- **planificateur** (I15) ;
- liste « à programmer » ;
- publication : conflits restants, modifications non publiées, confirmation ;
- historique des publications ;
- « Paramétrage › Programme » ;
- carte « Programme » au tableau de bord (communications à programmer, conflits,
  modifications non publiées).

Chaque écran est inscrit dans le rail et a sa fiche d'aide (règle de L2).

**Portail** :

- programme public pré-rendu, en FR et EN : liste, grille, filtres, recherche, fiche de
  session ;
- espace auteur : « Confirmer ma présentation » ;
- `/compte/mon-passage` et lien `.ics`.

## 6. Sécurité

- Droits vérifiés par le serveur ; matrice étendue, avec un test par case.
- Le programme **brouillon** n'est jamais servi hors de la gestion. Le public et « Mon
  passage » ne lisent que l'instantané publié.
- **Instantané public** construit par liste blanche :
  - ni adresse, ni compte, ni donnée de brouillon ;
  - un test à traceurs le vérifie, comme pour RG-04.
- **Publication** : réauthentification récente et journal (RG-17).
- **Fichier `.ics`** :
  - réservé à l'utilisateur connecté, `no-store` ;
  - textes échappés selon RFC 5545 ;
  - aucune autre personne que les co-intervenants et le président de séance.

## 7. Tests

- **Unitaires** :
  - calcul des créneaux, tampons, RG-13 ;
  - conflits de salle et de personne (RG-12), y compris pour un auteur sans compte (adresse) ;
  - heures locales, changement d'heure.
- **Concurrence** : deux placements simultanés, mis en série par le verrou ; révision
  périmée (412).
- **Workflow** : `CONFIRMED`, `SCHEDULED` et le retour à `CONFIRMED`, retraits, RG-11
  inactif.
- **Publication** : refus en présence de conflits ; instantané ; différences ; e-mails
  idempotents par version.
- **API** : matrice des droits, test à traceurs de l'instantané public, `.ics` (pliage des
  lignes, échappement, UTC).
- **Front** : planificateur, y compris le parcours au clavier ; programme public ; « Mon
  passage ».
- **E2E** (L5.7) : confirmation de présentation → salles et sessions → placement → conflit
  signalé puis corrigé → publication → « Mon passage » et `.ics`.

## 8. Étapes

| Étape | Contenu | Critère de fin | Charge |
|---|---|---|---|
| L5.0 | Vérifications : génération iCal (à la main ou `icalendar`), CDK glisser-déposer au clavier, pré-rendu d'un programme volumineux, changement d'heure | Choix consignés | 0,5 – 1 |
| L5.1 | Modèle `program`, capacités, paramètres de l'édition, matrice, registre | Matrice au vert | 2 – 2,5 |
| L5.2 | Service de planification : créneaux, RG-12, RG-13, verrou, révision, journal, intégrité | Tests des conflits au vert | 3 – 3,5 |
| L5.3 | Confirmation de présentation, retraits, rôles `SESSION_CHAIR` et `SPEAKER`, API de gestion | Tests du workflow au vert | 2 – 2,5 |
| L5.4 | Publication (instantané, `SCHEDULED`, différences, e-mails), API publique, « Mon passage », `.ics` | Test à traceurs au vert | 2,5 – 3 |
| L5.5 | Écrans de gestion : salles, sessions, planificateur, à programmer, publication, historique, paramétrage, tableau de bord, aide | Démo F côté gestion | 6 – 7,5 |
| L5.6 | Portail : programme public pré-rendu, confirmation de présentation, « Mon passage » | Démo F côté portail | 3 – 4 |
| L5.7 | E2E, recette, documentation, étude (§21) | Démo F sur o2switch | 1,5 – 2 |
| **Total L5** | | | **20,5 – 26** (+ marge de 1 j-h → **21,5 – 27**) |

## 9. Risques et hypothèses non vérifiées

| Risque | Mesure |
|---|---|
| Conflits manqués, faute de contrainte d'exclusion en base | Service unique sous verrou, contrôle complet avant publication, contrôle d'intégrité quotidien |
| Glisser-déposer inaccessible | Équivalent au clavier exigé et testé (I15) |
| Programme public en retard sur la publication | Pré-rendu au build (E1) : la gestion signale « portail à republier » ; décision sur le déploiement continu (D18) |
| Noms des auteurs publiés sans base claire | La déclaration « publication » (F7) doit couvrir le programme public : texte à confirmer (Q14) |
| Fuseau et changement d'heure | Saisie locale refusée si inexistante ou ambiguë (D13) ; tests sur un fuseau à changement d'heure |
| Volume du programme pré-rendu | Mesure en L5.0 (centaines de sessions) ; filtrage côté client sans bibliothèque lourde |
| Confirmation de présentation oubliée par les auteurs | Rappel par e-mail, sur le modèle des relances de L3 et L4 (commande cron idempotente) : **proposé**, à confirmer |

## 10. Questions au commanditaire

1. Validation de I1 à I18, en particulier :
   - I1 : publication par le Chair seul ; écriture par le CO « programme » et
     l'administrateur ;
   - I5 : confirmation de présentation par l'auteur, au lieu d'une transition système en L6 ;
     retraits ajoutés ;
   - I6 : publication refusée tant qu'il reste des conflits ;
   - I7 : programme public visible après republication du portail.
2. **Q12** : les autres fonctions du CO (logistique, secrétariat) écrivent-elles dans le
   programme ? Proposition : non, lecture seule.
3. **Q10** (sessions hybrides) : hors L5 ; les liens de visioconférence restent en P3.
4. **Q14** : la déclaration « publication » couvre-t-elle les noms et affiliations des auteurs
   au programme public ?
5. Rappel automatique de la confirmation de présentation (§9) : oui ou non ?
6. Charge de 21,5 à 27 j-h, contre 16 à 22 dans l'étude.
