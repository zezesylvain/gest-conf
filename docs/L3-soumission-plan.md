# Lot L3 — Soumission : plan d'implémentation

> **Statut : proposition à valider** (5 octobre 2026). Ce lot touche le modèle de données, les
> droits et le workflow des statuts : rien n'est codé avant validation (`CLAUDE.md`).
>
> Sources :
> - étude §4 M4, §5.1, §6 (RG-01, RG-02, RG-04, RG-17, RG-18, RG-19), §8.2, §9.2, §9.3,
>   §10.1, §14 (L3 : 12 à 16 j-h), §15, A2 ;
> - mises à jour §17 (L1) et §18 (L2) ;
> - plan L1, §1.3 (reports vers L3) et D7, D16, D18.

## En bref

| | |
|---|---|
| **Objectif** | Un auteur connecté prépare une soumission en brouillon (sauvegarde automatique), renseigne métadonnées, auteurs, fichier et déclarations, la soumet (référence `GC27-0001`, accusé de réception), la modifie jusqu'à la clôture et suit son statut. La gestion voit les soumissions et accorde des dérogations après clôture. |
| **Workflow** | Service unique `transition(submission, to_state, actor)` avec la **table complète** des statuts de l'étude (§5.1). L3 n'active que `DRAFT → SUBMITTED`, `SUBMITTED → SCREENING` (à la clôture) et le retrait ; les autres transitions arrivent en L4 et après. |
| **Point dur** | Le double aveugle se prépare ici : le fichier servi aux relecteurs (L4) est déposé, contrôlé et **nettoyé de ses métadonnées** dès L3. |
| **Hors périmètre** | Recevabilité, affectation, évaluation, décision (L4) ; version finale et réponse aux relecteurs (L4) ; invitation des co-auteurs avec accès à la soumission (P2) ; contrôle d'anonymisation assisté (P2) ; similarité (P3). |
| **Charge** | **16 à 19,5 j-h** (étude : 12 à 16). Détail au §8. |
| **Démo D** | Une autrice crée un brouillon, quitte la page et le retrouve, ajoute deux co-auteurs, dépose un PDF dont les métadonnées sont retirées, soumet et reçoit l'accusé `GC27-0001`. Elle modifie le titre avant clôture : la révision est conservée. Après la clôture, la modification est refusée ; le président accorde une dérogation de 48 h, journalisée. Dans la gestion, le président voit la liste filtrée ; un membre du CO voit les mêmes métadonnées. |

## 1. Périmètre

### 1.1 Fonctions de M4

| Fonction (M4) | Prio. | L3 |
|---|---|---|
| Brouillon avec sauvegarde automatique | P1 | Oui |
| Titre, résumé (limite de mots), mots-clés, thématique, type, langue | P1 | Oui |
| Auteurs et co-auteurs (ordre, affiliation, correspondant, présentateur) | P1 | Oui, en données (F5) |
| Invitation des co-auteurs sans compte | P2 | Non (information par e-mail seulement, F5) |
| Dépôt de fichiers (PDF ; anonymisé si double aveugle ; annexes) | P1 | PDF principal ; annexes non (F2) |
| Déclarations (originalité, éthique, conflits, publication) | P1 | Oui (F7) |
| Soumission définitive, accusé de réception, référence | P1 | Oui |
| Modification jusqu'à la clôture, versions conservées ; retrait motivé | P1 | Oui (F3) |
| Contrôles : taille et type, mots, doublons, métadonnées PDF | P1 | Oui ; contrôle assisté du texte : P2 |
| Version finale, réponse aux relecteurs | P1 | L4 |
| Rappel avant clôture (brouillons) | P1 (A2) | Oui (F13) |
| Notifications dans l'application (cloche) | P1 (M12) | Oui, minimales (F13) |

### 1.2 Reports de L1 et L2 traités ici

