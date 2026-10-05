# Déploiement sur o2switch

Topologie (étude §11.3) : un seul domaine, Angular en fichiers statiques dans
`public_html/`, Django servi par Passenger sous `/api`.

```text
~/public_html/              portail (pré-rendu) + .htaccess
~/public_html/gestion/      espace de gestion + .htaccess
~/gestconf-app/             code Django, .env de production, passenger_wsgi.py
~/virtualenv/gestconf-app/  environnement Python créé par cPanel
```

## 1. Installation initiale (une fois)

1. **Base de données** (cPanel › Bases de données MySQL) : créer la base et
   l'utilisateur, interclassement `utf8mb4_unicode_ci`. Relever la **version de
   MariaDB** : Django 5.2 exige MariaDB ≥ 10.5.
2. **Application Python** (cPanel › Setup Python App) :
   - version de Python : 3.12 (ou 3.13) ;
   - *Application root* : `gestconf-app` (hors de `public_html`) ;
   - *Application URL* : `<domaine>/api` ;
   - *Application startup file* : `passenger_wsgi.py` ; *Entry point* : `application` ;
   - variable d'environnement : `DJANGO_SETTINGS_MODULE=config.settings.prod`.
   Noter le chemin du script `activate` affiché par cPanel.
3. **Fichier `.env`** de production dans `~/gestconf-app/.env` (droits `600`), à
   partir de `backend/.env.example` : `DJANGO_SECRET_KEY`, `DATABASE_URL`,
   `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`. Ne jamais le committer.
4. **HTTPS** : vérifier le certificat AutoSSL et activer « Forcer la redirection
   HTTPS » dans cPanel › Domaines. La redirection n'est pas faite dans notre
   `.htaccess` pour éviter toute boucle si Apache est derrière un proxy.

## 2. Déployer une version

Depuis un poste disposant d'un accès SSH (clé) au compte o2switch, sur un arbre
de travail propre :

```bash
export DEPLOY_SSH=compte@serveur.o2switch.net
export DEPLOY_VENV_ACTIVATE=/home/compte/virtualenv/gestconf-app/3.12/bin/activate
export DEPLOY_BASE_URL=https://conference.exemple.org
deploy/deploy.sh
```

Étapes (étude §11.4) : build Angular → envoi du code Django → `pip install`,
`migrate`, `check --deploy` → redémarrage de Passenger (`tmp/restart.txt`) →
envoi des fichiers statiques → fusion du `.htaccess` racine → tests de fumée.

### Le `.htaccess` racine

cPanel écrit ses directives Passenger dans un `.htaccess`. Le script ne remplace
donc **que** le bloc délimité par `# BEGIN GEST-CONF` / `# END GEST-CONF`
(`htaccess_merge.py`, testé) ; une copie de l'ancien fichier est conservée dans
`deploy/backups/` (non versionné). Les dossiers `api/`, `.well-known/` et
`cgi-bin/` de `public_html` ne sont jamais touchés.

## 3. Tests de fumée

```bash
deploy/smoke-test.sh https://conference.exemple.org [version]
```

Vérifie : page pré-rendue, en-tête CSP, replis SPA du portail et de la gestion,
santé de l'API et de la base, HTTPS vu par Django, version déployée, **404 JSON
sur une URL d'API inconnue** (preuve que le repli SPA n'intercepte pas `/api/`),
absence d'admin Django.

## 4. Points à valider sur l'hébergement réel (lot L0)

Ils ont été validés sur une simulation locale (Apache 2.4 + `.htaccess`, Django
en configuration de production, Chromium), **pas encore sur o2switch** :

- [ ] Emplacement exact du bloc Passenger écrit par cPanel (`public_html/.htaccess`
      ou `public_html/api/.htaccess`) et absence de conflit avec nos règles.
- [ ] Passenger transmet-il `/api` dans `SCRIPT_NAME` ? (Indifférent pour le code :
      `config/mount.py` gère les deux cas.)
- [ ] `secure: true` dans `/api/v1/health` en HTTPS : sinon, ne pas activer
      `DJANGO_SECURE_SSL_REDIRECT` et garder `DJANGO_CSRF_TRUSTED_ORIGINS`.
- [ ] Version de MariaDB ≥ 10.5 ; installation de PyMySQL sans compilation.
- [ ] Modules Apache `mod_rewrite` et `mod_headers` actifs (sinon en-têtes absents).
- [ ] Fréquence minimale du cron (pour la future commande `run_jobs`).
