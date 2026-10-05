# Vérifications o2switch : fiche de l'étape L1.0

Cette fiche consigne les vérifications de l'hébergement prévues à l'étape L1.0 du plan L1
(`docs/L1-socle-plan.md`, §13, §14.1 risques R1 à R6 et R19, §14.2). Elle est **à remplir sur le
serveur réel** : aucune ligne n'a encore été vérifiée sur o2switch. Le critère de fin de L1.0
est : fiche remplie, décisions bloquantes (§5) validées.

Deux types de contrôles :
- **automatiques (V00 à V27)** : `deploy/check-o2switch.sh`, script en lecture seule lancé en SSH ;
- **manuels (M01 à M10)** : cPanel, navigateur ou `curl` depuis le poste local (procédures au §4).

**Mode SQL de MariaDB.** Depuis L1.1, l'application impose son mode SQL à chaque connexion
(`OPTIONS["init_command"]`, réglage `MARIADB_SQL_MODE` de `backend/config/settings/base.py` :
`STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION`). Le `sql_mode` global du
serveur (V08) n'est donc relevé que pour mémoire. Ce qui compte est que MariaDB **accepte** ce mode
à la connexion (V09) et que `check --database default` ne signale plus `mysql.W002` une fois L1.1
déployée (V25). Si c'est le cas, le risque R19 est levé.

## 0. Relevé

| Date | Compte et serveur | Commit du script | Opérateur |
|---|---|---|---|
| _à remplir_ | _à remplir_ | _à remplir_ | _à remplir_ |

## 1. Lancer le script

Prérequis (voir `deploy/README.md` §1) : accès SSH par clé au compte ; base MariaDB créée ; fichier
`~/gestconf-app/.env` déposé (droits 600) avec `DATABASE_URL`. L'application Python créée dans
« Setup Python App » et le code déployé sont facultatifs : les contrôles qui en dépendent (V04, V22,
V24, V25) l'indiquent.

Depuis le poste local, à la racine du dépôt :

```bash
ssh compte@serveur 'bash -s' < deploy/check-o2switch.sh | tee check-o2switch.txt
# Autres emplacements :
ssh compte@serveur 'bash -s -- --app-dir ~/gestconf-app --public-dir ~/public_html' < deploy/check-o2switch.sh
```

Ce que fait le script :
- il n'écrit que dans un dossier temporaire créé dans `$HOME` (venv jetable, programmes de contrôle)
  et dans un fichier de verrou temporaire de `~/gestconf-app/tmp/`, supprimés à la sortie ;
- il n'affiche **aucun secret** : le `.env` est lu par un programme Python qui n'en affiche aucune
  valeur, les erreurs MariaDB sont réduites à leur code, les valeurs des `SetEnv` des `.htaccess`
  sont masquées et la sortie de `manage.py check` est filtrée. Relire tout de même la sortie avant
  de la diffuser ;
- il termine par un **récapitulatif** trié par identifiant, à reporter dans la colonne « Obtenu » ;
- code de sortie 1 s'il y a au moins un ÉCHEC.

Le lancer **deux fois** : avant le premier déploiement de L1.1, puis après (V25 et M10).

`--no-network` saute les téléchargements et les accès HTTPS sortants (V03, V04, V19 à V21).

## 2. Contrôles automatiques (`deploy/check-o2switch.sh`)