| Report | Origine | Traitement |
|---|---|---|
| Compteurs de numérotation | L1 §1.3 | Table `core.Counter`, verrouillée en transaction (F4) |
| Stockage privé des fichiers | L1 §1.3 | `GESTCONF_PRIVATE_FILES_DIR`, distinct des fichiers publics (F2) |
| Formats et article complet par type ; langues des soumissions | L1 §1.3, Q5, Q6 | Colonnes de `SubmissionType` et d'`Edition` (F1, F11) |
| `Consent.edition` | L1 §1.3 | Non nécessaire : les déclarations sont propres à la soumission (F7) |
| RG-19 : gel de `double_blind` et du code | L1 §1.3 | Gel dès qu'une soumission existe (F9) |
| Rôle `AUTHOR` | D7 | Attribué au premier brouillon |
| Anti-robots | D16 | À trancher (F12) |
| Notifications dans l'application | L1 §1.3 | Minimales (F13) |
| E2E Playwright | L1 §1.3 | Parcours auteur dans la CI (F14) |
| Déploiement continu | D18 | Hors lot ; à décider avant l'ouverture de l'appel (§10) |

## 2. Décisions à valider

### 2.1 Tableau

| # | Question | Recommandation |
|---|---|---|
| F1 | Résumé seul ou article complet (Q5) ? | **Par type de communication** : résumé toujours ; fichier PDF « aucun », « facultatif » ou « obligatoire » ; taille maximale (défaut 10 Mo) |
| F2 | Fichiers et double aveugle | **Un seul PDF principal** par soumission, versionné. En double aveugle, ce PDF **est** la version anonyme (consigne affichée), et le serveur retire ses métadonnées (`pypdf`, Python pur). Pas d'annexe en L3 |
| F3 | Modification après soumission | Jusqu'à la clôture, la soumission reste `SUBMITTED`. Chaque modification enregistrée crée une **révision** (cliché des métadonnées, des auteurs et du fichier courant) ; les fichiers ne sont jamais écrasés |
| F4 | Référence | `GC27-0001`, attribuée à la **première soumission définitive** (pas au brouillon), sans trou ni doublon, conservée en cas de retrait |
| F5 | Co-auteurs | Données saisies par l'auteur, figées dans la soumission (nom, adresse, institution, pays, ordre, correspondant, présentateur). Rattachement au compte quand l'adresse vérifiée correspond. **Information par e-mail** à la soumission (transparence, détection d'adresse erronée). Accès des co-auteurs à la soumission : P2 |
| F6 | Soumissionnaire | Toujours auteur, prérempli depuis son profil (profil complet exigé) ; il peut ne pas être présentateur |
| F7 | Déclarations | Cases propres à la soumission, avec la **version du texte** : originalité, éthique, absence de conflit non déclaré, accord de publication des métadonnées en cas d'acceptation. Toutes obligatoires pour soumettre |
| F8 | Clôture et dérogations (RG-02) | Écriture refusée après `call_close` (heure de l'édition). **Dérogation par soumission**, avec échéance et motif, accordée par `ADMIN`, `CHAIR` ou `SC_CHAIR` ; journalisée |
| F9 | RG-19 | `double_blind` et `code` gelés dès qu'une soumission non brouillon existe ; un `ADMIN` peut forcer, avec motif et audit |
| F10 | Gestion en L3 | Liste et détail (lecture) des soumissions, filtres, export CSV, téléchargement du PDF ; identité visible de `ADMIN`, `CHAIR`, `SC_CHAIR` et du CO (matrice §3.3). `SC_MEMBER` : aucun accès avant L4 |
| F11 | Langues des soumissions (Q6) | `Edition.submission_languages` (défaut : `fr`, `en`) ; langue obligatoire |
| F12 | Anti-robots (D16) | **Pas de captcha en L3** : soumettre exige un compte à adresse vérifiée, et l'inscription est déjà limitée en débit. À réexaminer si des abus apparaissent |
| F13 | Notifications | E-mails : accusé de réception (auteur), information des co-auteurs, retrait, dérogation, rappel des brouillons à J-7 et J-1 de la clôture. **Cloche minimale** (table `Notification`, `/me/notifications`) dans l'espace compte |
| F14 | E2E | Premier test Playwright **dans le dépôt** : parcours auteur complet, lancé en CI |
| F15 | Doublons | Avertissement non bloquant à la soumission (même titre normalisé chez le même soumissionnaire) ; signalés dans la liste de gestion |
| F16 | Anonymisation d'un compte auteur (RG-18) | Brouillons supprimés ; refus tant qu'une soumission non brouillon d'une édition non archivée existe (`account_has_active_duties` étendu) ; la conservation au-delà relève de L8 et de Q14 |
| F17 | Espace auteur | Dans le **portail**, sous `/compte/soumissions` (comme l'espace compte, D11) : jamais pré-rendu |

### 2.2 Le workflow (règle n° 4)

- `apps/submissions/workflow.py` : la **table complète** des transitions de l'étude (§5.1), chacune
  avec ses rôles autorisés et ses gardes ; les transitions non livrées en L3 sont déclarées mais
  refusées (`transition_not_available`).
- `transition(submission, to_state, actor, *, reason="")` est le **seul** chemin qui écrit
  `status`. Il vérifie la légalité, les droits et les gardes. Il écrit `StatusHistory` et le
  journal d'audit, puis programme les notifications (file `Job`), le tout dans une transaction
  avec verrou de ligne (`select_for_update`).
- Un méta-test vérifie qu'aucun module hors `workflow.py` n'affecte `status`.
- Transitions de L3 :

  | De | Vers | Qui | Garde |
  |---|---|---|---|
  | `DRAFT` | `SUBMITTED` | Soumissionnaire | RG-01 ; appel ouvert, ou dérogation en cours |
  | `SUBMITTED` | `SCREENING` | Système (commande de clôture) | `call_close` passée, sans dérogation en cours |
  | `DRAFT`, `SUBMITTED` | `WITHDRAWN` | Soumissionnaire | Motif obligatoire si `SUBMITTED` |

- **Clôture** : la commande `close_call`, ajoutée au cron (`deploy/cron.sh`), est idempotente et verrouillée.
  Elle fait passer en `SCREENING` les soumissions `SUBMITTED` de chaque édition dont la clôture
  est passée, sauf celles qui ont une dérogation en cours (traitées à son échéance).

### 2.3 Fichier PDF (règle n° 8, sans adaptation)

- Stockage hors racine web (`GESTCONF_PRIVATE_FILES_DIR`), nom aléatoire (UUID), empreinte
  SHA-256. Servi par un endpoint authentifié, `Content-Disposition: attachment`, `nosniff`.
- Contrôles :
  - signature `%PDF-` ; analyse par `pypdf`, avec un délai et un nombre de pages bornés ;
  - PDF chiffré refusé ; taille maximale du type ;
  - nombre de pages affiché à l'auteur.
- **Double aveugle** : réécriture par `pypdf` sans dictionnaire `/Info` ni métadonnées XMP. Le
  fichier stocké est la version nettoyée ; l'original n'est pas conservé. Un PDF que `pypdf` ne
  sait pas réécrire est refusé, avec un message clair.
- Vérification préalable en L3.0 : `pypdf` sur un jeu de PDF réels (LaTeX, Word,
  LibreOffice), et absence de métadonnées après réécriture, contrôlée avec un second outil.

## 3. Modèle de données (app `submissions`, additif)

| Table | Champs principaux | Remarques |
|---|---|---|
| `submission` | `edition`, `reference` (nullable, unique), `submitter`, `track`, `submission_type`, `language`, `title`, `abstract`, `keywords` (JSON, 1 à 6), `status`, `submitted_at`, `withdrawn_at`, `withdraw_reason`, `revision` (entier), `declarations` (JSON versionné) | Index (`edition`, `status`) ; `requested_format` = type, `assigned_format` en L4 |
| `submission_author` | `submission`, `position`, `user` (nullable), `first_name`, `last_name`, `email`, `institution`, `country`, `is_corresponding`, `is_presenter` | Unicité (`submission`, `position`) et (`submission`, `email`) ; au moins un correspondant (RG-01) |
| `submission_file` | `submission`, `kind` (`main` ; `camera_ready` en L4), `version`, `storage_name`, `original_name`, `size`, `sha256`, `pages`, `metadata_removed`, `is_current`, `uploaded_by` | Jamais supprimé tant que la soumission existe |
| `submission_revision` | `submission`, `number`, `at`, `actor`, `snapshot` (JSON) | Révisions après la soumission (F3) |
| `status_history` | `submission`, `from_status`, `to_status`, `actor`, `reason`, `at` | Ajout seul |
| `submission_extension` | `submission`, `until`, `reason`, `granted_by`, `granted_at`, `revoked_at` | RG-02 |
| `core_counter` | `scope` (unique, ex. `submission:GC27`), `value` | `select_for_update` |
| `notification` | `user`, `kind`, `payload` (JSON), `read_at` | Cloche (F13) |
| `submission_type` | + `file_policy` (`none`, `optional`, `required`), `max_file_mb` | F1 |
| `edition` | + `submission_languages` (JSON) | F11 |

- Registre des données personnelles : auteurs (y compris tiers), révisions, fichiers,
  notifications ; export et anonymisation. Le test de balayage est étendu.
- Contrôles d'intégrité (`check_integrity`) : fichier courant unique, fichier manquant sur le
  disque, référence sans trou.

## 4. API

**Auteur** (connecté, adresse vérifiée, profil complet pour créer) :
- `GET/POST /v1/submissions?edition=` (les siennes) ; `GET/PATCH/DELETE /v1/submissions/{id}`
  (`DELETE` : brouillon seul) ; `If-Match` sur `revision` contre les écritures concurrentes
  (deux onglets), avec un 412 explicite.
- `PUT /v1/submissions/{id}/authors` (liste complète, ordonnée).
- `POST/GET /v1/submissions/{id}/file` (multipart) ; `GET …/file/content`.
- `GET /v1/submissions/{id}/check` : ce qui manque pour soumettre (RG-01), sans rien écrire.
- `POST /v1/submissions/{id}/submit`, `POST …/withdraw`, `GET …/timeline`.
- `GET /v1/me/notifications`, `POST /v1/me/notifications/read`.

**Gestion** (`ManageViewSet`, 2FA) : `…/manage/editions/{id}/submissions` (liste paginée,
filtres statut, thématique, type, langue, doublons ; export CSV), détail, fichier,
`…/submissions/{id}/extensions` (accorder ou révoquer).

Capacités nouvelles :

| Capacité | Rôles |
|---|---|
| `submissions.read` | `ADMIN`, `CHAIR`, `SC_CHAIR`, `OC_MEMBER` |
| `submissions.extend` | `ADMIN`, `CHAIR`, `SC_CHAIR` |
| `submissions.export` | `ADMIN`, `CHAIR`, `SC_CHAIR` |

L'export est journalisé (RG-17 : « export de masse »). La matrice des droits est étendue,
avec un test par case, dont « un auteur ne voit pas la soumission d'un autre (404) ».

**Double aveugle préparé pour L4** : les sérialiseurs de gestion sont nommés par rôle dès L3
(`SubmissionManageSerializer`). Le sérialiseur relecteur (`SubmissionReviewerSerializer`,
sans auteurs ni métadonnées de fichier) et ses tests RG-04 sont écrits en L4, avec le premier
endpoint relecteur.

## 5. Frontend

**Portail, espace auteur** (`/compte/soumissions`, rendu navigateur) :
- liste de ses soumissions (statut, référence, échéance de modification) ;
- **assistant en 5 étapes** : informations → auteurs → fichier → déclarations → récapitulatif
  et soumission ;
  - sauvegarde automatique (anti-rebond, indicateur « enregistré à… ») ;
  - compteur de mots ;
  - liste « ce qui manque » lue sur `check` ;
- suivi : frise des statuts (libellés de l'étude M6), révisions, retrait motivé ;
- cloche dans l'en-tête de l'espace compte.

**Gestion** :
- rubrique « Soumissions » : liste filtrée, détail (métadonnées, auteurs, fichier,
  historique), dérogations, export ;
- tableau de bord : compteurs par statut ;
- entrées dans `core/navigation.ts` et fiches d'aide (règle de L2).

## 6. Sécurité et données personnelles

- Querysets filtrés par rôle : un auteur n'interroge que ses soumissions (404 sinon) ; la
  gestion seulement dans ses éditions.
- Fichiers privés : endpoint authentifié, aucun accès par Apache ; métadonnées retirées en
  double aveugle.
- Limites de débit : création de soumission, dépôt de fichier, soumission.
- Données de tiers (co-auteurs) : information par e-mail (F5), export et anonymisation par le
  registre ; adresses jamais dans le journal en clair.
- RG-02 et RG-19 journalisés ; toute écriture après clôture passe par une dérogation.

## 7. Tests

- **Backend** :
  - workflow : table complète, transitions refusées, gardes, historique, méta-test
    « `status` écrit seulement par `workflow.py` » ;
  - tests RG-01, RG-02, RG-19 (nom ou docstring) ;
  - numérotation concurrente (MariaDB, deux transactions) ;
  - PDF : chiffré, faux PDF, métadonnées retirées, taille ;
  - révisions, retrait, dérogations, clôture idempotente ;
  - matrice des droits ; registre et balayage ; e-mails.
- **Frontend** : assistant (sauvegarde automatique, conflit 412, compteur de mots, liste des
  manques), frise, liste de gestion.
- **E2E** (Playwright, CI) : inscription → profil → brouillon → co-auteurs → PDF →
  déclarations → soumission → accusé (e-mail en console) → modification → clôture simulée →
  refus.

## 8. Étapes

| Étape | Contenu | Critère de fin | Charge |
|---|---|---|---|
| L3.0 | Vérifications : `pypdf` (réécriture sans métadonnées sur des PDF réels), stockage privé, Playwright en CI | Rapport ; F2 et F14 confirmées | 1 |
| L3.1 | Modèle, compteur, workflow et `transition`, RG-19, registre | Tests du workflow au vert | 3 – 3,5 |
| L3.2 | API auteur : brouillons, auteurs, fichier, `check`, soumission (RG-01), révisions, retrait, RG-02 et dérogations, e-mails | Tests RG-01, RG-02, matrice | 3,5 – 4 |
| L3.3 | Espace auteur du portail : liste, assistant, suivi, cloche | Démo D côté auteur dans Chromium | 4 – 5 |
| L3.4 | Gestion : soumissions, détail, dérogations, export, tableau de bord, aide ; clôture `close_call` | Démo D côté gestion | 2,5 – 3 |
| L3.5 | Rappels des brouillons, doublons, notifications | Tests d'idempotence des rappels | 1 |
| L3.6 | E2E en CI, recette, documentation, étude (§19) | Démo D sur o2switch | 1 – 2 |
| **Total** | | | **16 – 19,5** |

## 9. Risques et hypothèses non vérifiées

| Risque | Mesure |
|---|---|
| `pypdf` ne réécrit pas certains PDF, ou laisse des métadonnées | L3.0 sur un jeu réel ; refus explicite plutôt que fichier non nettoyé |
| Pic de charge à la clôture (§14.4) | Sauvegarde automatique légère, limites de débit, test de charge en L9 ; dérogations plutôt que report global |
| Pertes d'écriture entre deux onglets | `If-Match` sur `revision`, 412 explicite |
| Texte de la notice et des déclarations non définitifs (Q14) | Versions « v0 » ; **l'ouverture réelle de l'appel reste bloquée** jusqu'aux textes définitifs |
| Fournisseur d'e-mails de production non choisi (D10) | Accusés en file ; aucun envoi réel sans fournisseur configuré |
| Déploiement manuel pendant l'appel (D18) | Décision à prendre avant l'ouverture de l'appel |

## 10. Questions au commanditaire

1. Validation de F1 à F17, en particulier :
   - F1 (résumé seul ou article, par type) ;
   - F2 (un seul PDF, anonyme en double aveugle) ;
   - F5 (information des co-auteurs par e-mail) ;
   - F8 (qui accorde les dérogations) ;
   - F12 (pas de captcha) ;
   - F16 (anonymisation refusée tant qu'une soumission est active).
2. Q3 (double aveugle activé par défaut), Q5 (formats, limites, modèles), Q6 (langues des
   soumissions).
3. Textes définitifs : notice d'information et déclarations ; fournisseur d'e-mails ;
   déploiement continu (D18) avant l'ouverture de l'appel.
4. Charge de 16 à 19,5 j-h, contre 12 à 16 dans l'étude.
