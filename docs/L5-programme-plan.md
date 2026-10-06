# Lot L5 — Programme : plan d'implémentation

> **Statut : validé le 6 octobre 2026, livré** (décisions I1 à I18 telles que proposées,
> sans correction ; propositions du §10 retenues, dont la lecture seule des autres fonctions
> du CO et le rappel de la confirmation de présentation). Étapes L5.0 à L5.7 livrées ; bilan
> du lot : `docs/L5-programme.md` ; étude : §21. Reste ouverte la question Q14 : la
> déclaration « publication » couvre-t-elle les noms des auteurs au programme public ?
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

## 11. Bilan de L5.0 (6 octobre 2026)

**iCal (I8)** : générateur **écrit à la main**, sans dépendance.

- La bibliothèque `icalendar` 7.3.0 est pur Python, mais elle apporte quatre paquets
  (`python-dateutil`, `six`, `typing_extensions`, `tzdata`) pour un besoin d'une centaine de
  lignes.
- Prototype du sous-ensemble utile de RFC 5545 :
  - `VCALENDAR` (`VERSION`, `PRODID`, `CALSCALE`, `METHOD:PUBLISH`) ;
  - `VEVENT` (`UID`, `DTSTAMP`, `DTSTART` et `DTEND` en UTC, `SUMMARY`, `LOCATION`,
    `DESCRIPTION`) ;
  - échappement de `\`, `;`, `,` et des sauts de ligne ;
  - lignes de 75 octets au plus, pliées sans couper un caractère UTF-8 ; fins de ligne CRLF.
- Relu par `icalendar`, hors du dépôt : textes restitués à l'identique, échappements et
  accents compris ; heures UTC exactes.
- Les tests de L5.4 vérifieront ces règles directement.

**Glisser-déposer (I15)** : le CDK d'Angular 22.2.1 n'a ni gestion du clavier ni attributs
ARIA dans son module de glisser-déposer (code installé vérifié). L'**équivalent au clavier**
est donc indispensable :

- menu « Placer dans… » ;
- boutons « monter » et « descendre » ;
- annonce du résultat dans une région `aria-live`.

**Pré-rendu d'un programme volumineux (I7)** : le portail pré-rend en interrogeant l'API au
build (`getPrerenderParams`), et chaque page embarque les réponses qu'elle a lues.

- **Mesure** sur un programme synthétique : 300 sessions et 1 200 communications donnent
  763 Ko de JSON ; une journée de 100 sessions, 254 Ko ; une session, 2,5 Ko. Le taux de
  compression mesuré (×20) est trompeur, le texte synthétique étant répétitif.
- **Compression** : aucune n'est configurée dans nos `.htaccess`, et celle d'o2switch n'est
  pas vérifiée. Il faut raisonner en taille brute.
- **Découpage retenu** :
  - une page d'accueil du programme (jours, sessions, sans le détail des communications) ;
  - **une page par jour** ;
  - une page par session, chacune lisant sa propre réponse d'API (`/v1/public/program`
    résumé, `/v1/public/program/days/{date}`, `/v1/public/program/sessions/{id}`).
- **À vérifier sur o2switch** : compression HTTP des pages statiques (`mod_deflate`). Elle
  s'ajoutera, si besoin, au `.htaccess` du portail.

**Heures et changement d'heure (I12)** : `local_to_utc` refuse les heures inexistantes et
ambiguës (essai : 02:30 le 28 mars et le 31 octobre 2027, à Paris).

- Les débuts et fins de session sont saisis à l'heure locale, puis convertis.
- Les durées et les créneaux sont calculés en **temps réel**, en UTC. Une session qui
  traverse un changement d'heure affiche donc des heures locales cohérentes avec le temps
  écoulé : à Paris, 01:30 plus 150 minutes affiche 05:00.
- Les erreurs de saisie sont renvoyées sur le champ concerné de la session (`starts_local`,
  `ends_local`).

## 12. Bilan de L5.1 (6 octobre 2026)

**Application `program`**, une migration, conforme au §3 avec deux adaptations :

- salles (équipements en liste fermée et note libre) ;
- sessions : type en catalogue fermé, titres FR et EN, thématique, salle, début et fin,
  consignes ;
- créneaux : position, durée, début et fin calculés, communication **ou** titre libre
  (contrainte), intervenant invité. Une communication n'occupe qu'un créneau : c'est un
  `OneToOneField`, comme le recommande Django ;
- rôles de séance (unicité session, compte, rôle) ;
- publications, en ajout seul, avec instantané et différences ;
- confirmations de présentation.

**Adaptation 1, état du programme** : la révision du brouillon (I14) vit dans une table
`program_state`, une ligne par édition, et non dans l'édition. La ligne est verrouillée par
chaque écriture de planification. Les contrôles de conflits sont ainsi mis en série sans
bloquer les autres écritures de l'édition. Elle porte aussi la révision et la version
publiées, d'où le nombre de modifications non publiées.

**Adaptation 2, services en paquet** (`apps/program/services/`), comme `reviews` :
paramètres en L5.1, puis planification, publication et agenda.

**Paramètres de l'édition (I17)** :

- `session_buffer_minutes` (0 à 30, contrainte en base) ;
- `presenter_registration_required` (RG-11, désactivée, sans effet avant L6) ;
- route `…/program/settings` : lecture `program.read`, écriture `program.write`, journal
  `program.settings_changed` (avant et après).

**Capacités (I1)** :

- `program.read` : `ADMIN`, `CHAIR`, `SC_CHAIR`, `OC_MEMBER` (toutes fonctions) ;
- `program.write` : `ADMIN` et CO « programme » (`FUNCTION_CAPABILITIES`) ;
- `program.publish` : `CHAIR` seul ; l'administrateur ne publie pas.

**Matrice** : profil « CO programme » ajouté, et cas de la route des paramètres ; elle
compte 1 328 tests.

**Données personnelles** :

- rôles de séance, créneaux d'intervenant et confirmations, à l'export ;
- anonymisation **refusée** tant que la personne figure au programme d'une édition non
  archivée ;
- ensuite, son nom est retiré des instantanés publiés (`ProgramPublication.redact`).

**Vérifications** :

- 2 208 tests backend sous SQLite ; les tests transverses, du paramétrage et du programme
  passent aussi sous MariaDB ;
- schéma régénéré sur MariaDB ; client TypeScript régénéré ;
- traductions du backend à jour ;
- front : 302 tests, lint et format.

## 13. Bilan de L5.2 (6 octobre 2026)

**Service de planification** (`apps/program/services/planning.py`), seul à écrire le
brouillon. Chaque écriture :

1. refuse une édition archivée (409) ;
2. verrouille la ligne `program_state` de l'édition, ce qui met les écritures en série ;
3. compare la révision attendue (412 `stale_revision` si elle a changé, I14) ;
4. recalcule les créneaux touchés ;
5. journalise (`program.*`, avant et après) et incrémente la révision.

**Créneaux (I3, RG-13)** :

- à la suite depuis le début de la session, séparés par le tampon de l'édition ;
- en temps réel, en UTC (I12) ;
- durée par défaut : celle du type de communication, sinon 20 minutes ;
- insertion à une position, déplacement dans la session ou vers une autre, changement de
  durée, retrait : les positions restent contiguës, et les deux sessions d'un déplacement
  sont recalculées ;
- le **dépassement** (RG-13) est signalé avec ses minutes, pas refusé : le brouillon peut
  contenir des conflits (I6).

**Sessions (I2, I12)** :

- saisies à l'heure de l'édition, avec les erreurs de conversion renvoyées sur
  `starts_local` ou `ends_local` ;
- fin après le début, 24 heures au plus, début pendant les dates de l'édition ;
- salle et thématique de l'édition ; salle active ;
- un changement d'horaire déplace les créneaux ;
- la suppression retire les créneaux et les rôles : les communications retournent dans la
  liste « à programmer ».

**Communications programmables (I5)** : `CONFIRMED` (ou `SCHEDULED`, pour un
déplacement), de la même édition, une seule fois.

**Salles (I9)** : nom unique dans l'édition (sans tenir compte de la casse), équipements en
liste fermée ; une salle utilisée ne se supprime pas (409 `in_use`) et se désactive.

**Conflits (RG-12, RG-13)** : `detect_conflicts` analyse tout le brouillon en un nombre
constant de requêtes.

- Salle : deux sessions qui se chevauchent dans la même salle. Deux sessions contiguës ne
  sont pas en conflit.
- Personne : présentateurs, intervenants invités et rôles de séance, à deux endroits au
  même moment.
  - Une personne s'identifie par son compte ou, pour un auteur sans compte, par son adresse
    sans tenir compte de la casse.
  - Le conflit ne cite que le **nom**, jamais l'adresse.
  - Deux présences dans la même session ne sont pas un conflit (président qui présente dans
    sa séance).
  - Les présentateurs sont ceux de la confirmation (I5), sinon les auteurs marqués
    présentateurs, sinon l'auteur qui a soumis.
- Dépassement (RG-13).

**Intégrité** : contrôle `program.slots` (créneaux contigus et cohérents avec la session et
le tampon ; communications placées confirmées ou programmées).

**Tests** : 22 tests de planification, dont un test de concurrence sur MariaDB (quatre
placements simultanés, mis en série sans perte : créneaux contigus, révision incrémentée
quatre fois).
2 229 tests backend sous SQLite ; les 32 tests du programme passent sous MariaDB. Le service
n'a pas encore de route : l'API de gestion arrive en L5.3.

## 14. Bilan de L5.3 (6 octobre 2026)

**Workflow (I5)** :

- `CAMERA_READY_RECEIVED → CONFIRMED` devient disponible, déclenchée par le soumissionnaire.
  L'étude la donnait au système en L6 : **écart validé** avec le plan.
  - Une garde de l'application `program` exige les présentateurs enregistrés ; L6 y
    ajoutera RG-11.
- Trois retraits ajoutés, avec motif obligatoire : depuis `CAMERA_READY_RECEIVED`,
  `CONFIRMED` et `SCHEDULED`.
  - L'effet inscrit par `program` libère le créneau (journalisé) et prévient l'équipe du
    programme : CO « programme » et Chair, sinon administrateurs.
  - Le motif n'est pas dans l'e-mail, et l'objet ne porte aucune variable autre que le nom du
    site, règle déjà vérifiée par un test des gabarits.
- La table compte 22 transitions (19 de l'étude, plus les 3 retraits).
- **Point ouvert** : `ACCEPTED_MINOR → WITHDRAWN` n'existe toujours pas. Un auteur accepté
  sous réserve ne peut retirer sa communication qu'après la version finale. À trancher, avec
  une transition à ajouter si besoin.

**Confirmation de présentation (I5)** : `POST /v1/submissions/{id}/confirm-presentation`.

- Réservée au soumissionnaire, une fois la version finale reçue.
- Présentateurs choisis parmi les auteurs (positions distinctes).
- La première fois, la communication passe à « confirmée ». Ensuite, un changement de
  présentateurs d'une communication placée incrémente la révision du programme : les
  conflits de personnes en dépendent (RG-12).
- Journal `program.presentation_confirmed` et `program.presenters_changed`.
- `/v1/submissions/{id}` expose `presentation` et l'action `confirm_presentation`.

**Rôles de séance (I10)** : `SPEAKER` et `SESSION_CHAIR` sont invitables par `ADMIN` et
`CHAIR`. La migration ne change que les choix du champ. Un rôle de séance ou un intervenant
invité doit avoir un rôle actif dans l'édition.

**API de gestion** (`…/program/…`, `program.read` en lecture, `program.write` en écriture,
table des capacités explicite) :

- `GET program` : brouillon complet pour le planificateur. Il contient les jours, les
  salles, les sessions avec créneaux et rôles, la liste « à programmer », les conflits, la
  révision et l'indicateur de modifications non publiées.
- Salles, sessions, créneaux et rôles : création, modification, suppression. Chaque
  écriture renvoie le brouillon complet, porte `If-Match` (412 `stale_revision`) et passe
  par le service de planification.
  - Un `PATCH` de créneau qui change la durée et la position s'exécute dans une seule
    transaction.
- `GET program/people?q=` : personnes de l'édition, avec nom, institution et rôles,
  jamais d'adresse.
- Objets d'une autre édition : 404.
- Composants du schéma nommés : `ProgramPerson`, `ProgramConflict`, énumérations
  `SessionKind`, `SessionRoleKind`, `Equipment`, `ProgramConflictKind`.

**Tests** :

- 2 422 tests backend sous SQLite ; 1 908 sous MariaDB pour les suites touchées (transverses, programme, soumissions, comptes, communications) ;
- 56 tests du programme ;
- matrice : 1 497 tests, une case par profil pour les 13 routes du programme ;
- table d'attribution des rôles et table du workflow mises à jour.

## 15. Bilan de L5.4 (6 octobre 2026)

**Publication (I6)** : `POST …/program/publish` (`program.publish`, Chair seul,
réauthentification récente, `If-Match`).

- **Refusée** tant qu'il reste un conflit (409 `program_conflicts`, RG-12 et RG-13), ou sans
  modification depuis la dernière publication (409 `program_unchanged`). Les deux codes sont
  nouveaux et traduits dans l'interface.
- **Instantané numéroté**, en ajout seul, construit par liste blanche :
  - sessions, salles, thématiques, créneaux ;
  - auteurs avec nom, institution et indication du présentateur ;
  - rôles de séance, intervenants invités ;
  - consignes, pour « Mon passage » seulement ;
  - une **clé de personne** interne (`user:<id>` ou `email:<adresse>`), que les réponses
    publiques retirent.
- **Transitions à ce moment seulement** (règle n° 4) :
  - `CONFIRMED → SCHEDULED` pour les communications placées ;
  - `SCHEDULED → CONFIRMED` pour celles retirées du programme publié. Cette transition
    est ajoutée (écart I6 validé) ; la table en compte 23.
  - Le workflow revérifie `program.publish` (famille `ORGANIZERS`).
- **Journal** `program.published` ; historique `GET …/program/publications` (version, date,
  auteur, résumé des différences).

**Notifications ciblées (I16)** :

- les passages de chaque personne sont comparés entre deux instantanés ;
- un e-mail part à chaque personne dont le passage est **nouveau, modifié ou supprimé**,
  une fois par version (clé d'idempotence avec une empreinte, sans adresse en clair) ;
- l'e-mail donne la date et l'heure de l'édition, la salle, le rôle et le titre ; la ligne
  est traduite (« : » à la française ou à l'anglaise) ;
- un présentateur **sans compte** reçoit l'e-mail à son adresse d'auteur, avec l'invitation
  à créer un compte pour retrouver son passage ;
- l'objet ne porte que le nom du site.

**Programme public (I7)** : trois routes anonymes, en cache public de 5 minutes, sur la
dernière publication de l'édition courante (404 tant que rien n'est publié).

- `GET /v1/public/program` : jours et sessions, sans le détail des communications.
- `GET /v1/public/program/days/{date}` : sessions d'un jour, en heure de l'édition.
- `GET /v1/public/program/sessions/{id}` : une session.
- Découpage décidé en L5.0. Les routes sont inscrites dans la liste blanche des vues
  anonymes (méta-test).
- **Test à traceurs** : ni adresse, ni clé de personne, ni consignes, ni identifiant de
  compte. Le brouillon reste invisible jusqu'à la publication suivante.
- **Intervenants invités (I11)** : biographie et photo seulement avec les consentements de
  L2, lus à la publication. Un retrait de consentement prend effet à la publication
  suivante.

**« Mon passage » (I8)** : `GET /v1/me/agenda` et `GET /v1/me/agenda.ics`, connecté, sans
cache.

- Lu dans la dernière publication de chaque édition non archivée.
- Une personne s'y reconnaît par son compte ou par une adresse **vérifiée**. Un co-auteur
  qui crée son compte plus tard retrouve donc son passage.
- Chaque passage donne la date, l'horaire, la salle (accès), la durée, le rôle, les
  co-intervenants, les présidents de séance et les consignes.
- Fichier iCal par le générateur de L5.0 (`apps/program/ical.py`), testé sur l'échappement,
  le pliage à 75 octets et l'UTC.

**Intégrité** : contrôle `program.publication`. Une communication programmée figure au
programme publié, et une communication publiée n'est pas restée confirmée.

**Tests** : 13 tests de publication ; matrice avec la publication (réauthentification
comprise) et l'historique. 2 462 tests backend sous SQLite ; 1 948 sous MariaDB pour les suites
touchées.

## 16. Bilan de L5.5 (6 octobre 2026)

**Rubrique « Programme » de la gestion**, inscrite dans le rail (catégorie entre Évaluation et
Paramétrage, `program.read`), dans la recherche et dans l'aide (une fiche par écran). Le rôle
actif l'affiche pour l'administrateur, le Chair, le président du CS et le CO.

- **Planificateur** (`/editions/{id}/programme`, I15) :
  - un jour à la fois, une colonne par salle active (plus les salles inactives encore
    utilisées et une colonne « hors salle ») ;
  - liste « à programmer » filtrable par thématique, type et texte ;
  - glisser-déposer du CDK : placer, réordonner, changer de session, rendre à la liste ;
  - **équivalent au clavier** : « Placer dans… » (choix de la session, groupé par jour),
    flèches monter et descendre, « Actions… » (déplacer, durée, retirer). Le focus suit le
    créneau ; chaque résultat est annoncé dans une région `aria-live` ;
  - heures des créneaux dans le fuseau de l'édition, jamais celui du navigateur ; occupation
    de chaque session (« 60 / 90 min ») ;
  - conflits renvoyés par le serveur à chaque écriture, sur la session, sur le créneau et
    dans une liste avec « Voir ». Une personne est citée par son nom, jamais par son
    adresse ;
  - sous 768 px, la grille devient une liste.
- **Sessions** : formulaire (type, titres, salle, thématique, horaires saisis à l'heure de
  l'édition, consignes), erreurs de conversion sur le champ concerné. Après la création, la
  session reste ouverte pour ses **rôles de séance** et ses **éléments libres** (intervenant
  invité facultatif). Le choix d'une personne cherche dans l'édition par le nom, sans
  adresse.
- **Salles** : équipements en liste fermée, accessibilité, désactivation ; une salle utilisée
  ne se supprime pas (message du serveur).
- **Publication** : état (version publiée, modifications non publiées, conflits, communications
  à programmer), publication confirmée réservée au Chair (réauthentification par
  l'intercepteur), effets annoncés, historique (version, date, auteur, différences). Rappel :
  le programme public paraît à la prochaine mise en ligne du portail.
- **Paramétrage › Programme** : tampon (RG-13) et RG-11.
- **Tableau de bord** : carte « Programme » (sessions, à programmer, conflits, état publié).
- Toutes les écritures envoient la révision lue (`If-Match`) et remplacent l'état de l'écran
  par le brouillon renvoyé. Une révision périmée (412) recharge le brouillon et le dit.

**Corrections du serveur, trouvées en construisant les écrans** :

- **Tampon (RG-13)** : le changer ne recalculait pas les créneaux existants et ne changeait
  pas la révision. Les horaires restaient faux jusqu'à la prochaine écriture de chaque
  session, et le contrôle d'intégrité les aurait signalés. Désormais, le changement verrouille
  l'état du programme, recalcule toutes les sessions et incrémente la révision (test dédié).
- **Schéma OpenAPI** : les listes `program/people` et `program/publications` étaient décrites
  paginées et triables, alors que les vues renvoient une liste simple. Le client généré
  lisait `results` et ne trouvait personne. Les vues du programme n'ont plus ni pagination ni
  tri générique ; schéma et client régénérés ; test de l'historique ajouté.
- **Portail à republier (I7)** : `program.published` compte désormais parmi les
  modifications non publiées du portail (bandeau de L2) ; les écritures du brouillon, non.
- Message de validation d'un créneau traduit.

**Correctif commun de la gestion** : `.table-wrap` est positionné. Les libellés masqués des
tableaux (position absolue) ne font plus déborder la page sur mobile.

**Vérifications** :

- parcours dans Chromium, sur une base de démonstration (3 salles, 7 sessions sur deux jours,
  12 communications) : placement au clavier et à la souris, montée avec focus conservé,
  correction d'un dépassement et d'un président de séance à deux endroits, rôle ajouté par
  la recherche, refus de suppression d'une salle utilisée, publication par le Chair
  (version 1, 11 personnes prévenues), tableau de bord, bandeau du portail ; aucun
  débordement à 375 px sur les six écrans ;
- front : 330 tests (shared 76, portail 116, gestion 138) ; lint, format, build ;
- backend : 2 465 tests sous SQLite ; 1 763 sous MariaDB pour le programme, le portail et les
  tests transverses ; schéma régénéré sur MariaDB.

**Point connu, antérieur à L5** : le bundle initial du portail (367,7 ko) dépasse le seuil
d'avertissement (365 ko), sans atteindre celui d'erreur (380 ko). Le bilan de L4 le
signalait déjà. À traiter en L5.6, qui touche le portail.

## 17. Bilan de L5.6 (6 octobre 2026)

**Programme public pré-rendu (I7)**, en FR et en EN, sans Material (budget du portail) :

- **Accueil** `/fr/programme/` (la page du site, qui n'est plus « à venir ») : jours et
  sessions, sans le détail des communications. Filtres par jour, salle, thématique et type,
  recherche sans tenir compte des accents ; le nombre de sessions affichées est annoncé.
  Avant la première publication : « pas encore publié ».
- **Une page par jour** `/fr/programme/<date>/` : liste détaillée (créneaux, auteurs,
  présentateurs signalés, présidents de séance, salle et accessibilité) ou **grille par
  salle** ; recherche dans les titres, les auteurs, les intervenants et les références.
- **Une page par session** `/fr/programme/session/<id>/` : horaire et fuseau, salle et
  indications d'accès, description, présidents, communications ; intervenants invités avec
  photo et biographie selon leurs consentements (I11).
- Heures dans le fuseau de l'édition, indiqué sur chaque page.
- Sélecteur de langue, titre, adresses canoniques et `hreflang` comme les pages du site ;
  marqueur de rendu complet `data-gc-rendered`.
- Pages du jour et de la session dans un seul morceau chargé à la demande
  (`program.routes.ts`).

**Pré-rendu** : `getPrerenderParams` lit `/v1/public/program` (aucun paramètre avant
publication). Le serveur annonce ces pages dans `/v1/public/portal/routes` : le contrôle après
build les exige (nombre et marqueur), et le plan du site les reprend (`alternates`). Le
portail ne dépend pas du programme : `program` inscrit un fournisseur d'adresses
(`register_route_provider`) dans `AppConfig.ready()`.

**Espace auteur** :

- section « Présentation » de la soumission : choix des présentateurs parmi les auteurs,
  « Confirmer ma présentation » (I5), puis mise à jour possible ;
- **créneau publié** dans `/v1/submissions/{id}` (`schedule`, plan §4), lu dans la dernière
  publication, jamais dans le brouillon. Un soumissionnaire qui ne présente pas sait ainsi
  quand passe sa communication ;
- retrait étendu à la version finale reçue, confirmée et programmée (motif obligatoire).

**« Mon passage » (I8)** : `/compte/mon-passage`, dans la navigation du compte. Passages
regroupés par édition et par jour, heures de l'édition, rôle, salle et accès,
co-intervenants, présidence, consignes ; lien « Ajouter à mon agenda (.ics) ».

**Vérifications** :

- **build pré-rendu** contre une API au programme publié (base de démonstration : 7
  sessions, 2 jours) : 35 pages pré-rendues, contrôle complet (34 routes), plan du site.
  Les pages ne contiennent aucune adresse ;
- **dans Chromium**, build servi avec `/api` relayé comme sous Apache :
  - au chargement, aucun appel d'API pour le programme (données embarquées) ;
  - le contenu est lisible sans JavaScript ;
  - filtres, recherche, grille par salle, passage en anglais ;
  - aucun débordement à 375 px ;
  - côté auteur : « Mon passage », fichier `.ics` téléchargé (UTC), créneau publié dans la
    soumission ;
- front : 345 tests (shared 76, portail 131, gestion 138) et 11 tests de scripts ; lint,
  format, build ;
- backend : 2 467 tests sous SQLite ; 1 860 sous MariaDB (programme, portail, soumissions,
  transverses), dont les nouveaux tests des routes du programme et du créneau publié ;
  schéma régénéré sur MariaDB.

**Points à signaler** :

- **Q14 toujours ouverte** : le programme public affiche les noms et institutions des
  auteurs (I7). À confirmer avant la mise en ligne.
- Bundle initial du portail : 367,8 ko, inchangé par L5.6 (+0,1 ko, déclaration des
  routes). Il est fait à 96 % du framework (`@angular/core` 213 ko, routeur 97 ko) ; notre
  code y pèse une trentaine de ko. Le seuil d'avertissement (365 ko) date d'une version
  antérieure d'Angular : à relever (370 ko) ou à garder comme simple avertissement. **À
  trancher par le commanditaire**, le seuil d'erreur (380 ko) restant inchangé.
- La page « Intervenants » reste « à venir » (fiche M10, P2).

## 18. Bilan de L5.7 (6 octobre 2026)

**Rappel de la confirmation de présentation** (proposition du §9, retenue à la validation et
restée à faire) : commande `remind_presentations`, horaire, idempotente et verrouillée.

- Tant que l'auteur n'a pas confirmé, le soumissionnaire reçoit un rappel trois jours, puis
  dix jours après la réception de sa version finale (date lue dans l'historique des
  statuts), une fois chacun.
- Un passage manqué n'est pas rattrapé : seul le rappel le plus récent part.
- Idempotence par la clé de l'e-mail, sans nouvelle table. Rien pour une communication
  confirmée ni pour une édition archivée.
- Gabarit FR et EN, objet sans autre variable que le nom du site ; cron et `deploy/README.md`
  mis à jour (liste fermée de `cron.sh` et son test).

**Bout en bout** : le parcours en série de L4 se prolonge de trois étapes, sur la même base.

1. L'auteure confirme sa présentation.
2. Dans la gestion :
   - le CO « programme » (2FA) crée une salle et une session trop courte, puis place la
     communication au clavier ;
   - le dépassement de 5 minutes est signalé (RG-13), puis corrigé par la durée du créneau ;
   - le Chair (2FA) publie : statut « programmée », e-mail de passage, historique.
3. L'auteure voit « Mon passage », télécharge le fichier iCal (UTC), retrouve le créneau dans
   sa soumission et la session au programme public, sans son adresse.

Le seed crée deux comptes de plus (CO « programme », Chair). Les 8 tests passent.

**Documentation** :

- bilan du lot `docs/L5-programme.md` ;
- étude §21 (Markdown et HTML), version 1.5 ;
- `CLAUDE.md` : structure, cron, état d'avancement, « Décisions du lot L5 ».

**Vérifications finales** :

- backend : 2 471 tests sous SQLite (8 ignorés) ; **2 479 sous MariaDB, suite complète** ;
  ruff ; traductions ; shellcheck ;
- front : 345 tests et 11 tests de scripts ; lint, format, build ;
- E2E : 8 tests.

**À faire hors du code** : passage en CI de L5.3 à L5.7 (nouvelle PR, sur demande) ; démo F
sur o2switch ; Q14 ; transition `ACCEPTED_MINOR → WITHDRAWN` ; seuil d'avertissement du bundle
du portail.
