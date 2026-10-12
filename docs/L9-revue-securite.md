# Revue de sécurité — GEST-CONF (lot L9, S7)

Revue interne avant l'ouverture (étude §9.3, §12 ; plan L9, S7), sur le code du dépôt au
12 octobre 2026 (branche `claude/happy-mayer-nj3g47`, après L9.4). Référentiels : **OWASP Top 10
(2021)** et une sélection de contrôles de l'**ASVS 4.0 niveau 2**. Chaque constat est **corrigé**
dans le lot ou **accepté par écrit** ; ce qui ne se vérifie que sur l'hébergement est renvoyé au
runbook (`docs/L9-runbook-o2switch.md`, L9.8).

Un test d'intrusion par un prestataire reste une décision du commanditaire (question 6 du plan) ;
cette revue ne le remplace pas.

## 1. Méthode

- **Lecture du code et des tests** : pour chaque contrôle, la preuve (fichier, test, commande)
  est citée ; un contrôle sans preuve est un constat.
- **Outils automatiques**, déjà en CI : `ruff` avec les règles `S` (flake8-bandit),
  `pip-audit` (dépendances de production), `npm audit --omit=dev --audit-level=high`,
  `manage.py check --deploy --fail-level WARNING` en réglages de production, matrice des droits
  (`backend/tests/test_matrix.py`) et méta-tests de plateforme (`backend/tests/test_platform_rules.py`).
- **ZAP 2.16.1** (paquet multiplateforme, Java 21), en local : import du schéma OpenAPI (359
  adresses), exploration et **analyse passive** de l'API servie en réglages de production
  (§5). Sur l'hébergement, l'opérateur lance `deploy/zap/baseline.yaml` (passif seulement).
- **Test de charge** (L9.4) : il a révélé un défaut de disponibilité (constat R7).

## 2. Synthèse des constats

| # | Constat | Réf. | Gravité | Statut |
|---|---|---|---|---|
| R1 | Taille des requêtes non bornée : un envoi de plusieurs gigaoctets remplissait le disque temporaire avant le contrôle de taille de la vue | A04, V12.1 | Moyenne | **Corrigé** : `RequestSizeLimitMiddleware`, 413 avant lecture au-delà de `GESTCONF_MAX_REQUEST_MB` (55 Mio) ; résiduel R1b |
| R1b | Passenger met l'envoi en mémoire tampon avant Django (`PassengerBufferUpload`) : la borne de Django ne protège pas cette étape | A04 | Faible | **À vérifier** sur l'hébergement (runbook : envoi de 100 Mio → 413, espace disque inchangé) ; `LimitRequestBody` non posé dans le `.htaccess` faute de savoir si o2switch l'autorise (une directive refusée rendrait tout le portail en erreur 500) |
| R2 | Réponses JSON authentifiées sans `Cache-Control` : données personnelles cachables par le navigateur ou un intermédiaire | V8.2.1 | Moyenne | **Corrigé** : `DefaultNoStoreMiddleware` (`no-store` sauf en-tête fixé par la vue) |
| R3 | PDF d'attestations et de lettres servis sans contrôle d'empreinte (les factures l'avaient déjà) | A08 | Moyenne | **Corrigé** : `PrivateStore.read_verified`, 404 si le fichier est absent ou modifié |
| R4 | Le PDF émis d'une lettre d'invitation porte le numéro de passeport et restait sur le disque après l'effacement de K14 et après l'anonymisation | V8.3, RGPD | Moyenne | **Corrigé** : `erase_passport_data` efface le numéro **et** le PDF (la lettre reste vérifiable par son code) |
| R5 | Aucune commande de rotation de `GESTCONF_SIGNING_ENCRYPTION_KEYS` | A02 | Faible | **Corrigé** : `rotate_signing_keys` (testée) ; procédure dans `deploy/README.md` |
| R6 | Pas de `SECRET_KEY_FALLBACKS` : changer la clé déconnecte tout le monde et casse les liens envoyés | A02 | Faible | **Corrigé** : `DJANGO_SECRET_KEY_FALLBACKS` en production ; procédure documentée |
| R7 | Bandeau public limité à 60 requêtes/min **par adresse IP** : derrière le Wi-Fi du lieu (une adresse pour des centaines de participants), il disparaissait au moment où il sert le plus | A04 (disponibilité) | Moyenne | **Corrigé** : 600/min (le navigateur le garde 60 s) |
| R8 | Aucun test ne vérifiait la longueur minimale du mot de passe (12) | V2.1.1 | Faible | **Corrigé** : `test_password_must_have_at_least_12_characters` |
| R9 | Aucun test d'injection d'en-tête par l'objet d'un e-mail | A03 | Faible | **Corrigé** : `test_subject_never_carries_a_line_break` |
| R10 | Actions de la CI épinglées par version majeure (`@v7`), pas par empreinte | A08 | Faible | **Accepté** : actions officielles `actions/*` seulement, `permissions: contents: read`, aucun secret dans la CI ; à revoir si une action tierce est ajoutée |
| R11 | Pas de Dependabot ni de Renovate | A06 | Faible | **Accepté provisoirement** : `pip-audit` et `npm audit` à chaque CI ; leur activation ouvrirait des PR automatiques sur le dépôt : proposition au commanditaire |
| R12 | Jeton du QR du badge stocké en clair | A02 | Faible | **Accepté par conception** (K2, K3) : le serveur régénère le badge à la demande ; jeton révocable (badge perdu), servi à son seul titulaire ; la liste hors ligne n'en contient que l'empreinte |
| R13 | Numéro de passeport en clair en base | A02 | Faible | **Accepté** : masqué au participant, lu par `letters.manage` seul, jamais au journal, effacé 30 jours après l'édition et à l'anonymisation (R4) |
| R14 | HSTS sans `includeSubDomains` ni `preload` | V9.1 | Info | **Accepté** : sous-domaines du compte non vérifiés (fiche o2switch) |
| R15 | CSP : `style-src 'unsafe-inline'` | A05 | Info | **Accepté** : styles des composants Angular ; `script-src` à empreintes (`inject-csp.mjs`), aucun gestionnaire en ligne |
| R16 | En-tête `Server` avec version (vu par ZAP sur le serveur de développement) | A05 | Info | **À vérifier** sur l'hébergement (ZAP de l'opérateur) ; hors de portée du `.htaccess` |
| R17 | Pas d'antivirus des PDF déposés | V12.4 | Faible | **Question 9 du plan** (hypothèse : accepté) : type vérifié par le contenu, PDF chiffré refusé, réécrit en double aveugle, téléchargement authentifié |

