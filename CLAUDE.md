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

## Structure du dépôt (cible)

```text
GEST-CONF/
├── CLAUDE.md
├── Etude_fonctionnelle_et_technique_GEST-CONF.md / .html
├── backend/                 # Django
│   ├── config/settings/ (base, dev, prod) ; urls.py (API uniquement) ; passenger_wsgi.py
│   ├── apps/ core, accounts, conferences, committees, submissions, reviews,
│   │         program, registrations, payments, events, communications,
│   │         sponsors, logistics, reports
│   ├── tests/
│   └── requirements/ (base, prod, dev)
└── web/                     # Angular
    └── projects/ portail, gestion, shared (api-client généré, auth, ui-kit, i18n)
```

Chaque app Django : `models.py`, `services.py` (logique métier), `serializers.py` (par rôle si champs sensibles), `permissions.py`, `views.py`, `urls.py`, `tests/`. **La logique métier va dans `services.py`**, pas dans les vues ni les modèles.

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
ruff check . ../deploy && ruff format --check . ../deploy
python manage.py spectacular --file schema.yml --validate   # schéma OpenAPI (versionné)

# Frontend (Node >= 22.22.3 ou >= 24.15, exigence d'Angular 22)
cd web && npm ci
npm run start:portail       # :4200 ; npm run start:gestion -> :4201/gestion/ (proxy /api -> :8000)
npm test && npm run lint && npm run format:check
npm run build               # portail pré-rendu + gestion + CSP à empreintes
npm run api:generate        # régénérer le client TypeScript après chaque évolution du schéma

# Déploiement : deploy/deploy.sh puis deploy/smoke-test.sh (voir deploy/README.md)
# Cron (deploy/cron.sh) : run_jobs (toutes les 5 min), cleanup et check_integrity (quotidiennes)
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
- **Non vérifié, à confirmer avant de s'appuyer dessus** : version de MariaDB, fréquence minimale du cron, limites de ressources, sous-domaines autorisés, antivirus, compilation de `mysqlclient` (utiliser `PyMySQL` par défaut). Ne pas affirmer ces points sans vérification.
- Sauvegarde quotidienne base + fichiers, copie hors hébergement, restauration testée.

## Méthode de travail attendue

- Avancer **par lots** (étude §14) : socle → portail → soumission → évaluation/décision (MVP) → programme → inscriptions → jour J → logistique/reporting → recette. Ne pas anticiper un lot ultérieur sans accord.
- Priorités : P1 (MVP) > P2 (V1) > P3 (V2). Ne pas implémenter du P3 tant que le P1 n'est pas livré.
- Avant toute modification large (modèle de données, permissions, workflow de statuts), proposer le plan et attendre validation.
- Une règle de gestion (RG-xx) implémentée = un test qui la référence dans son nom ou sa docstring.
- Être rigoureux et critique : signaler les incohérences de l'étude, les risques de sécurité et les hypothèses non vérifiées plutôt que de les contourner. Ne pas inventer d'API de bibliothèque : vérifier dans la documentation ou le code installé.

## Décisions du lot L1

Les décisions D1 à D18 du plan [`docs/L1-socle-plan.md`](docs/L1-socle-plan.md) ont été validées le 5 octobre 2026 : elles s'appliquent (notamment D1 : aucun rôle global, autorité de plateforme exercée par des commandes `manage.py` auditées). Elles sont reportées dans l'étude, **§17 « Mises à jour issues du lot L1 »**, qui prévaut sur les sections antérieures en cas de divergence. Bilan du lot et exploitation : [`docs/L1-socle.md`](docs/L1-socle.md).

## Questions ouvertes (étude §15, à ne pas trancher seul)

Date de la conférence, mono- ou multi-conférences, niveau de double aveugle, grille et pondérations définitives, résumé seul ou article complet, tarifs et agrégateur de paiement, entité de facturation, actes (DOI/ISBN), sessions hybrides, lettres d'invitation, emplacement de l'espace évaluateur (proposé : application `gestion`).
