# Lot L4 — Évaluation et décision : plan d'implémentation

> **Statut : proposition à valider** (5 octobre 2026). Ce lot touche le modèle de données, les
> droits et le workflow des statuts : rien n'est codé avant validation (`CLAUDE.md`).
>
> **Ordre des lots** : L4 démarre à la demande du commanditaire alors que L3 n'est pas clos.
> Le serveur de L3 est livré (modèle, workflow, API auteur). Restent L3.3 à L3.6 : espace auteur
> du portail, écrans de gestion des soumissions, rappels, E2E. Voir H17 pour l'articulation.
>
> Sources :
> - étude §3.3 (matrice), §4 M5 et M6, §5.1 et §5.2, §6 (RG-03 à RG-10, RG-17), §8.2
>   (« Évaluation »), §9.2, §10.2, §15 (Q3, Q4, Q16), A2, A3 (US-03 à US-06) ;
> - mises à jour §17 (L1) et §18 (L2) ;
> - plan L1 §1.3 et §5.4 (préparation de RG-04 reportée en L4, D3 pour `SC_MEMBER`) ;
> - plan L3 §12 (écart `REVISION_REQUESTED`).

## En bref

| | |
|---|---|
| **Objectif** | Le président du CS contrôle la recevabilité, affecte les relecteurs (conflits exclus), suit l'avancement ; les relecteurs évaluent selon une grille pondérée (score calculé par le serveur), sans jamais voir l'identité des auteurs en double aveugle ; après discussion, le président classe, simule un seuil, décide et publie les résultats ; les auteurs reçoivent décision et commentaires, puis déposent leur version finale. |
| **Point dur** | **RG-04** : aucun endpoint relecteur ne doit renvoyer une donnée d'identité. Registre des champs d'identité, sérialiseurs dédiés, méta-test et test de fuite sur **toutes** les réponses relecteur, avant le premier endpoint. |
| **Hors périmètre** | Suggestions d'affectation et enchères (P2, US-05), export PDF des évaluations (P2), cloche de notifications (L3.5), validation des décisions par le Chair (P2, H13), similarité/plagiat (P3). |
| **Charge** | **24 à 30,5 j-h** (étude : 18 à 24). Détail au §8. |
| **Démo E** | Le président déclare 4 soumissions recevables, en rejette une (motif), affecte 2 relecteurs chacune : le système refuse un relecteur co-auteur et un relecteur de la même institution. Une relectrice déclare un conflit et se retire. Les relecteurs notent (score en direct), une divergence de 40 points est signalée, la discussion s'ouvre, une note est révisée. Le président simule un seuil à 70, décide en lot, publie : les auteurs reçoivent décision et commentaires anonymes ; l'un dépose sa version finale. Un relecteur n'a vu, à aucun moment, ni nom ni affiliation (vérifié par le test de fuite sur toutes ses réponses). |

## 1. Périmètre

### 1.1 Fonctions de M5 et M6

| Fonction | Prio. | L4 |
|---|---|---|
| Grille par édition et par type, poids = 100 (RG-05), versions verrouillées | P1 | Oui (H3) |
| Note pondérée par le serveur, score final, option pondération par la confiance | P1 | Oui (H4) |
| Recommandation, confiance, commentaires aux auteurs et au comité | P1 | Oui |
| Signalements d'éthique, de plagiat, suggestion de format | P1 (facultatifs) | Oui |
| Recevabilité (SCREENING → UNDER_REVIEW ou REJECTED motivé) | P1 | Oui (H10) |
| Affectation manuelle, charge maximale, échéance, relance, remplacement | P1 | Oui (H6, H15) |
| Affectation assistée (mots-clés, thématiques, charge) ; enchères | P2 ; P3 | Non |
| Conflits : déclaration, détection même établissement et co-auteurs | P1 | Oui (H8) |
| Double aveugle (RG-04, RG-10) | P1 | Oui (H9) |
| Tableau de bord du président, divergence, discussion (RG-08) | P1 | Oui (H12, H13) |
| Modification après envoi, historique (RG-06) ; REVIEWED (RG-07) | P1 | Oui |
| Classement et simulation de seuil (US-06) ; export CSV | P1 | Oui ; PDF : P2 |
| Décisions individuelles ou en lot, format attribué, publication (RG-09) | P1 | Oui (H16) |
| Validation par le Chair « si la politique l'impose » | P1 conditionnel | Non en L4 (H16) |
| Notification groupée des auteurs, commentaires anonymes | P1 | Oui |
| Version finale ; réponse aux relecteurs | P1 (M4 point 8) | Oui (H18) |