Aucun constat critique ou élevé.

## 3. OWASP Top 10 (2021)

### A01 — Contrôle d'accès défaillant : **conforme**

- Capacités par rôle et par édition (`apps/accounts/roles.py`), vérifiées par le serveur :
  `HasCapability` refuse toute action non déclarée ; `EditionScopedViewMixin` lit l'édition dans
  l'URL, renvoie 404 aux non-membres et filtre les querysets par édition ;
  `ManageViewSet` = authentification + capacité + 2FA.
- **Matrice des droits** : 281 couples route × méthode × 19 profils
  (`tests/test_matrix.py::test_matrix`, `::test_matrix_stale_reauthentication`,
  `::test_matrix_archived_edition_is_read_only`, `::test_every_manage_route_is_in_matrix`,
  `::test_object_of_another_edition_is_404`).
- Règles de plateforme : authentification par défaut, vues anonymes en liste blanche, aucun rôle
  global, aucune permission de modèle Django (`tests/test_platform_rules.py`).
- **Double aveugle (RG-04)** : sérialiseurs relecteurs en liste blanche contrôlée par méta-test
  (`apps/reviews/anonymity.py`, `test_anonymity.py`), un test de fuite par route relecteur
  (`test_leaks.py`, 9 tests), PDF réécrit sans métadonnées (`test_f2_identity_is_removed_from_every_byte`).
- Objets d'autrui : querysets filtrés par propriétaire (`test_author_sees_only_own_submissions`,
  `test_someone_else_registration_is_404`).

### A02 — Défaillances cryptographiques : **conforme après R5 et R6**

- Secrets TOTP chiffrés (`MultiFernet`, `GESTCONF_MFA_ENCRYPTION_KEYS`, obligatoire en
  production), rotation `rotate_mfa_keys` testée ; certificat PAdES réexporté sans mot de passe
  et chiffré (`GESTCONF_SIGNING_ENCRYPTION_KEYS`), rotation `rotate_signing_keys` (R5).
- Mots de passe : PBKDF2-SHA256 par défaut de Django 5.2.
- Jetons d'invitation stockés en SHA-256 (`test_invitation_token_never_stored_in_clear`) ;
  jeton de notification de paiement en empreinte, comparé à temps constant.
- Transport : cookies `Secure`, HSTS d'un an ; redirection HTTPS par cPanel, vérifiée par les
  tests de fumée (L9.2).

### A03 — Injection : **conforme**

- SQL : ORM ; requêtes brutes paramétrées ou sur un nom cité par `quote_name` (`core/locking.py`,
  `core/integrity.py`, `core/cache_maintenance.py`, `core/backups.py`) ; ni `.raw`, ni `.extra`.
