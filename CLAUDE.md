# CLAUDE.md — GEST-CONF

Plateforme de gestion de conférences scientifiques : portail public, espace de gestion (comités, administration), espaces auteurs / évaluateurs / intervenants / participants.

**Source de vérité fonctionnelle et technique : `Etude_fonctionnelle_et_technique_GEST-CONF.md`** (à la racine). Avant d'implémenter un module, relire la section correspondante (modules §4, workflows §5, règles de gestion RG-xx §6, modèle de données §8, API et sécurité §9). Si le code et l'étude divergent, le signaler et proposer une mise à jour de l'étude plutôt que de dériver silencieusement.

## Stack (imposée)

| Couche | Choix |
|---|---|
| Backend | Python 3.12/3.13, Django (LTS), Django REST Framework, **sans `django.contrib.admin`** |
| Frontend | Angular (version stable courante), composants autonomes, signaux — workspace avec 2 applications (`portail`, `gestion`) + bibliothèque `shared` |
| Base de données | MariaDB, InnoDB, `utf8mb4` |
| Hébergement | o2switch mutualisé, **un seul domaine** : `/` portail, `/gestion/` back-office, `/api/` Django via Passenger |
| Auth | `django-allauth` en mode *headless* (client `browser` seul) + sessions + CSRF (pas de JWT dans le navigateur), 2FA TOTP par `allauth.mfa` (décision D2 ; `django-otp` abandonné, faute d'intégration headless) imposée côté serveur aux rôles de gestion, ORCID (P2) |
| API | REST `/api/v1/`, OpenAPI via `drf-spectacular`, client TypeScript généré pour Angular. Authentification : endpoints allauth tels quels sous `/api/_allauth/browser/v1/`, consommés par une façade TypeScript écrite à la main et couverte par des tests de contrat (décision D4) |

## Règles non négociables

1. **Pas d'admin Django.** Ne jamais ajouter `django.contrib.admin` ni `admin.py`. Les opérations passent par l'espace de gestion Angular ou des commandes `manage.py`.
2. **Les droits se vérifient côté serveur**, jamais seulement dans Angular. Les guards Angular sont de l'ergonomie, pas de la sécurité.
3. **Double aveugle (RG-04)** : aucun endpoint destiné à un relecteur ne renvoie nom, e-mail, affiliation ou métadonnées de fichier d'un auteur. Utiliser des sérialiseurs distincts par rôle et filtrer les querysets par rôle. Toute modification touchant à cela exige un test dédié.
4. **Transitions de statut via un service unique** (`transition(submission, to_state, actor)`) : vérifie la légalité, les droits, écrit `status_history`, déclenche notifications. Aucune vue ne modifie `status` directement.
5. **Rôles rattachés à une édition** (`UserRole(user, edition, role)`) ; jamais de rôle global implicite.
6. **Grille d'évaluation** : somme des poids = 100 (RG-05) ; une grille déjà utilisée est verrouillée (on duplique en nouvelle version). Le score pondéré est recalculé côté serveur.
7. **Aucune donnée de carte bancaire** sur le serveur ; un paiement n'est valide que sur webhook vérifié (RG-15).
8. **Fichiers déposés hors racine web**, nom aléatoire, type vérifié par contenu, servis par un endpoint authentifié.
9. **Pas de Celery/Redis/WebSocket** (hébergement mutualisé) : tâches asynchrones = table `job` + commande `manage.py run_jobs` lancée par cron. Les commandes cron doivent être idempotentes et verrouillées.
10. **Pas de bibliothèque à dépendances système lourdes** (ex. WeasyPrint) sans confirmation de disponibilité sur o2switch : privilégier ReportLab/fpdf2, `pypdf`/`pikepdf`, `segno`.
11. **Ne jamais committer de secrets** (`.env`, clés agrégateur, `SECRET_KEY`). Configuration par variables d'environnement.

## Structure du dépôt

```text
GEST-CONF/
├── CLAUDE.md, README.md
├── Etude_fonctionnelle_et_technique_GEST-CONF.md / .html   # étude (Markdown et HTML tenus à jour ensemble)
├── docs/                    # plans de lot (Lx-…-plan.md) et bilans (Lx-….md), fiche o2switch
├── deploy/                  # deploy.sh, smoke-test.sh, cron.sh, check-o2switch.sh, README.md
├── backend/                 # Django
│   ├── config/settings/ (base, dev, prod, test) ; urls.py (API uniquement) ; mount.py ; passenger_wsgi.py
│   ├── apps/ core, accounts, conferences, portal, communications, submissions, reviews,
│   │         program, registrations, payments, events (à venir, lot par lot :
│   │         sponsors, logistics, reports)
│   ├── tests/               # tests transverses : matrice des droits, schéma, règles de plateforme
│   ├── locale/              # traductions du backend (FR/EN)
│   ├── schema.yml           # schéma OpenAPI versionné
│   └── requirements/ (base, prod, dev : fichiers .in compilés en .txt à empreintes)
└── web/                     # Angular
    ├── projects/ portail, gestion, shared (client d'API généré, auth, ui-kit, i18n)
    ├── e2e/                 # Playwright : playwright.config.ts, seed.py, django.ts, totp.ts, tests/
    └── scripts/             # api-barrel, check-prerender, inject-csp (et leurs tests)
```

Les comités n'ont pas d'application propre : rôles par édition dans `accounts`, pages publiques dans `portal` (L2).

Chaque app Django : `models.py`, `services.py` (logique métier ; paquet `services/` quand il grossit, comme `accounts`, `reviews` et `program`), `serializers.py` (par rôle si champs sensibles), `permissions.py`, `views.py`, `urls.py`, `tests/`. **La logique métier va dans les services**, pas dans les vues ni les modèles.

## Conventions de code

- **Langue** : identifiants (code, tables, champs, endpoints) en **anglais** ; commentaires, documentation et messages de commit en **français** ; textes d'interface via i18n (FR/EN, clés de traduction, aucune chaîne en dur).
- **Python** : `ruff` (lint + format), typage des signatures publiques des services, `Decimal` pour tout montant et tout score, dates stockées en UTC ; affichage converti dans le fuseau de l'édition côté interface, mais **saisie** des échéances en heure locale de l'édition, convertie côté serveur (décision D13).
- **Django** : requêtes optimisées (`select_related` / `prefetch_related`, pas de N+1), migrations rétro-compatibles (ajout puis suppression en deux temps), FK `ON DELETE RESTRICT` par défaut, suppression logique ou anonymisation pour les données personnelles. Numérotation (références, factures) via compteur verrouillé en transaction.
- **DRF** : erreurs normalisées `{code, message, fields}`, pagination/filtre/tri uniformes (`django-filter`), throttling sur auth, inscription, contact, vérification d'attestation.
- **Angular** : composants autonomes, lazy loading par route, formulaires réactifs typés, état local en signaux, client API **généré** (ne pas l'éditer à la main), accessibilité WCAG 2.1 AA.
- **Portail** : pré-rendu statique (SSG), pas de SSR ; budget de bundle surveillé.

## Commandes

```bash
# Backend (Python 3.12/3.13)
cd backend && python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements/dev.txt
python manage.py migrate && python manage.py runserver   # http://localhost:8000/api/v1/health
pytest                      # SQLite par défaut ; DATABASE_URL=mysql://... pour MariaDB (fait foi en CI)
ruff check . ../deploy ../web/e2e && ruff format --check . ../deploy ../web/e2e
DATABASE_URL=mysql://... python manage.py spectacular --file schema.yml --validate   # schéma OpenAPI (versionné), généré sur MariaDB comme en CI (bornes des entiers)

# Frontend (Node >= 22.22.3 ou >= 24.15, exigence d'Angular 22)
cd web && npm ci
npm run start:portail       # :4200 ; npm run start:gestion -> :4201/gestion/ (proxy /api -> :8000)
npm test && npm run lint && npm run format:check
npm run build               # portail pré-rendu + gestion + CSP à empreintes
npm run api:generate        # régénérer le client TypeScript après chaque évolution du schéma
GESTCONF_E2E_PYTHON=../backend/.venv/bin/python npm run e2e   # Playwright lance Django, le portail et la gestion (ports 8000, 4200, 4201 libres) ; GESTCONF_E2E_CHROMIUM=<chemin> pour un Chromium déjà installé

# Déploiement : deploy/deploy.sh puis deploy/smoke-test.sh (voir deploy/README.md)
# Cron (deploy/cron.sh) : run_jobs (toutes les 5 min), close_call, remind_drafts, remind_reviewers, remind_presentations, expire_registrations et sync_payments (horaires), cleanup et check_integrity (quotidiennes)
```

Les URL Django sont déclarées **sans** le préfixe `/api` (`v1/...`) : `config/mount.py` gère le montage.

## Tests (exigés)

- `pytest-django` : unitaires (score pondéré, transitions, détection de conflits de planning, numérotation), API (droits par rôle, **double aveugle**, filtres), intégration (webhook de paiement simulé, e-mails, PDF, cron).
- Un test par case sensible de la matrice des droits (étude §3.3).
- E2E Playwright : parcours auteur → évaluation → décision → inscription → check-in.
- Couverture visée ≥ 80 % sur la logique critique (évaluation, décisions, planning, paiements).
- Ne pas marquer une tâche terminée si les tests échouent.

## Déploiement o2switch (points d'attention)

- Python via cPanel « Setup Python App » (Passenger/WSGI) ; application **hors racine du domaine** ; URL de l'app = `/api`. Les règles de repli SPA du `.htaccess` ne doivent ni écraser le bloc Passenger ni intercepter `/api/`.
- Déploiement : build Angular en CI → rsync/SSH vers `public_html/` et `public_html/gestion/` → `pip install` → `migrate` → redémarrage Passenger (`tmp/restart.txt`) → tests de fumée.
- **Non vérifié, à confirmer avant de s'appuyer dessus** : version de MariaDB, fréquence minimale du cron, limites de ressources, sous-domaines autorisés, antivirus, compilation de `mysqlclient` (`PyMySQL` est le pilote retenu). Ne pas affirmer ces points sans vérification. Aucune ligne de la fiche [`docs/L1-verifications-o2switch.md`](docs/L1-verifications-o2switch.md) n'est encore remplie : elle se remplit avec `deploy/check-o2switch.sh` (lecture seule, en SSH) et les contrôles manuels qu'elle décrit.
- Sauvegarde quotidienne base + fichiers, copie hors hébergement, restauration testée.

## Méthode de travail attendue

- Avancer **par lots** (étude §14) : socle → portail → soumission → évaluation/décision (MVP) → programme → inscriptions → jour J → logistique/reporting → recette. Ne pas anticiper un lot ultérieur sans accord.
- Priorités : P1 (MVP) > P2 (V1) > P3 (V2). Ne pas implémenter du P3 tant que le P1 n'est pas livré.
- Avant toute modification large (modèle de données, permissions, workflow de statuts), proposer le plan et attendre validation.
- Une règle de gestion (RG-xx) implémentée = un test qui la référence dans son nom ou sa docstring.
- Être rigoureux et critique : signaler les incohérences de l'étude, les risques de sécurité et les hypothèses non vérifiées plutôt que de les contourner. Ne pas inventer d'API de bibliothèque : vérifier dans la documentation ou le code installé.
- Chaque lot : plan `docs/Lx-…-plan.md` (décisions numérotées) soumis à validation, étapes `Lx.0`…`Lx.n` committées et poussées une à une avec leur bilan dans le plan, puis bilan du lot `docs/Lx-….md`, section « Mises à jour issues du lot » de l'étude (Markdown **et** HTML) et section « Décisions du lot » ci-dessous.

## État d'avancement

| Lot | État |
|---|---|
| L0 à L4 (MVP : squelette, socle, portail, soumission, évaluation et décision) | Livrés en code, testés en local et en CI ; bilans dans `docs/`. **Aucune démo sur o2switch** encore faite |
| L5 — Programme | **Livré en code, testé en local et en CI** (L5.0 à L5.7, E2E compris ; PR #8 et #9, fusionnées) ; bilan [`docs/L5-programme.md`](docs/L5-programme.md). Ouverts : Q14, `ACCEPTED_MINOR → WITHDRAWN`, seuil d'avertissement du bundle du portail |
| L6 — Inscriptions et paiements | **Livré en code et testé en local** (L6.0 à L6.7, E2E compris) ; bilan [`docs/L6-inscriptions.md`](docs/L6-inscriptions.md). Passage en CI : nouvelle PR, sur demande. Ouverts : Q7 (tarifs ; carte bancaire absente de l'API v1 de CinetPay), Q8 (entité de facturation, conservation, format du numéro), J15 reportée |
| L7 — Jour J et attestations | **Livré en code et testé en local** (L7.0 à L7.8, E2E compris) ; bilan [`docs/L7-jour-j.md`](docs/L7-jour-j.md). Passage en CI : nouvelle PR, sur demande. Ouverts : Q17 (prestataire de signature qualifiée), nom complet du pays sur les badges, démo H sur téléphones réels |
| L8 et suivants | Non commencés |

## Décisions du lot L1

Les décisions D1 à D18 du plan [`docs/L1-socle-plan.md`](docs/L1-socle-plan.md) ont été validées le 5 octobre 2026 : elles s'appliquent (notamment D1 : aucun rôle global, autorité de plateforme exercée par des commandes `manage.py` auditées). Elles sont reportées dans l'étude, **§17 « Mises à jour issues du lot L1 »**, qui prévaut sur les sections antérieures en cas de divergence. Bilan du lot et exploitation : [`docs/L1-socle.md`](docs/L1-socle.md).

## Décisions du lot L2

Les décisions E1 à E14 du plan [`docs/L2-portail-plan.md`](docs/L2-portail-plan.md) et les adaptations de son §2.4 ont été validées le 5 octobre 2026. Elles sont reportées dans l'étude, **§18 « Mises à jour issues du lot L2 »**, qui prévaut sur les sections antérieures (§17 compris). Points à retenir :

- portail **pré-rendu au build seul**, `/fr/…` et `/en/…` ; une modification n'est visible qu'à la publication (`deploy/deploy.sh --portal-only`), la gestion compte les modifications non publiées ;
- contenus du portail par le CMS-lite (`apps/portal`) : sections typées à catalogue fermé, HTML en liste blanche assaini au serveur **et** au rendu ; capacité `portal.write` ;
- fichiers publics (`core.PublicFile`) : adaptation de la règle n° 8 limitée aux fichiers publics par nature ; les fichiers des auteurs restent soumis à la règle sans adaptation ;
- comités publics : consentement `directory_listing` (et `photo_publication` pour la photo), jamais d'adresse ;
- gestion : chaque nouvel écran s'inscrit dans `core/navigation.ts` (rail et recherche) et reçoit sa fiche d'aide (`help/help-sheets.ts`), sous peine d'échec des tests de cohérence.

Bilan du lot : [`docs/L2-portail.md`](docs/L2-portail.md).

## Décisions du lot L3

Les décisions F1 à F17 du plan [`docs/L3-soumission-plan.md`](docs/L3-soumission-plan.md) ont été validées le 5 octobre 2026. Elles sont reportées dans l'étude, **§19 « Mises à jour issues du lot L3 »**, qui prévaut sur les sections antérieures (§17 et §18 compris). Points à retenir :

- statut des soumissions écrit par `apps/submissions/workflow.py` seul (`transition()`, méta-test) ; transitions des lots suivants déclarées mais refusées jusqu'à leur lot ;
- fichiers des auteurs : règle n° 8 **sans adaptation** (`GESTCONF_PRIVATE_FILES_DIR`, endpoints authentifiés) ; en double aveugle, PDF réécrit sans métadonnées ;
- capacités `submissions.read`, `submissions.extend`, `submissions.export` ; sérialiseurs par rôle, la vue relecteur (RG-04) arrive en L4 ;
- cron : `close_call` et `remind_drafts`, toutes les heures ;
- client de l'API : `npm run api:generate` réécrit l'index en réexportations « étoile » (`web/scripts/api-barrel.mjs`), sans quoi les fonctions d'API gonflent le bundle initial ;
- E2E : `npm run e2e` (Playwright lance Django et le portail ; données préparées par `web/e2e/seed.py`).

Bilan du lot : [`docs/L3-soumission.md`](docs/L3-soumission.md).

## Décisions du lot L4

Les décisions H1 à H19 du plan [`docs/L4-evaluation-plan.md`](docs/L4-evaluation-plan.md) ont été validées le 5 octobre 2026. Elles sont reportées dans l'étude, **§20 « Mises à jour issues du lot L4 »**, qui prévaut sur les sections antérieures (§17 à §19 compris). Points à retenir :

- espace évaluateur dans la gestion (rubrique « Évaluations »), 2FA imposée à `SC_MEMBER` ; capacités `reviews.*`, `decisions.*`, `grids.write` ; le CO n'a aucun accès aux évaluations ;
- RG-04 : tout sérialiseur relecteur dérive de `ReviewerSerializer` ou `ReviewerModelSerializer` (`apps/reviews/anonymity.py`, liste blanche contrôlée par méta-test) ; toute route `reviewer-…` doit figurer dans `LEAK_TESTED_ROUTES` (`apps/reviews/tests/test_anonymity.py`) avec son test de fuite (`test_leaks.py`), sous peine d'échec de la suite ;
- note pondérée calculée par le serveur seul (`apps/reviews/services/scoring.py`, `Decimal`) ; grille verrouillée à la première évaluation (RG-05) ;
- décisions provisoires invisibles des auteurs, transitions et e-mails à la publication seulement (RG-09) ; côté auteur, commentaires sous pseudonymes « Relecteur N », jamais de note ni de commentaire au comité (RG-10) ; `REVISION_REQUESTED` non utilisé (`accepted_minor`) ;
- gardes et effets de l'évaluation inscrits dans le workflow par `register_guard` et `register_effect` (`apps/reviews/apps.py`) : `submissions` ne dépend pas de `reviews` ;
- cron : `remind_reviewers`, toutes les heures ;
- E2E : un seul parcours en série, de l'inscription de l'auteur à sa version finale ; Playwright lance aussi la gestion ; le comité se connecte avec un secret TOTP de test (`web/e2e/seed.py`, `web/e2e/totp.ts`).

Bilan du lot : [`docs/L4-evaluation.md`](docs/L4-evaluation.md).

## Décisions du lot L5

Les décisions I1 à I18 du plan [`docs/L5-programme-plan.md`](docs/L5-programme-plan.md) ont été validées le 6 octobre 2026, avec les propositions de son §10 (lecture seule des autres fonctions du CO, rappel de la confirmation de présentation). Elles sont reportées dans l'étude, **§21 « Mises à jour issues du lot L5 »**, qui prévaut sur les sections antérieures (§17 à §20 compris). Points à retenir :

- application `program` : salles, sessions, créneaux **calculés** par le service ; capacités `program.read`, `program.write` (administrateur, CO « programme »), `program.publish` (Chair seul) ;
- le brouillon s'écrit par `apps/program/services/planning.py` seul : verrou de l'état du programme (`ProgramState`), révision en `If-Match` (412), journal `program.*` ; conflits RG-12 et RG-13 signalés à chaque écriture, publication refusée tant qu'il en reste ;
- **publication** : instantané numéroté en ajout seul, construit par liste blanche ; transitions `CONFIRMED ↔ SCHEDULED` à ce moment seulement ; e-mails aux seules personnes dont le passage change ; le programme public, « Mon passage », l'iCal et le créneau de la soumission lisent l'instantané, **jamais le brouillon** ;
- confirmation de présentation par l'auteur (`CAMERA_READY_RECEIVED → CONFIRMED`, écart validé) ; retraits jusqu'au programme publié ; rappel `remind_presentations` (cron horaire) ;
- programme public **pré-rendu** (une page par jour et par session), visible après `deploy.sh --portal-only` ; ses pages sont annoncées par un fournisseur d'adresses (`register_route_provider` du portail) ;
- gestion : planificateur accessible au clavier (« Placer dans… », flèches, `aria-live`), le CDK n'ayant ni clavier ni ARIA ;
- E2E : le parcours en série se prolonge jusqu'à la publication du programme, « Mon passage » et l'iCal ; le seed crée un CO « programme » et un Chair (2FA).

Bilan du lot : [`docs/L5-programme.md`](docs/L5-programme.md).

## Décisions du lot L6

Les décisions J1 à J16 du plan [`docs/L6-inscriptions-plan.md`](docs/L6-inscriptions-plan.md) ont été validées le 6 octobre 2026 (J15 reportée). Elles sont reportées dans l'étude, **§22 « Mises à jour issues du lot L6 »**, qui prévaut sur les sections antérieures (§17 à §21 compris). Points à retenir :

- applications `registrations` (tarifs, inscriptions) et `payments` (paiements, pièces) ; `registrations` ne dépend pas de `payments` (effets déclarés), ni `program` de `registrations` ;
- capacités `registrations.read`, `registrations.manage` (CO « finances » et « secrétariat »), `pricing.write` (CO « finances »), `finance.read` (Chair, CO « finances ») ; réauthentification pour le paiement manuel, le remboursement, les exports et les mentions de facturation ;
- statut d'une inscription écrit par `apps/registrations/workflow.py` seul (méta-test) ; montants en `Decimal`, exacts dans la devise de l'édition (`apps/core/money.py`), calculés par le serveur seul ;
- **RG-15** : une notification n'est qu'un signal (jeton comparé à temps constant, empreinte seulement) ; seule l'interrogation du statut chez le prestataire confirme ; le navigateur est **dirigé** vers la page hébergée (`location.assign`), jamais par formulaire ; fournisseur factice refusé en production sauf recette déclarée ;
- pièces (RG-14) : facture au paiement, avoir au remboursement, pro forma non comptable ; numéros `<préfixe>-<édition>-<année>-<rang>` sans trou ; ajout seul ; PDF `fpdf2` identiques pour des données identiques, empreinte vérifiée ; aucune facture sans mentions de facturation ;
- RG-11 : conflit `registration` au planificateur quand le paramètre est actif, bloquant à la publication ;
- espace participant **`/compte/mon-inscription`** (`/compte/inscription` reste la création de compte) ; page publique « Inscription » pré-rendue ;
- cron : `expire_registrations` et `sync_payments`, toutes les heures ;
- E2E : le parcours en série se prolonge jusqu'à l'inscription payée par le fournisseur factice, puis au virement, à l'annulation et à l'avoir ; le seed crée un CO « finances » et un second participant.

Bilan du lot : [`docs/L6-inscriptions.md`](docs/L6-inscriptions.md).

## Décisions du lot L7

Les décisions K1 à K17 du plan [`docs/L7-jour-j-plan.md`](docs/L7-jour-j-plan.md) ont été validées le 6 octobre 2026, avec K18 (rôle signataire, Q11) et K19 (modèle officiel et signature électronique, Q14) issues des réponses du commanditaire. Elles sont reportées dans l'étude, **§23 « Mises à jour issues du lot L7 »**, qui prévaut sur les sections antérieures (§17 à §22 compris). Points à retenir :

- application `events` (pointages, signatures, modèles, attestations, lettres) ; rôles `VOLUNTEER` (invitable dès L7, 2FA) et `SIGNATORY` (12ᵉ rôle, 2FA, seul à déposer sa signature) ; capacités `checkin.scan`, `checkin.manage`, `certificates.manage`, `letters.manage`, `signature.manage`, `sessions.chair` (présidence vérifiée session par session) ;
- **QR du badge = titre d'accès** : le serveur n'accepte que le jeton, jamais son empreinte ; badges PDF `fpdf2` générés à la demande, jamais stockés ; badge perdu = nouveau jeton ; une inscription en attente de paiement est refusée à l'accueil ;
- **accueil hors ligne** (PWA sous `/gestion/accueil`, service worker ajouté par cet écran seul) : liste d'empreintes valable 48 heures, file de pointages revérifiée par le serveur (lots de 200, clé d'idempotence), effacées à la déconnexion ; 504 du service worker = serveur injoignable ; `npm run build` régénère `ngsw.json` après la CSP (`scripts/check-ngsw.mjs`) ; décodeur du QR (`jsQR`) préparé dès l'ouverture de l'écran ;
- `SCHEDULED → PRESENTED` par le président de séance (délégation `register_actor_grant` déclarée par `events`), le CO « programme » ou l'administrateur ; correction motivée ;
- **RG-16** vérifiée à l'émission (présence, communication présentée, évaluations envoyées en nombre seulement) ; attestations et lettres en ajout seul, PDF figés à empreinte vérifiée, révocation motivée ; émission par `run_jobs` ; signataire désigné par nature, sans lui rien ne s'émet ; PAdES par `pyHanko` (`GESTCONF_SIGNING_ENCRYPTION_KEYS`), prestataire qualifié non branché (Q17) ;
- vérification publique `/verification/<code>` du portail, rendue dans le navigateur, `noindex`, limitée en débit, même réponse pour un code inconnu ou mal formé ;
- lettres d'invitation instruites par le CO ; numéro de passeport masqué au participant, effacé 30 jours après l'édition (`cleanup`) ; comptoir : inscription d'une personne sans compte ;
- portail : « Mes documents » (`/compte/mes-documents`) ; gestion : rubriques « Jour J » et « Attestations et lettres », l'édition s'ouvre sur l'écran du rôle ;
- aucune ligne de cron nouvelle ; `Permissions-Policy: camera=(self)` sous `/gestion/` seulement ;
- E2E : le parcours en série se prolonge par la signature, la lettre d'invitation, le pointage par caméra simulée sans réseau puis synchronisé, l'entrée de session, « présentée », le comptoir et les attestations vérifiées publiquement ; le seed crée un bénévole, un CO « secrétariat » et un signataire.

Bilan du lot : [`docs/L7-jour-j.md`](docs/L7-jour-j.md).

## Questions ouvertes (étude §15, à ne pas trancher seul)

Date de la conférence, mono- ou multi-conférences, niveau de double aveugle, grille et pondérations définitives, résumé seul ou article complet, tarifs et agrégateur de paiement, entité de facturation, actes (DOI/ISBN), sessions hybrides, noms des auteurs au programme public (Q14), prestataire de signature qualifiée (Q17). (L'emplacement de l'espace évaluateur est tranché : application `gestion`, décision H1 ; les lettres d'invitation par K12 ; le signataire des attestations par K18.)
