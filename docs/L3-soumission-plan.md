# Lot L3 — Soumission : plan d'implémentation

> **Statut : validé le 5 octobre 2026** (décisions F1 à F17 telles que proposées, sans
> correction). L3.0 est faite : résultats au §11.
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

## 11. Résultats de L3.0 (5 octobre 2026)

| Vérification | Résultat | Conséquence |
|---|---|---|
| **`pypdf` (F2)** | `pypdf` 6.19.0, pur Python (roue `py3-none-any`), ajouté seul aux dépendances verrouillées. | Pas de contrôle o2switch supplémentaire |
| Corpus de PDF porteurs d'identité | Le module Writer de LibreOffice est absent du conteneur : pas de PDF Word ou LibreOffice réels. Corpus : un PDF Chromium réel, et des variantes qui reproduisent ce que laissent ces logiciels. Variantes : `/Info` (auteur, titre, créateur), XMP `dc:creator`, mise à jour incrémentale, annotation de commentaire signée (`/T`), fichier joint, objets compressés, PDF chiffré, faux PDF. | À rejouer en L3.1 sur des PDF Word, LibreOffice et LaTeX réels (jeu de tests versionné) |
| Mise à jour incrémentale | `pdfinfo` affiche « Anonyme », mais l'ancien `/Info` (« Awa Zadi ») reste dans les octets du fichier. | Confirme qu'il faut **réécrire** le PDF, pas modifier `/Info` |
| Nettoyage prototype | Nouveau document construit **à partir des pages seules** :<br>• sans catalogue d'origine, donc sans XMP, fichiers joints, formulaires ni JavaScript ;<br>• sans `/Info` ;<br>• `/Metadata`, `/PieceInfo` et `/Thumb` retirés des pages ;<br>• annotations réduites aux liens, sans auteur ni date.<br>Vérifié par recherche dans les octets et par `pdfinfo` : aucune trace du nom, aucune métadonnée, texte intact (`pdftotext`). | Algorithme retenu pour L3.1 |
| Défaut trouvé | Une annotation copiée puis retirée restait écrite dans le fichier, comme objet orphelin. | Filtrer **avant** la copie, puis supprimer les objets orphelins (`compress_identical_objects(remove_unreferenced=True)`) ; test dédié en L3.1 |
| Refus | PDF chiffré refusé (`is_encrypted`) ; faux PDF refusé (`PdfReadError`). | Messages clairs côté auteur |
| Performance | 300 pages avec liens : 0,2 s ; liens conservés. | Traitement synchrone au dépôt (pas de tâche différée) |
| Limites connues | Le **texte** du document (nom dans le corps ou en en-tête de page) et les EXIF d'images JPEG incorporées ne sont pas traités. | Consigne affichée à l'auteur ; contrôle assisté du texte en P2 (étude M4) |
| **Stockage privé** | Décision de conception, sans vérification hors ligne possible : `GESTCONF_PRIVATE_FILES_DIR`, distinct des fichiers publics, hors racine web, à sauvegarder avec la base. | Ajouté à `.env.example` et à `deploy/README.md` en L3.1 |
| **Playwright en CI (F14)** | `@playwright/test` 1.63.0 (dans `web/`, lockfile produit avec npm 11 comme la CI). `web/e2e/playwright.config.ts` lance Django (SQLite dédiée, `migrate`, `createcachetable`) et le portail (`ng serve`, mandataire `/api`). Deux tests de fumée passent en local. Nouveau job CI « E2E (Playwright) ». | Le parcours auteur complet s'y ajoute en L3.6 |
| Défaut trouvé | Sans `createcachetable`, `/health` répond 503. | Commande ajoutée au démarrage E2E |

## 12. Bilan de L3.1 (5 octobre 2026)

**Livré (backend)** :

- **App `submissions`** :
  - `Submission`, `SubmissionAuthor`, `SubmissionFile` ;
  - `SubmissionRevision` et `StatusHistory`, en ajout seul, avec des méthodes nommées de
    rédaction pour l'anonymisation ;
  - `SubmissionExtension`, avec contrainte de motif non vide.
- **Énumération des statuts** : les 16 statuts de l'étude.
- **Réglages** :
  - `SubmissionType.file_policy` (`none`, `optional`, `required`) et `max_file_mb` (F1) ;
  - `Edition.submission_languages` (F11), audités.
