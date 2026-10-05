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
  apps/core/        socle : santé, format d'erreur normalisé, modèle horodaté
  apps/accounts/    utilisateur (identifié par e-mail)
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
pip install -r requirements/dev.txt
cp .env.example .env          # puis renseigner DATABASE_URL (sinon : SQLite)
python manage.py migrate
python manage.py runserver    # http://localhost:8000/api/v1/health
```

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
| Tests backend | `cd backend && pytest` (SQLite ; `DATABASE_URL=mysql://...` pour MariaDB) |
| Qualité backend | `ruff check . && ruff format --check .` |
| Schéma OpenAPI | `python manage.py spectacular --file schema.yml --validate` |
| Client TypeScript | `cd web && npm run api:generate` (après chaque évolution du schéma) |
| Tests frontend | `cd web && npm test` |
| Lint / format frontend | `npm run lint` · `npm run format:check` |
| Build de production | `npm run build` (portail pré-rendu + gestion + CSP) |
| Déploiement | `deploy/deploy.sh` — voir [`deploy/README.md`](deploy/README.md) |