| N° | Contrôle | Comment | Attendu | Obtenu | Conséquence / décision selon le résultat |
|---|---|---|---|---|---|
| V00 | Système | Script : `/etc/os-release`, `uname`, nom d'hôte | Informatif (CloudLinux ou AlmaLinux probable, non vérifié) | _à remplir_ | Aucune ; contexte des autres lignes |
| V01 | Python 3.12 ou 3.13 disponible | Script : `/opt/alt/python3*/bin/python3` (Python de CloudLinux utilisés par « Setup Python App ») et `PATH` ; recouper avec la liste de versions proposée par « Setup Python App » | 3.12 et/ou 3.13 | _à remplir_ | 3.12 : choix par défaut (fichiers verrouillés compilés en 3.12). 3.13 seul : acceptable (CI et installation verrouillée vérifiées en 3.13). Ni l'un ni l'autre : **bloquant**, escalade |
| V02 | glibc ≥ 2.17 | Script : `getconf GNU_LIBC_VERSION`, sinon `ldd --version` | ≥ 2.17 (roues manylinux2014) ; ≥ 2.28 donne accès aux roues manylinux_2_28 | _à remplir_ | < 2.17 : R1, pas de roue binaire pour `cryptography`, donc 2FA d'allauth compromise. Repli `django-otp` et étape maison (+3 à 4 j-h), **décision du commanditaire**. Pour mémoire, `cryptography` 50.0.2 publie encore des roues manylinux2014 (vérifié le 2026-10-05) |
| V03 | `cryptography` et `fido2` en roues binaires | Script : venv jetable (même Python que le venv de l'application s'il existe), `pip install --only-binary=:all: cryptography==50.0.2 fido2==2.2.1` (versions prévues pour L1.3 et L1.6, et non la dernière publiée ; à réaligner sur le fichier verrouillé quand elles y entreront), puis import et chiffrement Fernet. Ce venv ne sert jamais aux contrôles MariaDB | OK, avec la version, l'étiquette de la roue et la version d'OpenSSL embarquée | _à remplir_ | ÉCHEC : R1, même conséquence que V02. Si le message cite le réseau, voir V21 |
| V04 | Dépendances verrouillées installables en roues | Script : `pip install --dry-run --require-hashes --only-binary=:all: -r ~/gestconf-app/requirements/prod.txt` (si le code est déployé), avec **le pip du venv de l'application** s'il existe (celui qu'utilise `deploy.sh`), sinon celui du venv jetable ; version de pip affichée | OK | _à remplir_ | ÉCHEC : `deploy.sh` échouera aussi (il installe avec `--require-hashes --only-binary=:all:`). Identifier le paquet dans le message, puis épingler une version qui a une roue, ou, après accord, autoriser sa compilation sur le serveur (non garantie) |
| V05 | Connexion à MariaDB | Script : PyMySQL avec les identifiants de `DATABASE_URL`, décodés comme le fait django-environ. PyMySQL est celui du venv de l'application (installé par `deploy.sh` depuis `prod.txt`, empreintes vérifiées) ; à défaut, un venv dédié qui ne contient que PyMySQL, **version et empreintes de `prod.txt`** (`--require-hashes --no-deps`) | OK (hôte et port affichés) | _à remplir_ | 1045 : vérifier l'encodage `%XX` des caractères spéciaux dans `DATABASE_URL` et le rattachement de l'utilisateur à la base (cPanel). **Mot de passe ASCII conseillé** : PyMySQL 1.2.3 encode le mot de passe en latin-1 (`pymysql/connections.py:314`) et refuse donc un mot de passe UTF-8 non ASCII (constaté en essai local). 2003 : hôte ou port |
| V06 | MariaDB ≥ 10.5 | Script : `SELECT VERSION()` | ≥ 10.5 (exigence de Django 5.2) | _à remplir_ | < 10.5 ou MySQL : **bloquant** (R2). Dans tous les cas, aligner l'image de la CI (`mariadb:10.11` dans `.github/workflows/ci.yml`) sur la version relevée (décision H-1 du §5) |
| V07 | `SKIP LOCKED` | Script : version ≥ 10.6 | Informatif | _à remplir_ | Aucune : la file `Job` ne l'utilise pas (plan §8.2) |
| V08 | `sql_mode` global du serveur | Script : `SELECT @@GLOBAL.sql_mode` | Informatif | _à remplir_ | Aucune depuis L1.1 : l'application impose son propre mode (V09). Non strict : le code L0, lui, était exposé aux troncatures silencieuses (R19), d'où l'ÉCHEC attendu de V25 avant le déploiement de L1.1 |
| V09 | Mode SQL imposé par connexion accepté | Script : connexion avec `init_command = SET SESSION sql_mode='…'`, puis lecture de `@@SESSION.sql_mode` | Exactement `STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION` | _à remplir_ | OK : R19 levé. ÉCHEC : R19 ouvert, troncatures silencieuses possibles ; interroger o2switch. En attendant : clés de longueur fixe et longueurs validées dans les sérialiseurs (§3.1) |
| V10 | `utf8mb4` et `utf8mb4_unicode_ci` | Script : jeu et interclassement du serveur, de la base et des tables existantes | Base et tables en `utf8mb4` / `utf8mb4_unicode_ci` (comme la base de test de la CI) | _à remplir_ | ÉCHEC : avant toute donnée réelle, `ALTER DATABASE … CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci` (phpMyAdmin). Tables déjà créées en L0 : `ALTER TABLE … CONVERT TO …`, ou recréation de la base (aucune donnée réelle en L1, D18) |
| V11 | Moteur InnoDB | Script : `@@default_storage_engine` et moteur des tables existantes | InnoDB partout | _à remplir_ | ÉCHEC : recréer les tables concernées. `NO_ENGINE_SUBSTITUTION` (V09) refuse désormais une création hors InnoDB |
| V12 | `GET_LOCK` / `RELEASE_LOCK` exclusifs | Script : verrou pris par une connexion, refusé à une seconde, libéré, puis repris | OK | _à remplir_ | ÉCHEC : pas de repli par la base pour `LockedCommand`. On s'appuie sur `flock` (V15) et sur la réservation conditionnelle des jobs (R6, §8.2) |
| V13 | Limites MariaDB | Script : `max_user_connections`, `max_connections`, `wait_timeout`, `max_allowed_packet` | Informatif | _à remplir_ | `max_user_connections` bas (moins de 10) : limiter les processus Passenger et ne pas chevaucher les cron. `wait_timeout` court : garder `CONN_MAX_AGE = 0` (valeur actuelle) |
| V14 | Tables de fuseaux (`CONVERT_TZ`) | Script | Informatif | _à remplir_ | Aucune : `CONVERT_TZ` n'est pas utilisé, les dates sont en UTC (C9) |
| V15 | `flock` exclusif entre deux processus | Script : `fcntl.flock` (celui de `LockedCommand`) dans `~/gestconf-app/tmp/`, second processus refusé puis accepté | « busy acquired », système de fichiers local | _à remplir_ | ÉCHEC : `LockedCommand` utilise `GET_LOCK` (V12) ; si V12 échoue aussi, R6 (réservation conditionnelle seule) |
| V16 | Systèmes de fichiers | Script : type et option `noexec` de `/tmp`, `$HOME` et du dossier de l'application | Informatif | _à remplir_ | NFS : `flock` peu fiable (V15 tranche). `/tmp` en `noexec` : ne rien y exécuter (le script et `cron.sh` utilisent `$HOME`) |
| V17 | gettext (`msgfmt`) | Script | Informatif (probablement absent) | _à remplir_ | Aucune : les `.mo` sont versionnés et vérifiés en CI (`backend/locale/check.sh`) |
| V18 | `mysqldump` / `mariadb-dump` | Script | Présent | _à remplir_ | Absent : sauvegarde de la base uniquement par cPanel (M06) ; la future commande `backup_db` est à revoir |
| V19 | HTTPS sortant vers `api.brevo.com` | Script : `curl` sur `/v3/account`, sans clé | Une réponse HTTP (401 attendu) : DNS, connexion et TLS fonctionnent | _à remplir_ | ÉCHEC : Brevo inutilisable depuis le serveur (D10) ; prendre Mailjet si V20 est OK, sinon SMTP d'o2switch en secours, et demander l'ouverture à o2switch |
| V20 | HTTPS sortant vers `api.mailjet.com` | Script : `curl` sur `/v3/REST/user`, sans clé | Une réponse HTTP (401 attendu) | _à remplir_ | Idem V19 pour Mailjet |
| V21 | HTTPS sortant vers PyPI | Script : `pypi.org/simple/pip/` et `files.pythonhosted.org` | Une réponse HTTP (200, ou 404 sur la racine de `files.pythonhosted.org`) | _à remplir_ | ÉCHEC : `deploy.sh` ne peut pas installer les dépendances ; prévoir un dossier de roues transféré par rsync (à concevoir) |
| V22 | Venv cPanel de l'application | Script : `~/virtualenv/<racine de l'application>/<version>/bin/activate`, version de Python et **version de pip** de ce venv | Chemin trouvé, par exemple `~/virtualenv/gestconf-app/3.12/bin/activate` ; pip ≥ 22.2 | _à remplir_ | Reporter ce chemin dans `DEPLOY_VENV_ACTIVATE` et dans `deploy/cron.sh` (L1.2). Absent : créer l'application dans « Setup Python App » (`deploy/README.md` §1) |
| V23 | Fichier `.env` | Script : droits et emplacement | Droits 600, hors de `public_html` | _à remplir_ | ÉCHEC : `chmod 600`, ou déplacer le fichier hors de la racine web |
| V24 | Bloc Passenger dans les `.htaccess` | Script : directives `Passenger*` de `public_html/.htaccess` et `public_html/api/.htaccess` (valeurs de `SetEnv` masquées), position du bloc GEST-CONF | Bloc CloudLinux trouvé, `PassengerBaseURI "/api"` | _à remplir_ (fichier et lignes) | Voir M02. Si des `SetEnv` portent des secrets saisis dans « Setup Python App », ils sont en clair dans un `.htaccess` : préférer le `.env` (droits 600) et les retirer de cPanel |
| V25 | `check --database default --tag database` | Script : `manage.py check --database default --tag database` dans le venv de l'application (sortie filtrée ; contrôles de la base seulement, sans les contrôles de modèles comme `models.W036`) | Après le déploiement de L1.1 : aucun `mysql.W002` | _à remplir_ (avant / après L1.1) | Avant L1.1 avec un serveur non strict : ÉCHEC attendu (code L0 sans `init_command`). Après L1.1 : ÉCHEC = V09 en échec, voir V09 |
| V26 | Processus et limites du compte | Script : processus Passenger visibles, nombre de CPU, `ulimit` | Informatif | _à remplir_ | À recouper avec M07 |
| V27 | Format de ligne InnoDB | Script : `@@innodb_default_row_format`, `@@innodb_page_size` et `ROW_FORMAT` des tables InnoDB existantes (`information_schema.TABLES`) | Format `DYNAMIC` (ou `COMPRESSED`), pages ≥ 8 Kio | _à remplir_ | Index utf8mb4 longs : clé primaire `varchar(255)` du cache (1 020 octets), unicité de `django_content_type` (800 octets). En `COMPACT` ou `REDUNDANT` (767 octets) ou avec des pages de 4 Kio (768 octets), `migrate` échoue dès le premier déploiement (erreur 1709, constaté en essai local), puis `createcachetable`. ÉCHEC : **bloquant** ; demander à o2switch le format `DYNAMIC` par défaut, ou `ALTER TABLE … ROW_FORMAT=DYNAMIC` sur les tables existantes (base sans donnée réelle en L1) |

## 3. Contrôles manuels

| N° | Contrôle | Comment | Attendu | Obtenu | Conséquence / décision selon le résultat |
|---|---|---|---|---|---|
| M01 | Fréquence minimale du cron | cPanel › Tâches Cron, puis test empirique (§4.1) | Chaque minute (souhaité) ; toutes les 5 min acceptable | _à remplir_ | Fixe l'intervalle de `run_jobs` dans `deploy/cron.sh` (L1.2) et `--max-seconds` (inférieur à l'intervalle). Au-delà d'une minute : la réinitialisation du mot de passe attend le passage suivant du cron, et l'écran le dit (R5) |
| M02 | Emplacement du bloc Passenger | V24, puis lecture des `.htaccess` après création de l'application et après un `deploy.sh` (§4.2) | Bloc CloudLinux intact, bloc GEST-CONF ajouté sans le toucher, `/api/` non intercepté | _à remplir_ | Bloc dans `public_html/api/.htaccess` : rien à faire (`deploy.sh` n'y touche pas). Si cPanel réécrit le `.htaccess` racine à chaque modification de l'application : relancer `deploy.sh` (fusion idempotente) |
| M03 | Limite d'upload | `curl` depuis le poste local, corps de 10, 50 et 100 Mo (§4.3) | 405 jusqu'à la taille voulue | _à remplir_ (taille maximale acceptée) | Taille maximale des dépôts (L3 : article complet ou résumé, Q15) ; si elle est trop basse, demander à o2switch ou limiter les fichiers |
| M04 | Nombre de mandataires (`GESTCONF_TRUSTED_PROXY_COUNT`) | Endpoint de diagnostic, activé temporairement (§4.4) | Valeur mesurée (0, 1 ou plus) | _à remplir_ | **Production bloquée sans cette mesure (R3)** : sinon compteur de débit commun à tous et IP fausses dans l'audit. Valeur reportée dans le `.env` ; branchement d'`ALLAUTH_TRUSTED_PROXY_COUNT` sur la même variable en L1.3 |
| M05 | `SCRIPT_NAME`, `PATH_INFO` et HTTPS vus par Django | Même réponse que M04, et champ `secure` de `/api/v1/health` (§4.4) | `secure: true` en HTTPS ; `script_name` `/api` ou vide (les deux sont gérés par `config/mount.py`) | _à remplir_ | `secure: false` en HTTPS : laisser `DJANGO_SECURE_SSL_REDIRECT=false` (défaut) et garder `DJANGO_CSRF_TRUSTED_ORIGINS` |
| M06 | Sauvegardes cPanel | cPanel (outil de sauvegarde proposé), puis restauration d'essai (§4.5) | Sauvegarde quotidienne des fichiers et de la base, rétention connue, restauration réussie | _à remplir_ | D18 : **aucune donnée réelle** avant une sauvegarde et une restauration testées. Copie hors hébergement à organiser (CLAUDE.md) |
| M07 | Ressources du compte (CloudLinux) | cPanel › Utilisation des ressources (§4.6) | Limites relevées : CPU, mémoire, processus d'entrée (EP), NPROC, E/S | _à remplir_ | Nombre de processus Passenger, `--max-seconds` de `run_jobs`, coût de PBKDF2 au pic de connexions (R14) |
| M08 | Recette (sous-domaine ou second dossier) | cPanel › Domaines, et possibilité d'une seconde application Python (§4.7) | Possible | _à remplir_ | D18 : recette marquée `noindex`, sans donnée réelle. Impossible : recette sur un poste local seulement |
| M09 | Désactivation du diagnostic | Après M04 et M05 (§4.4, dernière étape) | `/api/v1/diagnostics/request` → 404 | _à remplir_ | Tant qu'il est actif, l'endpoint expose les en-têtes réseau de la requête : ne pas l'oublier. Contrôlé aussi à chaque déploiement par `deploy/smoke-test.sh` (« diagnostic désactivé ») : un oubli fait échouer le test de fumée |
| M10 | Tests de fumée après le déploiement de L1.1 | `deploy/smoke-test.sh https://<domaine> <commit>` (§4.8) | Tous les contrôles OK | _à remplir_ | Critère de fin de L1.1 (CSP en `<meta>` détectée, cache OK, `X-Robots-Tag`, `robots.txt`). ÉCHEC : voir le libellé du contrôle et `deploy/README.md` |

## 4. Procédures des contrôles manuels

### 4.1 M01 : fréquence minimale du cron

1. cPanel › Tâches Cron : noter les intervalles proposés et un éventuel message sur la fréquence
   minimale.
2. Test empirique : ajouter la tâche `* * * * * date -u '+\%Y-\%m-\%dT\%H:\%M:\%SZ' >> $HOME/cron-probe.log`
   (les `%` doivent être échappés dans une crontab), attendre 10 minutes, puis lire `~/cron-probe.log`.
   L'écart entre deux lignes donne la fréquence réelle.
3. **Supprimer la tâche et le fichier `~/cron-probe.log`.**

### 4.2 M02 : bloc Passenger

1. Après création de l'application dans « Setup Python App » : lancer le script (V24) et noter le
   fichier et les lignes du bloc `# DO NOT REMOVE. CLOUDLINUX PASSENGER CONFIGURATION BEGIN`.
2. Après un `deploy/deploy.sh` : relancer le script. Le bloc GEST-CONF doit apparaître, et le bloc
   CloudLinux doit être inchangé. Le test de fumée « API : URL inconnue -> 404 JSON » prouve que
   le repli SPA n'intercepte pas `/api/`.
3. Modifier un réglage anodin de l'application dans cPanel (par exemple la redémarrer), puis
   relancer le script : le bloc GEST-CONF a-t-il survécu ?

### 4.3 M03 : limite d'upload

Depuis le poste local (aucune donnée n'est enregistrée : `/api/v1/health` refuse le POST par un 405,
après qu'Apache et Passenger ont accepté le corps de la requête) :

```bash
for size in 10 50 100; do
  head -c "${size}M" /dev/urandom > "/tmp/upload-$size"
  printf '%s Mo : ' "$size"
  curl -s -o /dev/null -w '%{http_code} en %{time_total} s\n' -X POST \
    -H 'Content-Type: application/octet-stream' --data-binary "@/tmp/upload-$size" \
    https://<domaine>/api/v1/health
  rm -f "/tmp/upload-$size"
done
```

- **405** : corps accepté par Apache et Passenger (Django refuse ensuite la méthode).
- **413** : corps refusé avant Django (`LimitRequestBody` ou équivalent).
- Autre code (403, 406, 503…) : pare-feu applicatif ou mandataire ; noter le code.

### 4.4 M04, M05 et M09 : IP du client, montage et HTTPS

L'endpoint `GET /api/v1/diagnostics/request` (livré en L1.1) renvoie uniquement `remote_addr`,
`x_forwarded_for`, `x_real_ip`, `is_secure`, `script_name`, `path_info` et `client_ip`. Il répond
404 tant que `GESTCONF_DIAGNOSTICS` n'est pas activé.

1. Ajouter `GESTCONF_DIAGNOSTICS=1` dans `~/gestconf-app/.env`, puis `touch ~/gestconf-app/tmp/restart.txt`.
2. Noter l'adresse IP publique du poste local (celle qu'affiche la box ou le service réseau de
   l'établissement).
3. Depuis le poste local :
   ```bash
   curl -s https://<domaine>/api/v1/diagnostics/request
   curl -s -H 'X-Forwarded-For: 203.0.113.7' https://<domaine>/api/v1/diagnostics/request
   ```
4. Interpréter (`client_ip` est calculée avec la valeur actuelle, 0 par défaut) :

   | Observation | Valeur de `GESTCONF_TRUSTED_PROXY_COUNT` |
   |---|---|
   | `remote_addr` = IP du poste, `x_forwarded_for` vide | **0** (défaut, rien à changer) |
   | `remote_addr` = adresse du mandataire (privée ou locale), dernier élément de `x_forwarded_for` = IP du poste, y compris dans la 2e requête (où l'élément forgé `203.0.113.7` reste à gauche) | **1** |
   | L'IP du poste est l'avant-dernier élément, et le dernier est une adresse d'infrastructure | **2** (un mandataire de plus) |
   | `remote_addr` = adresse du mandataire et aucun en-tête ne contient l'IP du poste | Mesure impossible : **R3 ouvert, production bloquée**, interroger o2switch |
   | Dans la 2e requête, `remote_addr` ou `client_ip` vaut `203.0.113.7` (la valeur forgée) | L'hébergement fait confiance à un en-tête que le client peut forger (`mod_remoteip` ou mandataire mal réglé) : l'IP est usurpable **quelle que soit la valeur retenue**, même 0. **R3 ouvert, production bloquée**, interroger o2switch |

   **Condition commune à toutes les lignes** : quelle que soit la valeur retenue, `remote_addr` et
   `client_ip` de la **2e requête** (celle qui porte l'en-tête forgé) ne valent jamais `203.0.113.7`,
   et `client_ip` y vaut l'IP du poste. Conclure à 0 exige donc aussi d'examiner la 2e requête :
   `client_ip()` et DRF renvoient `REMOTE_ADDR` tel quel quand la valeur est 0, et ne protègent
   pas contre un `REMOTE_ADDR` déjà réécrit en amont de Django.

5. Reporter la valeur dans le `.env`, redémarrer, puis vérifier que `client_ip` vaut l'IP du poste
   **dans les deux requêtes** (la valeur forgée ne doit jamais être retenue).
6. M05 : noter `script_name`, `path_info` et `is_secure` (requête en HTTPS) ; recouper avec le champ
   `secure` de `curl -s https://<domaine>/api/v1/health`.
7. **M09 : retirer `GESTCONF_DIAGNOSTICS` du `.env`**, `touch ~/gestconf-app/tmp/restart.txt`, puis
   vérifier que `curl -s -o /dev/null -w '%{http_code}\n' https://<domaine>/api/v1/diagnostics/request`
   renvoie **404**.

### 4.5 M06 : sauvegardes cPanel

1. Identifier l'outil de sauvegarde proposé par cPanel (nom, fréquence, rétention, bases de données
   incluses ou non). Ces points ne sont **pas vérifiés** à ce jour.
2. Restauration d'essai : restaurer un fichier de test dans un dossier temporaire, puis une base de
   test (par exemple une copie de la base vers une base `…_restore_test`). Supprimer ensuite les
   éléments restaurés.
3. Si V18 est OK, tester aussi `mariadb-dump` (ou `mysqldump`) vers un fichier hors de
   `public_html`, en passant les identifiants par un fichier d'options en droits 600 et jamais sur
   la ligne de commande ; supprimer le fichier ensuite.

### 4.6 M07 : ressources du compte

cPanel › Utilisation des ressources (CloudLinux) : relever les limites (CPU, mémoire physique,
processus d'entrée, nombre de processus, E/S) et les éventuels dépassements récents.

### 4.7 M08 : recette

cPanel › Domaines : un sous-domaine peut-il être créé ? « Setup Python App » accepte-t-il une
seconde application (autre racine, autre URL) ? Noter les limites.

### 4.8 M10 : tests de fumée

```bash
deploy/smoke-test.sh https://<domaine> "$(git rev-parse --short HEAD)"
```

Les trois autres critères de fin de L1.1 (401 JSON pour une requête anonyme, 403 `csrf_failed`
pour un POST connecté sans jeton, 429 sur MariaDB) sont vérifiés par les tests pytest, exécutés
sur MariaDB en CI : aucun endpoint protégé n'est déployé avant L1.3.

## 5. Décisions à consigner

Préfixe **H** (hébergement), distinct des décisions D1 à D18 du plan L1 : H-8, par exemple, n'a
rien à voir avec D8.

| N° | Décision | Dépend de | Valeur retenue | Validée par, date |
|---|---|---|---|---|
| H-1 | Image MariaDB de la CI alignée sur la version d'o2switch | V06 | _à remplir_ | _à remplir_ |
| H-2 | Version de Python de l'application cPanel (3.12 ou 3.13) | V01, V22 | _à remplir_ | _à remplir_ |
| H-3 | 2FA par `allauth.mfa` confirmée, ou repli `django-otp` (R1) | V02, V03 | _à remplir_ | _à remplir_ |
| H-4 | Mode strict confirmé à la connexion (R19) | V09, V25 | _à remplir_ | _à remplir_ |
| H-5 | Verrou des commandes cron : `flock`, `GET_LOCK` ou réservation seule (R6) | V12, V15 | _à remplir_ | _à remplir_ |
| H-6 | Intervalle du cron de `run_jobs` et `--max-seconds` (R5) | M01 | _à remplir_ | _à remplir_ |
| H-7 | Fournisseur d'e-mails joignable (D10) | V19, V20 | _à remplir_ | _à remplir_ |
| H-8 | `GESTCONF_TRUSTED_PROXY_COUNT` (R3, bloquant pour la production) | M04 | _à remplir_ | _à remplir_ |
| H-9 | Sauvegarde et restauration testées avant toute donnée réelle (D18) | M06, V18 | _à remplir_ | _à remplir_ |
| H-10 | Taille maximale des dépôts | M03 | _à remplir_ | _à remplir_ |
| H-11 | Recette : sous-domaine, second dossier ou poste local | M08 | _à remplir_ | _à remplir_ |

## 6. Hors de L1.0

- SSH depuis les runners GitHub et restriction de commande dans `authorized_keys` : avant l'étape
  qui accueillera le déploiement continu (D18).
- Antivirus des fichiers déposés : L3 (soumissions).
- Délivrabilité réelle des e-mails (SPF, DKIM, DMARC) : jalon J-tech de L1.2.