- HTML : assainisseur en liste blanche au serveur (`apps/portal/sanitizer.py`,
  `test_xss_payloads_leave_no_active_content`) et au rendu (`sanitize.ts`) ; aucun
  `bypassSecurityTrust` dans le front.
- Tableurs : cellules neutralisées (`csv_cell`, `spreadsheet.cell`), chaînes XLSX typées texte
  (`test_n13_xlsx_strings_never_become_formulas`).
- En-têtes d'e-mail : objet réduit à une ligne (R9).

### A04 — Conception non sécurisée : **conforme après R1, R7**

- Limites de débit par portée (19 portées, `test_throttle_settings_are_scoped_only`), connexions
  échouées limitées (`test_too_many_failed_logins_are_throttled`).
- Statuts écrits par un service unique (méta-tests des workflows des soumissions et des
  inscriptions) ; réauthentification récente (5 min) pour les opérations sensibles (rôles,
  exports, paiements, publication, signature).
- Paiement : la notification n'est qu'un signal, seul l'appel au prestataire confirme (RG-15).

### A05 — Mauvaise configuration : **conforme après R2**

- Production : `DEBUG=False`, hôtes et origines CSRF par variables, `check --deploy` en CI ;
  `nosniff`, `Referrer-Policy`, COOP, `X-Frame-Options: DENY`.
- Portail et gestion : CSP (en-tête + `<meta>` à empreintes), `Permissions-Policy`, HSTS
  (`deploy/apache/*.htaccess`), vérifiés par les tests de fumée (L9.2).
- Pas d'admin Django (trois tests), pas de CORS (même origine), erreurs JSON normalisées sans
  trace (`apps/core/exceptions.py`).

### A06 — Composants vulnérables : **conforme (R11 accepté)**

- Dépendances verrouillées à empreintes, installées avec `--require-hashes` (CI et
  `deploy.sh`) ; `pip-audit` et `npm audit` en CI.

### A07 — Identification et authentification : **conforme après R8**

- allauth headless : connexion par e-mail, vérification obligatoire, prévention de
  l'énumération (`test_no_timing_oracle_on_signup`, `…_on_password_request`).
- Mots de passe de 12 caractères au moins, communs et numériques refusés (R8).
- 2FA imposée aux rôles de gestion (`MFA_REQUIRED_ROLES`), code non rejouable ; session de 12 h
  absolues ; clé de session renouvelée à la connexion ; autres sessions fermées au changement de
  mot de passe.

### A08 — Intégrité des logiciels et des données : **conforme après R3 (R10 accepté)**

- Pièces comptables, attestations et lettres : PDF figés, empreinte contrôlée à chaque lecture
  (R3) et par `check_integrity` ; déploiement par `git archive` du commit, sans `curl | bash`.

### A09 — Journalisation et supervision : **conforme**

- Journal d'audit en ajout seul, sans secret ni adresse en clair (`test_rg17_*`) ; connexions,
  échecs, 2FA, exports, commandes d'exploitation journalisés.
- Alertes aux opérateurs (erreurs, cron en échec, intégrité, sauvegarde en retard, disque) ;
  surveillance externe de disponibilité à configurer (runbook).

### A10 — SSRF : **conforme**

- Seuls appels sortants : prestataire de paiement (hôtes fixes, délai de 8 s) et fournisseur
  d'e-mails (délais d'anymail) ; aucune adresse fournie par un utilisateur n'est appelée.

## 4. ASVS 4.0, niveau 2 (sélection)