### 1.2 Reports traités ici

| Report | Origine | Traitement |
|---|---|---|
| Préparation de RG-04 : registre `IDENTITY_FIELDS`, sérialiseur anonymisé, méta-test, `assert_no_identity_leak` | Plan L1 §1.3, §5.4 | L4.0, avant tout endpoint relecteur (H9) |
| 2FA des relecteurs (`SC_MEMBER`) | D3 | À trancher : H2 |
| Expertises des relecteurs, en relationnel | Plan L1 §3.3 | Thématiques de compétence par édition (H7) |
| Seuils, charge maximale, RG-07 | Plan L1 §1.3 | Colonnes typées de l'édition (H4, H6, H12) |
| Conflit `SC_MEMBER` également `AUTHOR` | Plan L1 §5.5 | Exclusion automatique (H8) |
| Statut `REVISION_REQUESTED` sans transition | Plan L3 §12 | H16 |
| Indicateurs du tableau de bord (US-12) | Plan L1 §1.3 | Compteurs d'évaluation (L4.5) |

## 2. Décisions à valider

| # | Question | Recommandation |
|---|---|---|
| H1 | Où est l'espace évaluateur (Q16) ? | Dans l'application **`gestion`** (proposition de l'étude) : rubrique « Évaluations », 2FA, rail et aide de L2 |
| H2 | 2FA pour `SC_MEMBER` (D3) ? | **Oui, imposée** : un relecteur voit des travaux inédits ; la ligne s'ajoute à `MFA_REQUIRED_ROLES`. Coût : une étape d'enrôlement pour chaque relecteur |
| H3 | Grille | Par édition, et **facultativement par type** (sinon grille de l'édition). Critères bilingues, poids décimaux dont la somme vaut exactement 100 (RG-05), échelle par grille (défaut 0–5), critères obligatoires ou non. **Verrouillée dès la première évaluation enregistrée** ; « dupliquer en nouvelle version » ; les évaluations gardent la version utilisée. Grille par défaut de l'étude (25/30/15/15/15) proposée à la création |
| H4 | Calcul | Note pondérée d'une évaluation ramenée sur 100, en `Decimal` (2 décimales, arrondi au plus proche, demi supérieur), calculée **par le serveur** à chaque enregistrement ; les critères facultatifs non notés sont exclus du calcul (poids renormalisés). Score final : moyenne simple des évaluations envoyées ; **option par édition** : moyenne pondérée par la confiance (désactivée par défaut) |
| H5 | Recommandation | `accept`, `accept_minor`, `reject`, `discuss` ; confiance 1–5 ; commentaire aux auteurs (obligatoire à l'envoi) et au comité (facultatif) ; signalements éthique et plagiat ; format suggéré (type de communication) |
| H6 | Affectation | **Manuelle** par le président du CS (et le Chair) ; refus au-delà de la **charge maximale** par relecteur (paramètre de l'édition, défaut 10) ; échéance par défaut = date clé `review_deadline` (modifiable) ; suggestions automatiques : P2 |
| H7 | Expertises | Thématiques de compétence déclarées par le relecteur pour l'édition (table relationnelle) ; affichées au président lors de l'affectation, filtrables. Mots-clés libres : P2, avec les suggestions |
| H8 | Conflits | **Bloquants sans exception** : le relecteur est auteur de la soumission (compte ou adresse). **Bloquant, levable par le président avec motif journalisé** : même institution (comparaison normalisée du profil et des affiliations des auteurs), conflit déclaré par le relecteur. Un relecteur en conflit ne voit ni la soumission ni la discussion ; tout conflit est journalisé |
| H9 | RG-04 | Sérialiseurs **relecteur** distincts, construits par **liste blanche** ; registre des champs d'identité (compte, profil, auteurs, nom d'origine et métadonnées du fichier, clichés de révision, historique) ; méta-test : aucun sérialiseur relecteur n'expose un champ du registre ; **test de fuite** : chaque endpoint relecteur, avec des auteurs aux noms et adresses traceurs, ne renvoie aucun traceur, en double aveugle. Fichier servi : version courante nettoyée en L3, nom de téléchargement générique (`GC27-0001.pdf`). Édition **sans** double aveugle (Q3) : sérialiseur avec auteurs, choisi par le serveur selon `double_blind` |
| H10 | Recevabilité | Par le président du CS (et le Chair) : `SCREENING → REJECTED` avec motif (notifié immédiatement, étude §5.2) ; `SCREENING → UNDER_REVIEW` quand le nombre de relecteurs requis (`reviewers_per_submission`) est affecté. La fonction « secrétariat » du CO (Q12) n'a pas de droit en L4 |
| H11 | Identité des relecteurs | Jamais vue des auteurs (RG-10) ; **pseudonymes** (« Relecteur 1, 2 ») entre relecteurs d'une même soumission ; noms visibles du président et du Chair |
| H12 | Discussion (RG-08) et divergence | Discussion par soumission, ouverte **automatiquement** quand toutes les évaluations sont envoyées, ou par le président ; un relecteur ne voit les autres évaluations qu'après avoir envoyé la sienne **et** discussion ouverte. Divergence : écart maximal entre notes pondérées > seuil de l'édition (défaut 30 points sur 100) → signalée au tableau de bord et par e-mail au président ; aucune action automatique |
| H13 | Modification après envoi (RG-06) | Possible jusqu'à la décision ; chaque envoi crée une version (historique en ajout seul) ; le score est recalculé |
| H14 | REVIEWED (RG-07) | Transition **automatique** (système) quand le nombre requis d'évaluations est envoyé ; l'affectation d'un relecteur supplémentaire ne fait pas revenir en arrière |
| H15 | Échéances et relances | Relances à J-7 et J-1 et au premier jour de retard, une seule fois chacune (commande cron idempotente) ; remplacement manuel par le président (affectation annulée avec motif) |
| H16 | Décisions | Le président du CS (ou le Chair) enregistre une décision **provisoire** : issue (`accepted`, `accepted_minor`, `waitlist`, `rejected`) et format attribué ; individuelle ou en lot. **Publication des résultats** par le président : transitions de statut et e-mails à ce moment seulement (RG-09). `REVISION_REQUESTED` : **non utilisé**, `accepted_minor` couvre les « corrections demandées » (proposition de mise à jour de l'étude). Validation par le Chair : P2, non livrée. `WAITLIST → ACCEPTED` après publication, par le président |
| H17 | Ordre avec L3 | Livrer d'abord le **serveur** de L4 (L4.0 à L4.4), puis finir **L3.3 à L3.6** (l'E2E auteur en dépend), puis les écrans de L4 (L4.5, L4.6) et l'E2E « auteur → évaluation → décision » (L4.7) |
| H18 | Version finale | Pour `accepted` et `accepted_minor` : dépôt du PDF final **nominatif** (non nettoyé) jusqu'à la date clé `camera_ready`, avec lettre de réponse aux relecteurs (texte, obligatoire pour `accepted_minor`) ; `→ CAMERA_READY_RECEIVED`. Contrôle de la mise en page : non |
| H19 | Droits | Nouvelles capacités : `reviews.write` (relecteur : `SC_MEMBER`, `SC_CHAIR`), `reviews.manage` (recevabilité, affectations, conflits, suivi : `SC_CHAIR`, `CHAIR`, `ADMIN`), `reviews.read_all` (évaluations de tous : `SC_CHAIR`, `CHAIR`, `ADMIN`), `decisions.decide` (`SC_CHAIR`, `CHAIR`), `decisions.publish` (`SC_CHAIR`, `CHAIR`), `grids.write` (`ADMIN`, `CHAIR`, `SC_CHAIR`). Le CO n'a aucun accès aux évaluations (matrice §3.3 : « méta, sans notes ») |

## 3. Modèle de données (app `reviews`, additif)

| Table | Champs principaux | Remarques |
|---|---|---|
| `evaluation_grid` | `edition`, `submission_type` (nullable), `version`, `name`, `scale_min`, `scale_max`, `locked_at` | Unicité par clé d'unicité nullable (convention L1 §3.1) : (`edition`, type ou « toutes », `version`) |
| `criterion` | `grid`, `code`, `label_fr/en`, `help_fr/en`, `weight` (DECIMAL 5,2), `position`, `is_required` | Somme des poids = 100 contrôlée par le service ; grille verrouillée → refus |
| `reviewer_track` | `user`, `edition`, `track` | Expertises (H7) |
| `review_assignment` | `submission`, `reviewer`, `assigned_by`, `assigned_at`, `due_at`, `status` (`active`, `declined`, `cancelled`), `reason`, `conflict_override_reason`, `reminders` (JSON), `active_key` | Une affectation active par (soumission, relecteur) : clé d'unicité nullable |
| `review` | `assignment` (1–1), `grid`, `status` (`draft`, `submitted`), `recommendation`, `confidence`, `comment_to_authors`, `comment_to_committee`, `ethics_flag`, `plagiarism_flag`, `suggested_type`, `weighted_score` (DECIMAL 5,2), `submitted_at`, `version` | Score stocké, recalculable (contrôle d'intégrité) |
| `review_score` | `review`, `criterion`, `value` (DECIMAL 4,1) | Unicité (`review`, `criterion`) |
| `review_version` | `review`, `version`, `at`, `snapshot` (JSON) | Ajout seul (RG-06) |
| `conflict_of_interest` | `submission`, `reviewer`, `source` (`reviewer`, `system`, `chair`), `kind` (`author`, `institution`, `declared`), `reason`, `declared_by`, `at`, `overridden_by`, `overridden_reason` | Journalisé |
| `discussion` / `discussion_message` | `submission`, `opened_at`, `opened_by` / `discussion`, `author`, `body`, `at` | Pseudonymes calculés à la lecture |
| `decision` | `submission` (1–1), `outcome`, `assigned_type`, `comment_to_authors`, `decided_by`, `decided_at`, `published_at` | Provisoire tant que `published_at` est nul |
| `final_version` | `submission`, fichier (`SubmissionFile` de nature `camera_ready`), `response_letter`, `at` | H18 |
| `edition` (+) | `max_reviews_per_reviewer` (10), `divergence_threshold` (DECIMAL, 30), `confidence_weighted_score` (non) | Paramètres typés (plan L1 §3.4) |

- Registre des données personnelles : évaluations et messages (le relecteur est une personne), conflits, expertises ; export et anonymisation (une évaluation reste, sans nom ; refus tant qu'une affectation est active, comme F16).
- Contrôles d'intégrité : score recalculé égal au score stocké ; poids = 100 ; une seule affectation active.

## 4. API

**Relecteur** (`…/manage/editions/{id}/reviews/…`, 2FA, `reviews.write`, **ses** affectations seulement, 404 sinon) :
- `GET assignments`, `GET assignments/{a}` : soumission **anonymisée** (titre, résumé, mots-clés, thématique, type, langue, référence), grille, son évaluation ;
- `GET assignments/{a}/file` (nom générique) ; `POST assignments/{a}/decline` (motif ; conflit facultatif) ;
- `PUT assignments/{a}/review` (brouillon, score en retour), `POST …/review/submit` (RG-06) ;
- `GET assignments/{a}/discussion` (autres évaluations pseudonymes et messages, RG-08), `POST …/discussion` ;
- `PUT me/expertise` (thématiques).

**Président du CS / Chair** (`reviews.manage`, `reviews.read_all`, `decisions.*`) :
- `GET review-submissions` (filtres : statut, thématique, type, divergence, retard) ; `POST submissions/{s}/screening` (`admissible` ou `reject` + motif) ;
- `POST/DELETE assignments` (contrôles de conflit et de charge, levée motivée), `GET reviewers` (charge, expertises, conflits) ;
- `GET progress` (par relecteur, par thématique, retards, divergences) ; `POST submissions/{s}/discussion/open` ;
- `GET ranking?threshold=` (classement, simulation : nombre accepté au seuil, par type et thématique) ; `GET evaluations.csv` (journalisé) ;
- `PUT submissions/{s}/decision`, `POST decisions/batch` ; `POST decisions/publish` (réauthentification récente, journalisée) ;
- grilles : `GET/POST grids`, `PATCH grids/{g}` (refus si verrouillée), `POST grids/{g}/duplicate`.

**Auteur** (portail, `/v1/submissions/{id}`) : décision publiée, format attribué, commentaires aux auteurs **pseudonymes** (jamais de note, ni de commentaire confidentiel : RG-10) ; `POST …/final-version` (H18).

La matrice des droits est étendue (un test par case), et le **test de fuite RG-04** couvre chaque route relecteur.

## 5. Frontend

**Gestion — relecteur** (H1) : « Mes évaluations » (liste, échéances, statut) ; formulaire d'évaluation (résumé et PDF à gauche, grille pondérée à droite, **score calculé en direct** côté client à titre indicatif, le serveur faisant foi) ; déclaration de conflit ; discussion ; expertises.

**Gestion — président du CS** : recevabilité ; affectation (relecteurs, charge, expertises, conflits) ; suivi ; classement et simulation ; décisions individuelles et en lot ; publication confirmée ; grilles (paramétrage) ; tableau de bord enrichi (US-12). Chaque écran est inscrit dans le rail et a sa fiche d'aide (règle de L2).

**Portail — auteur** (après L3.3) : décision, commentaires, dépôt de la version finale.

## 6. Sécurité

- RG-04 : liste blanche, registre, méta-test, test de fuite (H9) ; aucun tri ni filtre sur un champ caché (méta-test L1 contre `"__all__"`).
- Querysets relecteur filtrés par affectation active **sans conflit** ; 404 sinon.
- RG-10 : pseudonymes côté auteur et entre relecteurs ; commentaires au comité jamais servis à l'auteur.
- Publication des résultats et export : réauthentification récente, audit (RG-17), y compris la **levée d'un conflit**.
- Scores et poids en `Decimal`, calculés par le serveur ; la valeur envoyée par le client est ignorée.

## 7. Tests

- Unitaires : calcul pondéré (exemple de l'étude : 3,70/5 → 74/100), critères facultatifs, arrondis, moyenne pondérée par la confiance ; RG-05 (somme, verrou, duplication).
- Workflow : RG-07 (REVIEWED automatique), recevabilité, publication (RG-09), liste d'attente.
- Droits : matrice par case ; un relecteur non affecté ou en conflit → 404 ; RG-08.
- RG-04 et RG-10 : test de fuite sur toutes les routes relecteur et auteur (traceurs), en double aveugle et en revue ouverte.
- Relances idempotentes ; divergence ; registre et balayage ; e-mails.
- E2E (L4.7) : soumission → recevabilité → affectation → évaluation → décision → publication → version finale.

## 8. Étapes

| Étape | Contenu | Critère de fin | Charge |
|---|---|---|---|
| L4.0 | RG-04 (registre, sérialiseur de base, méta-test, test de fuite) ; capacités ; 2FA `SC_MEMBER` (H2) | Méta-test et matrice au vert | 1,5 – 2 |
| L4.1 | Grilles (RG-05), modèle d'évaluation, calcul du score | Tests du calcul au vert | 2 – 2,5 |
| L4.2 | Recevabilité, affectations, conflits, charge, expertises, échéances, relances | Tests RG-03 et conflits | 3 – 3,5 |
| L4.3 | API relecteur, RG-06, RG-07, discussion (RG-08), divergence | Test de fuite RG-04 au vert | 3 – 3,5 |
| L4.4 | Classement, simulation, décisions, publication (RG-09, RG-10), e-mails, version finale, export CSV | Tests RG-09 et RG-10 | 3 – 3,5 |
| — | **Fin de L3** (L3.3 à L3.6, H17) | Plan L3 | (8,5 – 11, déjà comptés en L3) |
| L4.5 | Écrans de gestion : relecteur, président, grilles, tableau de bord, aide | Démo E côté gestion | 7 – 9 |
| L4.6 | Portail auteur : décision, version finale | Démo E côté auteur | 1,5 – 2 |
| L4.7 | E2E complet, recette, documentation, étude (§20) | Démo E sur o2switch | 1,5 – 2 |
| **Total L4** | | | **22,5 – 28** (+ marge d'intégration 1,5 – 2,5 → **24 – 30,5**) |

## 9. Risques et hypothèses non vérifiées

| Risque | Mesure |
|---|---|
| Fuite d'identité par un champ oublié ou une route nouvelle | Liste blanche + registre + méta-test + test de fuite sur toutes les routes relecteur |
| Identité dans le **texte** du PDF | Hors contrôle automatique (P2) ; consigne aux auteurs ; signalement possible par le relecteur |
| Pseudonymes réidentifiables par l'ordre d'affectation | Numérotation stable mais aléatoire par soumission |
| Relecteurs sans 2FA (si H2 refusée) | Risque accepté par le commanditaire, consigné |
| Charge des relecteurs mal estimée (Q13) | Charge maximale paramétrable |
| Décisions publiées par erreur | Réauthentification, confirmation, journal ; pas d'annulation de publication (correction par décision individuelle et nouvel e-mail) |

## 10. Questions au commanditaire

1. Validation de H1 à H19, en particulier :
   - H2 (2FA des relecteurs) ;
   - H8 (même institution : bloquant mais levable) ;
   - H11 (pseudonymes entre relecteurs) ;
   - H16 (`REVISION_REQUESTED` abandonné, pas de validation par le Chair en L4) ;
   - H17 (ordre avec la fin de L3).
2. Q3 (niveau de double aveugle) et Q4 (relecteurs par soumission, échelle, pondérations
   définitives) : les valeurs par défaut proposées s'appliquent en attendant.
3. Charge de 24 à 30,5 j-h, contre 18 à 24 dans l'étude.