- **Workflow** (`workflow.py`, règle n° 4) :
  - table des **19 transitions** de l'étude ;
  - les 4 transitions de L3 disponibles, les autres refusées (`invalid_transition`) jusqu'à
    leur lot.
- **`transition()`** :
  - verrou de ligne ; légalité ; édition archivée ;
  - acteur : soumissionnaire, ou système pour la clôture ;
  - gardes RG-01, RG-02 et motif de retrait ;
  - référence attribuée à la première soumission ;
  - `StatusHistory`, audit `submission.status_changed` ;
  - effets après validation (branchement des notifications en L3.2).
- **RG-01** (`missing_items`) :
  - champs et nombre de mots (apostrophes et traits d'union internes) ;
  - 1 à 6 mots-clés ; thématique et type actifs ; langue de l'édition ;
  - un correspondant ; soumissionnaire parmi les auteurs (F6) ;
  - fichier selon le type ; déclarations dans leur version courante (`declarations.py`,
    textes « v0 »).
- **RG-02** (`can_write`) : appel ouvert, ou dérogation en cours (non révoquée, non échue).
- **Compteur** `core.Counter` et `next_value`, sous verrou de ligne, dans la transaction
  appelante (F4).
- **RG-19** :
  - `code` et `double_blind` gelés dès la première soumission non brouillon (409
    `setting_frozen`) ;
  - un ADMIN de l'édition (ou l'opérateur) peut passer outre avec un motif, journalisé ;
  - `frozen_fields` exposé par l'API ; champ `reason` en écriture.
- **Données personnelles** :
  - traitement `submissions.submissions` dans le registre (export : ses soumissions et ses
    co-signatures) ;
  - registre des responsabilités (`register_duty_check`) : une soumission active dans une
    édition non archivée bloque l'anonymisation (F16) ;
  - anonymisation : brouillons supprimés ; ailleurs, lignes d'auteur anonymisées, nom et
    adresses retirés des clichés et des motifs.
- **Stockage privé** : `GESTCONF_PRIVATE_FILES_DIR` (défaut
  `<GESTCONF_FILES_DIR>/private`), documenté dans `.env.example` et `deploy/README.md`.
- **Intégrité** : fichier courant unique, fichier présent sur le disque, références sans trou.
- **Erreurs** : codes `submission_incomplete`, `call_closed`, `setting_frozen` (messages FR/EN
  dans `shared`) ; catalogue de traduction de l'API à jour ; schéma régénéré sur MariaDB.

**Défaut trouvé par le test de concurrence (MariaDB)** :

- *Symptôme* : quand le compteur n'existait pas encore, des `SELECT … FOR UPDATE` simultanés
  prenaient des verrous d'intervalle, et les insertions s'interbloquaient (erreur 1213).
- *Correction* :
  - le compteur est créé **avec l'édition** (récepteur, et migration pour les éditions
    existantes), hors contention ;
  - sa portée devient l'identifiant de l'édition (`submission:<id>`), puisque le code peut
    changer jusqu'à la première soumission ;
  - 8 soumissions simultanées : numéros 1 à 8 sans doublon, sur 3 passes consécutives.

**Écart signalé dans l'étude** : le statut `REVISION_REQUESTED` (tableau de M6) n'a aucune
transition dans le diagramme du §5.1. Il est déclaré, sans transition, et sera précisé en L4
avec les décisions. Le méta-test l'admet explicitement.

**Vérifications** :

- **Backend** : 1 372 tests sous SQLite, 1 379 sous MariaDB, dont 28 tests des soumissions :
  - table et méta-test « statut écrit par `workflow.py` seul », avec contre-épreuve du motif ;
  - RG-01, RG-02 et RG-19 ;
  - numérotation (séquence, pas de trou après refus, concurrence) ;
  - registre, export, anonymisation avec balayage, intégrité.
- **Contrôles** : `ruff` ; migrations ; schéma identique à la régénération ;
  `locale/check.sh` ; `pip-audit`.
- **Front** : tests, lint, format ; aucune erreur de type sur le client régénéré.

**Reporté** : l'écran « Confidentialité » de la gestion n'affiche pas encore le gel
(`frozen_fields`) ; le serveur le fait respecter. À faire en L3.4.

## 13. Bilan de L3.2 (5 octobre 2026)

**API de l'espace auteur** (`/v1/submissions…`, connecté, **ses** soumissions seulement,
404 sinon) :