| Chapitre | Contrôle | Preuve | Statut |
|---|---|---|---|
| V2 Authentification | 2.1.1 longueur ≥ 12 ; 2.2.1 anti-automatisation ; 2.8 TOTP | R8 ; `test_too_many_failed_logins_are_throttled` ; `test_same_code_cannot_be_replayed` | Conforme |
| V3 Sessions | 3.2.1 nouvelle clé à la connexion ; 3.3.1 déconnexion ; 3.3.2 durée absolue ; 3.4 cookies | `test_session_key_is_renewed_at_login` ; `test_absolute_session_timeout` ; `HttpOnly`, `Secure`, `SameSite=Lax` | Conforme |
| V4 Contrôle d'accès | 4.1.1 côté serveur ; 4.2.1 objets d'autrui ; 4.3.1 2FA d'administration | matrice des droits ; tests 404 ; `MfaVerified` | Conforme |
| V5 Validation | 5.1 entrées ; 5.2.1 HTML assaini ; 5.3.3 encodage de sortie | sérialiseurs DRF ; assainisseur ; Angular | Conforme |
| V7 Erreurs et journaux | 7.1 pas de secret au journal ; 7.4 erreurs génériques | `test_rg17_forbidden_keys_refused_at_any_depth` ; gestionnaire d'exceptions | Conforme |
| V8 Données | 8.2.1 pas de cache ; 8.3.4 effacement | R2 ; R4, `cleanup`, anonymisation (RG-18) | Conforme après correctifs |
| V9 Communications | 9.1.1 TLS partout | HSTS, cookies `Secure`, redirection vérifiée | Conforme (R14 accepté) |
| V10 Code malveillant | 10.3.2 intégrité des dépendances | empreintes, `--require-hashes` | Conforme |
| V12 Fichiers | 12.1.1 taille ; 12.2.1 type par le contenu ; 12.4.1 hors racine web ; 12.5.2 servis en pièce jointe | R1 ; `pdf.py`, `public_files.py` ; `PrivateStore` ; `attachment`, `nosniff` | Conforme après R1 (R1b, R17 ouverts) |
| V13 API | 13.1.3 pas de secret dans l'URL ; 13.2.1 méthodes ; 13.2.3 CSRF | schéma OpenAPI ; `HasCapability` par méthode ; CSRF de session | Conforme |
| V14 Configuration | 14.2.1 composants à jour ; 14.4 en-têtes | `pip-audit`, `npm audit` ; tests de fumée | Conforme |

## 5. Outils automatiques : résultats

- **`ruff`, règles `S`** : aucun constat ouvert. Exceptions hors tests, chacune justifiée sur sa
  ligne : `config/settings/test.py` (S105, clé de test), `payments/providers/cinetpay.py` et
  `accounts/services/mfa.py` (S105, noms de clé pris pour des mots de passe),
  `core/integrity.py` et `core/cache_maintenance.py` (S608, nom de table cité par
  `quote_name`), `core/backups.py` (S603, appels de `mariadb-dump` et `mariadb` sans shell,
  arguments en liste) ; `loadtest/locustfile.py` (S311, tirages non cryptographiques).
- **`pip-audit`, `npm audit`, `check --deploy`** : verts en CI (PR #13, `87cf3a7`) ; relancés à
  chaque CI.
- **ZAP** (local, API en réglages de production, base fictive) : une seule alerte, **faible** :
  en-tête `Server: WSGIServer/0.2 CPython/3.12.3`, propre au serveur de développement (R16).
  Aucune alerte sur les en-têtes de sécurité, le cache (après R2) ni la divulgation
  d'informations. Limites : les points d'authentification d'allauth (hors du schéma) et leurs
  cookies ne sont pas couverts par cet essai, ni les en-têtes posés par Apache : l'analyse de
  l'opérateur et les tests de fumée les couvrent. L'import OpenAPI envoie aussi des écritures :
  il n'est **jamais** lancé contre l'hébergement, dont l'analyse reste passive
  (`deploy/zap/baseline.yaml`).

## 6. Secrets et rotation

| Secret | Usage | Rotation |
|---|---|---|
| `DJANGO_SECRET_KEY` | sessions, CSRF, liens signés | nouvelle clé + `DJANGO_SECRET_KEY_FALLBACKS` (R6) |
| `GESTCONF_MFA_ENCRYPTION_KEYS` | secrets TOTP | `rotate_mfa_keys` |
| `GESTCONF_SIGNING_ENCRYPTION_KEYS` | certificat PAdES | `rotate_signing_keys` (R5) |
| `DATABASE_URL` | MariaDB | cPanel puis `.env` |
| `CINETPAY_API_KEY`, `CINETPAY_API_PASSWORD` | paiement | console du prestataire puis `.env` |
| `BREVO_API_KEY` ou `MAILJET_*` | e-mails | console du fournisseur puis `.env` |

Procédures : `deploy/README.md` (« Clés de la 2FA », « Clé du certificat de signature », « Clé
secrète de Django », « Autres secrets »). Aucun secret dans le dépôt ni dans la CI (règle n° 11) ;
les sels des liens de désabonnement et d'invitation sont des constantes, pas des secrets.

## 7. À vérifier sur l'hébergement (runbook, L9.8)

1. ZAP passif (`deploy/zap/baseline.yaml`) : traiter chaque alerte ; en-tête `Server` (R16).
2. Envoi de 100 Mio sur une route de dépôt : 413, espace disque inchangé (R1b).
3. Tests de fumée : en-têtes de sécurité, HSTS, redirection HTTPS (L9.2).
4. Droits du fichier `.env` (0600) et des dossiers privés et de sauvegarde (0700).
5. Absence de `phpinfo`, d'index de dossier et de fichiers de développement sous `public_html`.
