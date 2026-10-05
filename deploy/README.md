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
   `DEFAULT_FROM_EMAIL` et la clé du fournisseur d'e-mails (D10), `GESTCONF_PUBLIC_URL`
   (URL publique en `https://`, base des liens envoyés par e-mail), `GESTCONF_OPERATORS`
   (alertes, D17), `GESTCONF_CRON_INTERVAL_SECONDS`, `GESTCONF_MFA_ENCRYPTION_KEYS` (clé
   Fernet chiffrant les secrets de la 2FA, voir « Clés de la 2FA » ci-dessous). Ne jamais le
   committer.
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
6. envoi des fichiers statiques, fusion du `.htaccess` racine ;
7. **publication du portail pré-rendu** (ci-dessous), le backend de cette version étant en
   ligne ; puis tests de fumée.

### Publier le portail (lot L2, E9)

Le portail public est **pré-rendu au build** à partir de l'API publique de production : une
modification faite dans la gestion (contenus, édition, comités) n'y apparaît qu'à la
publication suivante. Le bandeau des écrans « Portail » de la gestion compte les
modifications non publiées.

```bash
deploy/deploy.sh --portal-only   # mêmes variables ; DEPLOY_BASE_URL obligatoire
```

1. lecture de l'édition courante (`/api/v1/public/portal/site`) et de l'heure de début ;
2. `npm run build:portail` avec `GESTCONF_PRERENDER_API_ORIGIN` (défaut : `DEPLOY_BASE_URL`) :
   pré-rendu des pages FR et EN, **contrôle de complétude** (chaque route annoncée par
   `/api/v1/public/portal/routes` doit avoir sa page complète, sinon refus), écriture de
   `sitemap.xml` et de la ligne `Sitemap:` de `robots.txt`, CSP à empreintes ;
3. `rsync --delete` vers la racine web **sans toucher** à `gestion/`, `api/`, `.htaccess`,
   `.well-known/` ;
4. `manage.py mark_portal_published <code> --release <commit> --built-at <début>` : le
   compteur repart de zéro ; une modification faite pendant le build reste comptée.