- **Brouillon** :
  - `POST` avec le **code** de l'édition (l'édition publique n'expose toujours pas son
    identifiant : choix du lot L1 respecté) ;
  - profil complet exigé (409 `profile_incomplete`) ; appel ouvert exigé ;
  - le soumissionnaire devient premier auteur, correspondant et présentateur (F6) ;
  - rôle `AUTHOR` attribué au premier brouillon (D7).
- **Écriture** :
  - `PATCH` partiel (sauvegarde automatique) ; `If-Match` facultatif sur `revision`, 412
    `stale_revision` si la soumission a changé entre-temps ;
  - après la soumission, chaque écriture crée une **révision** avec son cliché (F3).
- **Auteurs** : `PUT …/authors`, liste complète ; adresses uniques ; rattachement au compte
  dont l'adresse vérifiée correspond (F5) ; journal sans adresse.
- **Fichier** :
  - `POST`/`DELETE …/file`, `GET …/file/content` (`attachment`, `nosniff`, `no-store`) ;
  - contrôles : type par le contenu, `.pdf`, taille du type, PDF chiffré, 500 pages au plus ;
  - en double aveugle, PDF stocké **nettoyé** (`pdf.py`, défauts de L3.0 corrigés, aucun
    dictionnaire `/Info`) ;
  - versions conservées ; orphelins purgés par `cleanup`.
- **Soumission et suivi** :
  - `GET …/check` (RG-01, sans écriture) ; `POST …/submit` ;
  - `POST …/withdraw` (motif obligatoire une fois soumise) ;
  - `GET …/timeline` (historique et révisions) ;
  - `DELETE` d'un brouillon seulement (409 `submission_locked` ensuite).
