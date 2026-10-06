# Lot L4 — Évaluation et décision : bilan et exploitation

Ce document résume ce que livre le lot L4 de GEST-CONF et comment l'exploiter. Le détail des
choix, des vérifications et des défauts trouvés est dans
[`L4-evaluation-plan.md`](L4-evaluation-plan.md) (décisions H1 à H19 au §2, bilans des étapes
aux §11 à §18). L'étude est mise à jour en conséquence (§20 « Mises à jour issues du lot L4 »).

## 1. Ce qui est livré

| Étape | Contenu | Commit |
|---|---|---|
| L4.0 | Garde-fous RG-04 (registre, liste blanche, méta-test, test de fuite), capacités, 2FA des relecteurs | `1f2c954` |
| L4.1 | Grilles (RG-05), modèle de l'évaluation, calcul de la note pondérée | `4ee37e9` |
| L4.2 | Recevabilité, affectations, conflits (RG-03), charge, échéances, relances | `e50a46d` |
| L4.3 | Espace relecteur (API), RG-06, RG-07, discussion (RG-08), divergence | `d79af79` |
| L4.4 | Décisions, publication (RG-09, RG-10), version finale, classement, export | `35a1822` |
| L4.5 | Écrans de la gestion : relecteur, pilotage, classement, grilles, tableau de bord, aide | `a15829e` |
| L4.6 | Espace auteur du portail : décision publiée, commentaires, version finale | `5bcf45f` |
| L4.7 | Parcours de bout en bout en CI, recette, bilan, étude (§20), `CLAUDE.md` | ce lot |

## 2. Parcours couverts

- **Relecteur** (`SC_MEMBER`, `SC_CHAIR`), dans la gestion, rubrique « Évaluations », 2FA
  imposée :
  - « Mes évaluations » : échéances, statut, retards ;
  - formulaire d'évaluation :
    - soumission anonymisée et PDF nettoyé ;
    - grille pondérée, avec une note **indicative** calculée pendant la saisie (le serveur
      la recalcule et fait foi) ;
    - recommandation, confiance, commentaires aux auteurs et au comité, signalements ;
  - brouillon, envoi, renvoi jusqu'à la décision (RG-06) ;
  - refus motivé, avec conflit d'intérêts déclaré ou non ;
  - discussion sous pseudonymes une fois son évaluation envoyée (RG-08) ;
  - thématiques d'expertise.
- **Président du CS** (et `CHAIR`), rubriques « Pilotage » et « Classement » :
  - avancement (par relecteur, par thématique, retards, divergences) ;
  - recevabilité : rejet motivé, ou ouverture de l'évaluation une fois les relecteurs requis
    affectés ;
  - affectation parmi les candidats (charge, expertises, conflits), levée motivée d'un
    conflit levable, annulation, nouvelle échéance ;
  - évaluations nominatives, ouverture de la discussion, messages ;
  - décision individuelle, ou en lot selon une simulation de seuil ;
  - publication confirmée ; acceptation depuis la liste d'attente ;
  - export CSV des évaluations ;
  - grilles : création, modification tant que non verrouillée, duplication en nouvelle
    version (RG-05).
- **Auteur** (portail, `/compte/soumissions/:id`) :
  - décision publiée, format attribué, message du comité ;
  - commentaires des relecteurs sous pseudonymes (RG-10) ;
  - dépôt de la version finale et de la lettre de réponse jusqu'à la date `camera_ready` ;
  - retrait d'une communication acceptée.
- **Opérateur** : `remind_reviewers`, qui relance à J-7, J-1 et au premier jour de retard.

## 3. Sécurité et données personnelles, en bref

- **Double aveugle (RG-04)** :
  - sérialiseurs relecteur construits par liste blanche, sur un registre des champs
    d'identité ;
  - un méta-test refuse tout champ qui y mène ;
  - un **test de fuite** parcourt chacune des 9 routes relecteur avec des traceurs, erreurs
    comprises. Une route `reviewer-…` non testée fait échouer la suite.
  - Le parcours de bout en bout vérifie aussi, dans le navigateur du relecteur, l'absence des
    noms, de l'adresse et de l'institution des auteurs.
- **RG-03** :
  - un relecteur ne voit que ses affectations actives, sans conflit ; sinon 404 ;
  - conflit d'auteur jamais levable ;
  - même institution et conflit déclaré levables, avec un motif, une réauthentification
    récente et une entrée au journal.
- **RG-10** :
  - l'auteur ne reçoit ni le nom des relecteurs, ni leurs notes, ni les commentaires au comité ;
  - des tests le vérifient sur l'API, les e-mails et la page du portail (traceurs).
- **Droits** :
  - capacités `reviews.write`, `reviews.manage`, `reviews.read_all`, `decisions.decide`,
    `decisions.publish`, `grids.write` ;
  - capacités revérifiées par le workflow, au-delà de la vue ;
  - le CO n'a aucun accès aux évaluations.
