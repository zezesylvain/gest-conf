# Lot L8 — Logistique, partenaires, communication et reporting : bilan et exploitation

Ce document résume ce que livre le lot L8 de GEST-CONF et comment l'exploiter. Le détail des
choix, des vérifications et des défauts trouvés est dans
[`L8-logistique-plan.md`](L8-logistique-plan.md) : décisions N1 à N19 au §2, hypothèses
retenues au §2.1 (les questions du §10 n'ayant pas reçu de réponse), bilans des étapes aux
§11 à §21. L'étude est mise à jour en conséquence (§24 « Mises à jour issues du lot L8 »).

## 1. Ce qui est livré

| Étape | Contenu | Commit |
|---|---|---|
| L8.0 | Vérifications : `openpyxl` (Python pur, formules neutralisées), bandeau du portail chargé à la demande, plafond horaire partagé, segments sur MariaDB, assainisseur des annonces | `7ca3efb` |
| L8.1 | Applications `logistics`, `sponsors`, `surveys`, `reports` ; capacités par fonction du CO ; matrice ; registre des segments | `229df1e` |
| L8.2 | Tâches du CO (révision, commentaires, pièces jointes, cloche, rappel quotidien) ; budget prévisionnel et réalisé, lignes calculées, justificatifs, export | `1450a5f` |
| L8.3 | Partenaires : niveaux, fiches, contreparties, contributions, logo public, API publique, ligne « partenariats » du budget | `238ce6d` |
| L8.4 | Venues des intervenants invités, régimes alimentaires (RG-23), repas et estimation, postes de bénévoles, « Mon planning » et iCal | `e3410f5`, `76c1d0b` |
| L8.5 | Annonces (actualités, bandeau, cloche, e-mail), envois groupés par segments (RG-22), désabonnement, plafond partagé | `5141a34` |
| L8.6 | Questionnaire de satisfaction anonyme (RG-21) : invitations, relance unique, seuil de 5 réponses, export mélangé | `7c481ad` |
| L8.7 | Rapports par section (CSV, XLSX, PDF), fil d'activité du CO, commande au traiteur en PDF | `3ba4cfb` |
| L8.8 | Gestion : « Organisation », « Logistique », « Partenaires », « Communication », « Rapports », « Mon planning », tableau de bord, aide (cinq sous-étapes) | `dc7698c` à `ef2d38a` |
| L8.9 | Portail : « Partenaires », « Intervenants » (réelle), « Actualités », bandeau ; compte : « Ma venue », régime et annonces, questionnaires, désabonnement, cloche | `5da1d9f`, `16e73aa` |
| L8.10 | Parcours de bout en bout, recette, bilan, étude (§24), `CLAUDE.md` | dernier commit du lot |

Intégration continue : PR [zezesylvain/gest-conf#13](https://github.com/zezesylvain/gest-conf/pull/13).

## 2. Parcours couverts (démo I)

- **Comité d'organisation**, dans la gestion :
  - « Organisation » : tâches en trois colonnes, déplacées au clavier, avec responsable,
    échéance, commentaires et pièces jointes ; rappel quotidien des retards ; budget
    prévu et réalisé, recettes d'inscription et de partenariat calculées ; fil d'activité ;
  - « Logistique » (CO « logistique », lue par le Chair et le secrétariat) : venues des
    intervenants (voyages, hôtel, équipement manquant en salle), repas et effectifs pour le
    traiteur avec les régimes agrégés, liste nominative à part ; postes des bénévoles
    (CO « logistique » ou « bénévoles ») ;
  - « Partenaires » (CO « relations extérieures » ; lus par les finances, la communication
    et le Chair) : niveaux, fiches, contreparties, logo, publication au portail ;
  - « Communication » (CO « communication », Chair) : annonces avec aperçu de l'e-mail,
    essai, publication, retrait et annulation de l'envoi ; questionnaires (avec le
    secrétariat) et leurs résultats ;
  - « Rapports » : sections selon les capacités, graphiques doublés de tableaux, exports ;
  - tableau de bord : carte « Organisation ».
- **Bénévole** : « Mon planning » dans « Jour J », avec son fichier iCal ; cloche à chaque
  affectation ou retrait.
- **Intervenant invité** (portail) : « Ma venue » (besoins, voyages, demandes ; ce que le
  comité a réservé), régime.
- **Toute personne inscrite ou membre d'un comité** (portail) : « Régime et annonces »
  (régime avec consentement, abonnement aux annonces par e-mail), « Questionnaires »,
  désabonnement par le lien de l'e-mail, cloche.
- **Visiteur** (portail public) : « Partenaires », « Intervenants », « Actualités »
  pré-rendues ; bandeau de dernière minute visible aussitôt.

## 3. Sécurité et données personnelles, en bref

- **RG-21, anonymat du questionnaire** :
  - la réponse n'a aucune clé vers un compte ni vers l'invitation, et ne porte aucune date ;
    sa clé primaire est un UUID aléatoire ;
  - l'invitation est marquée « répondu » (au jour près) dans la même transaction ;
  - rien au journal ne relie une personne à une réponse ;
  - résultats à partir de 5 réponses ; textes libres exportés dans un ordre aléatoire ; la
    personne est prévenue que le comité lira ses commentaires.
- **RG-22, envois groupés** :
  - un e-mail par personne, jamais de copie, dans sa langue, avec la raison de l'envoi et
    un lien de désabonnement signé ;
  - la moitié du plafond horaire d'e-mails au plus, étalée ; annulation de ce qui n'est pas
    parti ; journal de masse (segment, nombre) ;
  - publication sous réauthentification récente.
- **RG-23, régimes** :
  - déclaration facultative, consentement explicite à chaque fois, retrait à tout moment ;
  - effectifs agrégés pour la restauration ; noms et allergies pour `logistics.read`
    seulement, par un export réauthentifié et journalisé ;
  - effacés 30 jours après la fin de l'édition (`cleanup`).
- **Listes blanches publiques** : partenaires (ni contact, ni montant, ni statut),
  intervenants (lus dans l'instantané publié, consentements de L2 figés, ni clé de compte),
  bandeau et actualités ; le logo d'un partenaire n'est public qu'une fois le partenaire
  publié (aperçu authentifié dans la gestion).
- **Note interne** du comité sur une venue : jamais servie à l'intervenant.
- **Journal** : adresses masquées dans les textes libres (`mask_emails`) ; contact d'un
  partenaire jamais journalisé.
- **Droits** (capacités par fonction du CO, revérifiées par le serveur) : `tasks.*` (tout le
  CO), `budget.*` (finances), `sponsors.*` (relations extérieures ; lecture finances,
  communication), `logistics.*` (logistique ; lecture secrétariat), `volunteers.plan`
  (logistique, bénévoles), `shifts.own` (bénévole), `communications.send` (communication),
  `surveys.manage` (communication, secrétariat) ; le Chair lit et communique.
- **Données personnelles** : venues, régimes, affectations, invitations aux questionnaires,
  désabonnements et annonces reçues figurent à l'export ; anonymisation et conservation
  selon N15.

## 4. Exploitation

- **Cron** : une ligne nouvelle, `remind_tasks` (quotidienne, 6 h 53 dans l'exemple de
  `deploy/cron.sh`). Les envois groupés, les invitations et la relance des questionnaires
  passent par `run_jobs` (toutes les 5 minutes) ; l'effacement des régimes par `cleanup`.
- **Portail** :
  - « Partenaires », « Intervenants » et « Actualités » sont **pré-rendues** : une
    modification n'y paraît qu'après `deploy/deploy.sh --portal-only` (la gestion compte les
    modifications non publiées) ;
  - le **bandeau** est lu à chaque visite, sans publication du portail ;
  - nouvelles adresses : `/fr/partenaires/`, `/en/partners/`, `/fr/actualites/`,
    `/en/news/` ; `/desabonnement/<jeton>` servie par la coquille rendue dans le navigateur.
- **E-mails** : le plafond (`GESTCONF_EMAIL_MAX_PER_HOUR`, 200 par défaut) borne les envois
  groupés à 100 par heure ; un envoi à 1 000 personnes prend au moins 10 heures. Limites
  réelles d'o2switch et du fournisseur de production **non vérifiées**.
- **Contrôles d'intégrité** (`check_integrity`) : contribution reçue sans montant ni date,
  questionnaire dont les réponses ne correspondent pas aux invitations « répondu ».
- **Avant la conférence** : niveaux et partenaires publiés, portail republié ; repas créés
  et commande au traiteur exportée (PDF) ; postes et affectations des bénévoles.
- **Après la conférence** : questionnaire publié (invitations aux présents à l'ouverture,
  relance à mi-chemin) ; rapports exportés.

## 5. Tests

- **Backend** : **6 700 réussis**, 10 ignorés (SQLite) ; sous MariaDB, les sous-ensembles de chaque étape et les tests de la négociation de contenu réussissent ; matrice des droits : **5 385 cas** (3 746 à la fin de L7).
  Ils couvrent notamment RG-21 (colonnes de la table des réponses, journal, réponse unique,
  seuil), RG-22 (un e-mail par personne dans sa langue, désabonnés, lots idempotents,
  moitié du plafond, annulation), RG-23 (consentement, agrégats, export nominatif
  réauthentifié, effacement), les listes blanches publiques (partenaires, intervenants,
  bandeau), les rapports sans donnée nominative, les exports CSV, XLSX et PDF.
- **Front (Vitest)** : **530 tests** : shared 82, portail 172, gestion 263, scripts 13 (469 à la fin de L7) ; lint, `format:check` et builds propres.
- **Bout en bout (Playwright)** : le parcours en série se prolonge par trois étapes :
  1. organisation : tâche créée puis terminée au clavier, recettes calculées au budget,
     partenaire publié et lu par l'API publique ;
  2. logistique : « Ma venue » et régime de l'intervenant invité, signal dans la liste,
     repas où le régime est compté sans nom, poste de bénévole retrouvé dans « Mon
     planning » ;
  3. communication : annonce au bandeau, visible aussitôt sur le portail, e-mail du
     segment parti par la file ; questionnaire publié, invitation de l'auteure présente,
     réponse anonyme, résultats sous le seuil puis au-dessus ; rapport « Satisfaction »
     exporté en PDF.
- **Défauts trouvés par le parcours**, tous deux **antérieurs à L8** et corrigés avec leurs
  tests (plan, §21) :
  - les téléchargements de la gestion par le client généré (exports CSV, XLSX et PDF,
    badges, iCal) recevaient un **406** : le client annonce le type du fichier en `Accept`,
    et DRF, qui ne rend que du JSON, refusait avant la vue. La négociation retient désormais
    le JSON quand le client n'accepte que des types de fichier (`apps/core/negotiation.py`),
    et un méta-test vérifie chaque réponse binaire du schéma ;
  - le corps d'erreur d'une requête de fichier, reçu en `Blob`, perdait son code : une
    réauthentification exigée par un export passait pour un refus. L'intercepteur du front
    le relit désormais en JSON.

## 6. Ce qui reste à faire ou à décider

**Décisions du commanditaire** (plan, §10, sans réponse : les propositions sont retenues
comme hypothèses) : ordre des lots L8 et L9, périmètre, niveaux et montants des
partenaires, régimes pour tous ou pour les intervenants, réservations des voyages,
questionnaire anonyme et par session, fournisseur d'e-mails et volume horaire, postes du
budget, indicateurs prioritaires.

**À vérifier sur o2switch** : plafond d'e-mails réel, délai d'un envoi groupé, bandeau sur
le portail en production, pré-rendu des trois pages nouvelles.

**Précisions et limites connues** :

- la page « Intervenants » présente les intervenants invités (créneaux libres) ; les
  présentateurs des communications restent au programme (Q14 ouverte) ;
- pas d'en-tête `List-Unsubscribe` sur les envois groupés (à envisager si le volume
  dépasse les seuils des messageries) ;
- bundle initial du portail : 369,8 ko pour un avertissement à 365 ko (368,9 ko à la fin
  de L7).

**Ouverts depuis les lots précédents** : Q7, Q8, Q14, Q17 ; transition
`ACCEPTED_MINOR → WITHDRAWN` ; « Mon programme » du participant (J15) ; démos D à I sur
o2switch (lot L9).