- **RG-02** :
  - écritures refusées après la clôture (409 `call_closed`), sauf dérogation en cours ;
  - services `grant_extension` (échéance saisie à l'heure de l'édition, D13) et
    `revoke_extension` (l'API de gestion vient en L3.4) ;
  - `can_edit`, `deadline` et `allowed_actions` exposés à l'auteur.
- **E-mails** (F13, mis en file **dans** la transaction de la transition) :
  - accusé de réception, information des co-auteurs, retrait, dérogation ;
  - objets sans variable (règle de L1 : l'objet survit à la purge des corps).
- **Réglages exposés** :
  - `file_policy` et `max_file_mb` dans les types de communication (gestion et public) ;
  - `submission_languages` dans l'édition (gestion) et dans l'édition publique ;
  - `double_blind` dans la vue auteur de sa soumission (et non dans l'édition publique).
- **Limites de débit** : `submission_write` (600/h, sauvegarde automatique comprise),
  `submission_upload` (30/h), `submission_submit` (20/h).
- **Codes d'erreur** : `stale_revision` (412), `submission_locked`, `profile_incomplete`.

**Défauts trouvés et corrigés pendant l'étape** :

- **Analyseurs multipart** : DRF les choisit avant de connaître l'action, d'où une classe de
  vue dédiée au fichier.
- **PDF chiffré** : le nombre de pages était lu avant le contrôle du chiffrement (message
  « illisible »).
- **Champ `Producer`** : pypdf l'ajoute par défaut ; il est retiré.
- **Identifiant de l'édition** : une substitution hors de la bonne classe l'avait retiré du
  sérialiseur de **gestion**. Le build l'a détecté et il est restauré.

**Vérifications** :

- **Backend** : 1 396 tests sous SQLite, 1 403 sous MariaDB, dont 50 pour les soumissions :
  - droits : 404 pour autrui, 401 anonyme ;
  - If-Match, révisions, auteurs ;
  - PDF : double aveugle, revue ouverte, 4 refus, politique et taille ;
  - corpus de nettoyage versionné (`test_pdf.py`) ;
  - e-mails, retrait, RG-02 et dérogation, suppression d'un brouillon, auteurs figés.
- **Contrôles** : `ruff` ; migrations ; schéma régénéré sur MariaDB et identique ;
  traductions à jour ; `pip-audit`.
- **Front** : 234 tests, lint, format, build (types vérifiés).

**Reporté en L3.4** (gestion) : écrans de saisie de `file_policy`, `max_file_mb`,
`submission_languages` et du gel RG-19 ; API de gestion des dérogations.

## 14. Bilan de L3.3 (5 octobre 2026)

**Espace auteur du portail** (`/compte/soumissions`, rendu navigateur, `authGuard`) :

- **« Mes soumissions »** :
  - liste : référence (ou « Brouillon »), titre, état traduit, échéance de modification ;
  - « Nouvelle soumission » si l'appel de l'édition courante est ouvert (dates clés
    publiques ; le serveur revérifie, RG-02) ;
  - profil incomplet : lien vers le profil et bouton désactivé (le serveur refuse aussi,
    409 `profile_incomplete`) ;
  - lien depuis l'accueil du compte et la navigation du compte.
- **Assistant en 5 étapes** (informations, auteurs, fichier, déclarations, récapitulatif) :
  - **sauvegarde automatique** des informations et des déclarations (anti-rebond de
    1,2 s, indicateur « Enregistré à… » à l'heure de l'édition) ; auteurs et fichier par
    une action explicite ;
  - compteur de mots du résumé, même règle que le serveur (apostrophes et traits d'union
    internes) ;
  - écritures **sérialisées** : chacune part avec la révision rendue par la précédente
    (`If-Match`) ; un 412 affiche « modifiée ailleurs » et propose de recharger ;
  - fichier : politique du type, avertissement en double aveugle, lien vers l'endpoint
    authentifié, versions, « métadonnées supprimées » ;
  - récapitulatif : manques lus sur `check` (RG-01) ; « Soumettre » désactivé tant que la
    soumission est incomplète ; suppression d'un brouillon ;
  - après la soumission : référence annoncée, lecture seule si l'appel est clos, retrait
    motivé, historique des états et nombre de révisions.
- **Choix de l'API** (ajustés à l'étape) :
  - thématique et type de communication échangés par leur **code** (l'édition publique
    n'expose pas d'identifiants) ;
  - mots-clés typés en liste ;
  - liste des soumissions non paginée : quelques soumissions par auteur.
- **Traductions** : clés `portail.submissions.*` (FR et EN), 16 états de l'étude (M6) et
  textes provisoires des 4 déclarations (Q14).

**Bundle initial du portail : 367,7 kB** (371,4 kB à la fin de L2 ; avertissement à
365 kB, erreur à 380 kB) :

- **Cause** : l'index du client généré utilise des réexportations nommées. Avec elles,
  esbuild range dans le bundle initial **toute fonction d'API utilisée**, même par une seule
  page chargée à la demande. L'étape l'aurait porté à 375,3 kB.
- **Vérification** : sans l'index, la fonction suit sa page. Avec des réexportations
  « étoile », chaque fonction suit les pages qui l'utilisent.
- **Correction** : `scripts/api-barrel.mjs` réécrit l'index en `export * from …` à chaque
  `npm run api:generate`. Le script a 3 tests. Le client n'est pas édité à la main et le
  contrôle « client obsolète » de la CI reste valable.
- **Effet** : le portail gagne aussi les fonctions déjà utilisées par les pages du compte
  (L1, L2). La gestion est à 359,9 kB.
- **Pages groupées** : les deux pages auteur forment un seul morceau chargé à la demande.

**Défauts trouvés dans le navigateur et corrigés** :

- **Bouton « Enregistrer les auteurs » sans effet** : le formulaire n'avait pas de
  `[formGroup]`, donc `ngSubmit` n'était jamais émis. Les tests unitaires appelaient la
  méthode directement ; un test clique désormais sur le bouton.
- **« Vous pouvez la soumettre »** restait affiché après la soumission.
- **Liste à 375 px** : débordement horizontal de 76 px. Le tableau défile maintenant dans
  son cadre (région focalisable).
- **Formulaire de retrait** mal aligné.

**Vérifications** :

- **Front** : portail 104 tests (20 nouveaux : service, liste, assistant), gestion 74,
  shared 76, scripts 11 ; lint, format, build.
- **Backend** : 1 396 tests sous SQLite, 1 403 sous MariaDB ; `ruff` ; schéma régénéré sur
  MariaDB et identique.
- **Parcours complet dans Chromium**, base locale avec un appel ouvert :
  - brouillon, sauvegarde automatique, compteur de mots ;
  - auteur prérempli, co-auteur ajouté ;
  - faux PDF refusé, vrai PDF déposé puis téléchargé (`attachment`), métadonnées
    supprimées ;
  - manques RG-01 affichés, puis déclarations enregistrées automatiquement ;
  - **conflit entre deux onglets** (412) puis rechargement ;
  - soumission (référence GC27-0001), liste, retrait motivé, historique, lecture seule ;
  - 375 px sans débordement à chaque étape ; aucune erreur dans la console.