- **Réauthentification récente** : publication des résultats, export CSV, levée d'un conflit.
  Ces actions sont journalisées (RG-17).
- **Données personnelles** : registre étendu aux relecteurs et aux lettres de réponse.
  - L'anonymisation d'un relecteur est refusée tant qu'une évaluation est en cours.
  - Ensuite, l'évaluation est conservée sans nom.

## 4. Exploitation

- **Cron**, à ajouter dans cPanel (voir [`deploy/README.md`](../deploy/README.md)) :

  ```text
  19 * * * *   $HOME/gestconf-app/deploy/cron.sh remind_reviewers
  ```

- **Avant d'ouvrir l'évaluation d'une édition** :
  - créer la grille (par défaut celle de l'étude : 25/30/15/15/15, échelle 0 à 5) ;
  - régler le nombre de relecteurs par soumission, la charge maximale, le seuil de divergence
    et la note finale pondérée par la confiance (« Paramétrage › Confidentialité », `ADMIN`
    ou `CHAIR`) ;
  - saisir les dates clés `review_deadline` (échéance par défaut des affectations) et
    `camera_ready` (fin du dépôt des versions finales).
- **Comité scientifique** : chaque relecteur active sa 2FA à sa première connexion
  (`SC_MEMBER` rejoint `MFA_REQUIRED_ROLES`, H2). En cas de perte, `reset_mfa`.
- **Liens des e-mails** :
  - relecteurs : `/gestion/editions/{id}/evaluations/{affectation}` ;
  - président : `/gestion/editions/{id}/pilotage/{soumission}`.
- **Publication des résultats** : irréversible. Une erreur se corrige par une décision
  individuelle (acceptation depuis la liste d'attente) et un nouvel e-mail.
- **Contrôles d'intégrité** (`check_integrity`) :
  - poids des grilles égaux à 100, note stockée égale à la note recalculée ;
  - clé d'affectation active cohérente avec le statut ; aucune affectation active d'un
    relecteur auteur de la soumission.

## 5. Tests

- **Backend** : 2 073 tests sous SQLite, 2 080 sous MariaDB. Ils couvrent notamment :
  - calcul de la note (exemple de l'étude : 3,70 / 5 → 74,00), RG-05 (somme, verrou,
    duplication) ;
  - recevabilité, conflits, charge, concurrence des affectations, relances idempotentes ;
  - RG-06, RG-07, RG-08, divergence ; décisions, publication (RG-09), RG-10, version finale ;
  - RG-04 : méta-test et test de fuite sur toutes les routes relecteur ;
  - matrice des droits : 1 188 cas.
- **Front (Vitest)** : 302 tests (portail 116, gestion 110, shared 76) et 11 tests des scripts
  de build.
- **Bout en bout (Playwright, CI)** : un parcours en série, sur une base créée pour la série.
  - Auteur : inscription, soumission, révision, clôture, recevabilité (L3).
  - Président du CS, dans la gestion, connecté avec sa 2FA : affectation de deux relecteurs,
    ouverture de l'évaluation.
  - Relecteurs : deux évaluations sans identité des auteurs (RG-04), passage automatique en
    « évaluée » (RG-07).
  - Président : décision provisoire, invisible de l'auteur, puis publication (RG-09).
  - Auteur : décision et commentaires sous pseudonymes, sans commentaire confidentiel (RG-10).
    Lettre de réponse exigée, version finale déposée et téléchargeable (H18).
  - Les e-mails attendus et les statuts sont contrôlés en base.
- **Recette locale dans Chromium** :
  - écrans du relecteur, du président et des grilles (L4.5) ;
  - espace auteur (L4.6), en français et en anglais ;
  - à 375 px, aucun débordement ; aucune erreur dans la console.

## 6. Ce qui reste à faire ou à décider

**Avant la campagne d'évaluation réelle** :

- démo E sur o2switch, avec la ligne de cron `remind_reviewers` ;
- enrôlement 2FA des relecteurs (une étape par relecteur) ;
- grille et pondérations définitives (Q4) ;
- fournisseur d'e-mails de production (D10).

**Décisions du commanditaire** :

- Q3 (niveau de double aveugle) et Q4 (relecteurs par soumission, échelle, pondérations) : les
  valeurs par défaut s'appliquent en attendant ;
- mise à jour de l'étude sur `REVISION_REQUESTED` (§20.2) : non utilisé, `accepted_minor`
  couvre les corrections demandées ;
- budget du bundle initial du portail : 367,7 kB pour un avertissement à 365 kB (inchangé).

**Reporté (P2)** :

- suggestions d'affectation et mots-clés d'expertise ;
- validation des décisions par le Chair ;
- export PDF des évaluations ;
- contrôle de l'identité dans le texte du PDF.

**Pour L5 (programme)** : formats attribués, soumissions acceptées et versions finales servent
d'entrée au programme. Un plan L5 est à proposer et à faire valider.
