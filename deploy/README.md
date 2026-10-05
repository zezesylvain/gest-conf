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
   `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `GESTCONF_EMAIL_BACKEND`,
   `DEFAULT_FROM_EMAIL` et la clé du fournisseur d'e-mails (D10), `GESTCONF_OPERATORS`
   (alertes, D17), `GESTCONF_CRON_INTERVAL_SECONDS`. Ne jamais le committer.
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

Étapes (étude §11.4) :
1. build Angular par `npm run build` : portail pré-rendu, gestion, puis **CSP à empreintes**
   ajoutée en `<meta>` dans chaque page HTML (`web/scripts/inject-csp.mjs`). Le script
   refuse de publier une page sans cette CSP, y compris avec `SKIP_BUILD=1` ;
2. envoi du code Django (dont les catalogues de traduction `.po` et `.mo` de `locale/`) :
   **contenu versionné du commit déployé uniquement** (`git archive`), jamais un fichier
   ignoré par git du poste local (`.coverage`, `htmlcov/`, `.env.local`…) ;
3. `pip install --require-hashes --only-binary=:all: -r requirements/prod.txt` : fichier
   verrouillé avec empreintes, aucune compilation sur l'hébergement ;
4. **avant** toute modification de la base : `check --deploy --fail-level WARNING`
   (sécurité), puis `check --database default --tag database --fail-level WARNING`
   (connexion et mode strict `mysql.W002` ; sans les contrôles de modèles, dont `models.W036`
   que déclencheront les contraintes conditionnelles d'allauth ignorées par MariaDB) ; puis
   `migrate`, puis `createcachetable` (tables `gestconf_cache` et `gestconf_throttle_cache`
   du cache partagé, sans effet si elles existent) ;
5. redémarrage de Passenger (`tmp/restart.txt`) ;
6. envoi des fichiers statiques, fusion du `.htaccess` racine, tests de fumée.

### Échec en cours de déploiement

Il n'y a **pas de retour arrière automatique**. Si une commande distante échoue après l'envoi
du code (étape 2), le nouveau code est déjà sur le disque, mais Passenger n'est pas redémarré
et `RELEASE` garde l'ancienne valeur. Un processus Passenger créé ensuite (montée en charge,
recyclage) chargera pourtant le nouveau code, éventuellement avec une base non migrée. Corriger
la cause et relancer `deploy.sh` (toutes les étapes sont idempotentes), ou redéployer l'ancien
commit (`git checkout <ancien commit>` puis `deploy.sh`). Les contrôles passent avant `migrate`
pour qu'un avertissement n'arrête jamais le déploiement entre deux migrations appliquées.

### Le `.htaccess` racine

cPanel écrit ses directives Passenger dans un `.htaccess`. Le script ne remplace
donc **que** le bloc délimité par `# BEGIN GEST-CONF` / `# END GEST-CONF`
(`htaccess_merge.py`, testé) ; une copie de l'ancien fichier est conservée dans
`deploy/backups/` (non versionné). Les dossiers `api/`, `.well-known/` et
`cgi-bin/` de `public_html` ne sont jamais touchés.

### Commandes planifiées (cron)