Le déploiement complet enchaîne cette publication (sauf `SKIP_PORTAL=1`, ou sans
`DEPLOY_BASE_URL` : le portail est alors rendu dans le navigateur, fonctionnel mais non
référencé, jusqu'au prochain `--portal-only`). Planifier la publication (cron) relève de la
décision D18 (déploiement continu), non tranchée.

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
47 3 * * *   $HOME/gestconf-app/deploy/cron.sh check_integrity
```

- `check_integrity` (quotidienne, lecture seule) : doublons d'adresses vérifiées et de 2FA
  (contraintes que MariaDB ne crée pas), cohérence invitations/rôles, taille du cache, tâches
  en échec. Les anomalies partent par e-mail aux opérateurs (`GESTCONF_OPERATORS`), sans
  donnée personnelle ; résumé dans le journal (`integrity.checked`).

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

### Données personnelles (plan L1 §4.9, RG-18)

- Les personnes exportent et anonymisent leur compte elles-mêmes (`/compte/mes-donnees`).
- Demande reçue par courrier ou e-mail, après vérification de l'identité :
  `python manage.py export_user_data --email … --output fichier.json` (droits 600 ; à
  transmettre par un canal sûr, puis à supprimer) et
  `python manage.py anonymize_user --email … --reason …` (irréversible ; refusée tant que la
  personne a un rôle de gestion actif : `revoke_role` d'abord).
- Durées de conservation (D15) : `cleanup` les applique **en simulation** tant que
  `GESTCONF_RETENTION_ENFORCED` est faux ; le résumé (`retention.applied`) indique ce qui
  serait purgé. Ne l'activer qu'après validation des durées par le commanditaire.

### Fichiers déposés (lot L2, E4)

- **Emplacement** : `GESTCONF_FILES_DIR` (défaut : `var/files` dans le dossier de
  l'application), **hors de `public_html`** : Apache ne les sert jamais, l'API les sert
  (`/api/v1/public/files/…` pour les fichiers publiés, avec `nosniff` ; aperçu authentifié
  dans la gestion).
- **Sauvegarde** : ce dossier fait partie de la sauvegarde quotidienne, **avec** la base (une
  ligne `PublicFile` sans son fichier répond 404 ; `check_integrity` le signale :
  `core.public_files_missing`).
- **Nettoyage** : `cleanup` supprime les fichiers orphelins (écrits puis transaction annulée)
  de plus de 24 h (`core.orphan_files`, toujours appliqué).
- **Fichiers des auteurs** (lot L3) : `GESTCONF_PRIVATE_FILES_DIR` (défaut :
  `<GESTCONF_FILES_DIR>/private`), hors de `public_html`, servis par l'API **authentifiée**
  seulement (règle n° 8). Même sauvegarde. `check_integrity` signale un fichier absent du
  disque (`submissions.missing_files`), plus d'un fichier courant par soumission et un trou
  dans les références (`submissions.current_files`, `submissions.references`).
- **Pillow** : roue binaire vérifiée par V28 (`deploy/check-o2switch.sh`). En cas d'échec, le
  repli de E4 s'applique sans changement de code (images non redimensionnées, JPEG portant un
  EXIF refusés) : retirer Pillow de `requirements/base.in`, recompiler, redéployer.

### Clés de la 2FA (plan L1 §4.10)

- **Génération** : `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
- **Sauvegarde** : la clé est conservée **hors de l'hébergement, séparément des sauvegardes de
  la base** (sinon le vol d'une sauvegarde livre aussi la clé). Sa perte rend toutes les 2FA
  inutilisables : chacun devra être réinitialisé (`reset_mfa`) puis se réenrôler.
- **Rotation** (rechiffrement vérifié par test) :
  1. placer la nouvelle clé **en tête** de `GESTCONF_MFA_ENCRYPTION_KEYS`, l'ancienne
     derrière (séparateur : virgule), puis redémarrer Passenger (`tmp/restart.txt`) ;
  2. `python manage.py rotate_mfa_keys --dry-run`, puis `python manage.py rotate_mfa_keys`
     (idempotente, auditée `mfa.keys_rotated`) ;
  3. retirer l'ancienne clé, redémarrer, puis vérifier une connexion 2FA.
- **Perte d'appareil d'un utilisateur** : après vérification de son identité hors bande
  (procédure à valider), `python manage.py reset_mfa --email … --reason …` (audit
  `mfa.reset`, e-mail à l'adresse principale).

## 3. Tests de fumée

```bash
deploy/smoke-test.sh https://conference.exemple.org [version]
```

Vérifie :
- portail : redirection de `/` vers `/fr/` ; si le portail est pré-rendu, pages `/fr/` et
  `/en/call/` complètes, adresse canonique, `hreflang`, Open Graph, `sitemap.xml` et ligne
  `Sitemap:` de `robots.txt` (sinon une ligne INFO, sans échec) ;
- portail : **CSP à empreintes en `<meta>`** sur `/fr/` et sur le repli SPA
  (pages `/compte/*`), en-tête CSP, repli SPA, `robots.txt` servi tel quel (texte) et
  excluant `/api/`, `/gestion/` et `/compte/` ;
- gestion : `base href`, **CSP en `<meta>`**, `X-Robots-Tag: noindex`, repli SPA ;
- authentification : `/api/_allauth/browser/v1/auth/session` répond 401 JSON
  (`is_authenticated: false`) et pose le cookie `csrftoken` ; le client « app » d'allauth est
  absent (404) ;
- API : `/api/v1/health` en 200 avec **base et cache OK** (un `createcachetable` oublié donne
  503 et `cache: error`) et **file de tâches OK** (`jobs: ok` : le cron `run_jobs` est passé
  récemment ; échoue au tout premier déploiement, avant que la crontab ait tourné), `X-Robots-Tag: noindex`, HTTPS vu par Django, version déployée,
  **404 JSON sur une URL d'API inconnue** (preuve que le repli SPA n'intercepte pas
  `/api/`), absence d'admin Django, **diagnostic de l'étape L1.0 désactivé** (404 sur
  `/api/v1/diagnostics/request` : un `GESTCONF_DIAGNOSTICS=1` oublié fait échouer le test).
- fichiers publics : le premier fichier publié du portail est servi par Django (200,
  `nosniff`) ; un fichier inconnu répond 404.

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
