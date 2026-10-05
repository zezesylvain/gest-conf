# GEST-CONF

Plateforme de gestion de conférences scientifiques : portail public, espace de gestion
(comités, administration), espaces auteurs, évaluateurs, intervenants et participants.

- **Étude fonctionnelle et technique** (source de vérité) : [`Etude_fonctionnelle_et_technique_GEST-CONF.md`](Etude_fonctionnelle_et_technique_GEST-CONF.md)
- **Règles de développement** : [`CLAUDE.md`](CLAUDE.md)
- **Avancement** : lot L0 (squelette et prototype de déploiement) — voir [`docs/L0-prototype-deploiement.md`](docs/L0-prototype-deploiement.md)
- **Lot L1 (socle)** : plan **validé** (D1–D18), en cours de réalisation — voir [`docs/L1-socle-plan.md`](docs/L1-socle-plan.md)

## Architecture en bref

Un seul domaine sur l'hébergement o2switch :

| URL | Contenu | Code |
|---|---|---|
| `/` | Portail public Angular, **pré-rendu** (fichiers statiques) | `web/projects/portail` |
| `/gestion/` | Espace de gestion Angular | `web/projects/gestion` |
| `/api/` | API REST Django (DRF) via Passenger | `backend/` |

Code partagé entre les deux applications Angular (client API généré, i18n FR/EN,
composants communs) : `web/projects/shared`, importé sous le nom `@gestconf/shared`.

```text
backend/            Django 5.2 LTS + DRF (sans admin Django)
  config/           réglages (base, dev, test, prod), urls, wsgi, montage /api
  apps/core/        socle : santé, erreurs (catalogue ErrorCode, DomainError), CSRF,
                    Actor, pagination, IP du client, middlewares, modèle horodaté
  apps/accounts/    utilisateur (identifié par e-mail)
  locale/           catalogue « en » des messages de l'API (.po et .mo versionnés)
  requirements/     *.in (sources) → *.txt verrouillés avec empreintes (pip-tools)
  schema.yml        schéma OpenAPI (généré, source du client TypeScript)
web/                workspace Angular 22 (portail, gestion, shared)
  scripts/          post-build : CSP à empreintes
deploy/             déploiement o2switch : .htaccess, script, tests de fumée
.github/workflows/  intégration continue
```

## Prérequis

- Python 3.12 ou 3.13
- Node.js **≥ 22.22.3** ou **≥ 24.15** (exigence d'Angular 22) — voir `web/.nvmrc`
- MariaDB ≥ 10.5 (exigence de Django 5.2) recommandée ; SQLite possible pour démarrer

## Démarrage rapide

### API Django

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements/dev.txt   # fichier verrouillé, empreintes vérifiées
cp .env.example .env          # puis renseigner DATABASE_URL (sinon : SQLite)
python manage.py migrate
python manage.py createcachetable   # table du cache partagé (gestconf_cache)
python manage.py runserver    # http://localhost:8000/api/v1/health
```

Le cache partagé (limites de débit, sonde `/health`) est une table en base : sans
`createcachetable`, `/api/v1/health` répond 503 avec `"cache": "error"`. La commande est
sans effet si la table existe déjà ; elle se relance après chaque `migrate` (déploiement compris).

En développement, la documentation interactive de l'API est servie sur
`http://localhost:8000/api/v1/docs`.

### Applications Angular

```bash
cd web
npm ci
npm run start:portail         # http://localhost:4200/
npm run start:gestion         # http://localhost:4201/gestion/
```

Les deux serveurs de développement relaient `/api` vers `runserver` (`web/proxy.conf.json`).

## Commandes utiles

| Objet | Commande |
|---|---|
| Tests backend | `cd backend && pytest` (SQLite ; `DATABASE_URL=mysql://...` pour MariaDB, qui fait foi en CI) |
| Couverture backend | `pytest --cov` (`--cov-report=html` pour le détail ; configuration dans `pyproject.toml`) |
| Qualité backend | `ruff check . ../deploy && ruff format --check . ../deploy` |
| Cache partagé | `python manage.py createcachetable` (après chaque `migrate`) |
| Schéma OpenAPI | `python manage.py spectacular --file schema.yml --validate --fail-on-warn` |
| Traductions de l'API | voir ci-dessous |
| Dépendances Python | `requirements/compile.sh` — voir ci-dessous |
| Client TypeScript | `cd web && npm run api:generate` (après chaque évolution du schéma) |
| Tests frontend | `cd web && npm test` |
| Lint / format frontend | `npm run lint` · `npm run format:check` |
| Build de production | `npm run build` (portail pré-rendu + gestion + CSP) |
| Déploiement | `deploy/deploy.sh` — voir [`deploy/README.md`](deploy/README.md) |

### Traductions de l'API

Les messages de l'API sont écrits en français dans le code (`LANGUAGE_CODE = "fr"`) et
traduits en anglais dans `backend/locale/en/LC_MESSAGES/django.po`. La langue suit l'en-tête
`Accept-Language` de la requête (`LocaleMiddleware`). Les `.po` **et** les `.mo` compilés
sont versionnés : gettext n'est pas garanti sur l'hébergement. Après toute modification
d'un message (gettext requis en local : `apt-get install gettext`) :

```bash
cd backend
python manage.py makemessages -l en --add-location=file   # puis traduire les msgstr vides
python manage.py compilemessages -l en --ignore=.venv       # --ignore : ne pas recompiler le venv
```

La CI vérifie que les `.po` et les `.mo` versionnés sont à jour avec `backend/locale/check.sh`
(utilisable en local, venv actif) : les `.mo` sont comparés **décompilés** (`msgunfmt`), car le
binaire produit par `msgfmt` dépend de sa version ; les `.po` sont régénérés sur une copie du
backend, sans toucher à l'arbre de travail, et ne doivent contenir aucune entrée non traduite,
approximative ou obsolète.

### Dépendances Python

Les fichiers `backend/requirements/*.txt` sont **verrouillés avec empreintes** (pip-tools,
`--generate-hashes`) : toutes les dépendances, transitives comprises, sont figées et
vérifiées à l'installation. On ne les modifie jamais à la main : on modifie le fichier
source `*.in` (`base.in` exécution, `prod.in` production, `dev.in` outils), puis on
recompile, **avec Python 3.12**, dans le venv du backend :

```bash
cd backend
requirements/compile.sh                            # après modification d'un .in
requirements/compile.sh --upgrade-package django   # montée de version ciblée
pip install -r requirements/dev.txt                # mettre le venv à jour
```

Les fichiers compilés doivent aussi s'installer sous Python 3.13 (la CI teste les deux
versions). `pip-audit -r requirements/prod.txt` contrôle les vulnérabilités connues.