Les tâches asynchrones (envoi des e-mails…) sont des lignes de la table `Job`, exécutées par
`run_jobs` (règle n° 9 : ni Celery ni Redis). `deploy.sh` dépose `deploy/cron.sh` dans le
dossier de l'application et y écrit le chemin du venv (`VENV_ACTIVATE`) : le cron charge le
**même** venv et le **même** `.env` que Passenger. À déclarer une fois dans cPanel › Tâches Cron
(intervalle de `run_jobs` selon la fréquence minimale relevée en L1.0, contrôle M01 / H-6 ;
`--max-seconds` inférieur à l'intervalle) :

```text
*/5 * * * *  $HOME/gestconf-app/deploy/cron.sh run_jobs --max-seconds 240
17 3 * * *   $HOME/gestconf-app/deploy/cron.sh cleanup
```

- Sorties dans `~/gestconf-app/logs/cron-<commande>.log` (rotation à 5 Mio), jamais sur la
  sortie standard : cron n'envoie pas d'e-mail à chaque passage.
- Les commandes sont **verrouillées** (`flock` dans `tmp/`, ou `GET_LOCK` avec
  `GESTCONF_COMMAND_LOCK=database`, décision H-5) et idempotentes : un chevauchement sort
  proprement. La réservation conditionnelle des jobs empêche de toute façon un double envoi.
- Supervision : `/api/v1/health` renvoie `jobs: late` après trois intervalles
  (`GESTCONF_CRON_INTERVAL_SECONDS`) sans passage réussi, `unknown` avant le premier passage.
- `cleanup` purge les sessions expirées et les corps d'e-mails à jeton non envoyés depuis
  24 h ; les autres durées de D15 restent **en simulation** (`GESTCONF_RETENTION_ENFORCED`).
- **Jalon J-tech** : `python manage.py send_test_email <adresse>` (en SSH, venv activé,
  `DJANGO_SETTINGS_MODULE=config.settings.prod`) met un e-mail en file ; le passage suivant du
  cron l'envoie. Contrôler la réception (SPF et DKIM valides dans les en-têtes), puis
  `python manage.py outbox` (statut `sent`).

## 3. Tests de fumée

```bash
deploy/smoke-test.sh https://conference.exemple.org [version]
```

Vérifie :
- portail : page pré-rendue, **CSP à empreintes en `<meta>`** sur `/` et sur le repli SPA
  (pages `/compte/*`), en-tête CSP, repli SPA, `robots.txt` servi tel quel (texte) et
  excluant `/api/`, `/gestion/` et `/compte/` ;
- gestion : `base href`, **CSP en `<meta>`**, `X-Robots-Tag: noindex`, repli SPA ;
- API : `/api/v1/health` en 200 avec **base et cache OK** (un `createcachetable` oublié donne
  503 et `cache: error`) et **file de tâches OK** (`jobs: ok` : le cron `run_jobs` est passé
  récemment ; échoue au tout premier déploiement, avant que la crontab ait tourné), `X-Robots-Tag: noindex`, HTTPS vu par Django, version déployée,
  **404 JSON sur une URL d'API inconnue** (preuve que le repli SPA n'intercepte pas
  `/api/`), absence d'admin Django, **diagnostic de l'étape L1.0 désactivé** (404 sur
  `/api/v1/diagnostics/request` : un `GESTCONF_DIAGNOSTICS=1` oublié fait échouer le test).

Les en-têtes JSON sont lus avec tolérance aux espaces. Validé localement contre le build de
production et Django en réglages de production (y compris les contre-épreuves : pages sans
CSP, `robots.txt` absent, table de cache absente) ; pas encore sur o2switch.

## 4. Vérifications de l'hébergement (étape L1.0)

Le script **en lecture seule** `deploy/check-o2switch.sh`, lancé en SSH, relève ce qui doit
l'être sur le serveur (Python, glibc, roues binaires de `cryptography`, MariaDB et son mode
SQL, verrous, outils, accès HTTPS sortants, venv cPanel, bloc Passenger…) sans afficher aucun
secret :

```bash
ssh compte@serveur 'bash -s' < deploy/check-o2switch.sh | tee check-o2switch.txt
```

Résultats et contrôles manuels (cron, upload, mesure de `GESTCONF_TRUSTED_PROXY_COUNT`,
sauvegardes…) : fiche [`docs/L1-verifications-o2switch.md`](../docs/L1-verifications-o2switch.md).

### Points hérités du lot L0

Ils ont été validés sur une simulation locale (Apache 2.4 + `.htaccess`, Django
en configuration de production, Chromium), **pas encore sur o2switch**. Chacun est repris
dans la fiche L1.0 (dans l'ordre : M02 ; M05 ; M05 ; V06 et V04 ; M10 ; M01) :

- [ ] Emplacement exact du bloc Passenger écrit par cPanel (`public_html/.htaccess`
      ou `public_html/api/.htaccess`) et absence de conflit avec nos règles.
- [ ] Passenger transmet-il `/api` dans `SCRIPT_NAME` ? (Indifférent pour le code :
      `config/mount.py` gère les deux cas.)
- [ ] `secure: true` dans `/api/v1/health` en HTTPS : sinon, ne pas activer
      `DJANGO_SECURE_SSL_REDIRECT` et garder `DJANGO_CSRF_TRUSTED_ORIGINS`.
- [ ] Version de MariaDB ≥ 10.5 ; installation de PyMySQL sans compilation.
- [ ] Modules Apache `mod_rewrite` et `mod_headers` actifs (sinon en-têtes absents).
- [ ] Fréquence minimale du cron (intervalle de `run_jobs`, `deploy/cron.sh`).
