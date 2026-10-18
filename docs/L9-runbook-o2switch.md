# Runbook o2switch — premier déploiement réel (lot L9, étape L9.8)

> **Statut** : runbook de l'opérateur du commanditaire (plan L9, décisions S1 et S12), rédigé le
> 12 octobre 2026 à partir du code du dépôt. **Aucune de ces étapes n'a encore été jouée sur
> o2switch** ; cette session de développement n'a pas accès à l'hébergement, et ne doit pas
> l'avoir : les clés SSH et les secrets de production restent chez le commanditaire.
>
> Documents liés : guide d'exploitation [`exploitation.md`](exploitation.md) (référence des
> commandes et des incidents), [`deploy/README.md`](../deploy/README.md), fiche
> [`L1-verifications-o2switch.md`](L1-verifications-o2switch.md), test de charge
> [`loadtest/README.md`](../loadtest/README.md), revue de sécurité
> [`L9-revue-securite.md`](L9-revue-securite.md), cahier de recette
> [`L9-cahier-de-recette.md`](L9-cahier-de-recette.md), check-list
> [`L9-mise-en-production.md`](L9-mise-en-production.md).

## Principes

- **Un échec arrête la suite.** On ne passe à l'étape suivante que si son critère de passage
  est rempli. Sinon : appliquer « En cas d'échec », corriger, rejouer l'étape entière.
- **Aucune donnée réelle avant l'étape 12** (D18) : ni compte d'une personne réelle, ni
  invitation réelle, ni édition réelle. Les commandes de données fictives (`seed_volume`,
  `loadtest_sessions`, `seed_demo`) refusent d'ailleurs une base qui contient un compte hors
  du domaine `@fictif.invalid` : un seul compte réel créé trop tôt bloque les étapes 7 et 9.
- **Aucun secret dans un relevé.** Les scripts n'en affichent pas, mais relire chaque sortie
  avant de la transmettre. Les mots de passe et secrets TOTP affichés par `seed_volume` et
  `seed_demo` (comptes fictifs) ne se recopient nulle part.
- **Relevés hors du dépôt** : dans `~/gestconf-releves/` sur le poste de l'opérateur.
  `deploy/deploy.sh` refuse un arbre de travail modifié, **fichiers non suivis compris** : un
  `check-o2switch.txt` ou un dossier `loadtest/resultats/` laissé dans le clone bloquerait le
  déploiement suivant.
- **Où reporter** :
  - « Fiche » : [`L1-verifications-o2switch.md`](L1-verifications-o2switch.md), colonnes
    « Obtenu » (§2, §3), relevé (§0), décisions H-1 à H-11 (§5) ;
  - « Bilan L9 » : le bilan du lot L9, rédigé à l'étape L9.9 (nom du fichier fixé par
    l'équipe) ; d'ici là, transmettre les relevés à l'équipe, qui les reporte ;
  - « Check-list » : [`L9-mise-en-production.md`](L9-mise-en-production.md), colonne
    « Preuve ».
- **Notations** : `<compte>`, `<serveur>`, `<domaine>` (sans `https://`), `<commit>` (empreinte
  courte du commit déployé), `<date>` (horodatage d'un dump, ex. `20261013T020700Z`). Sur le
  poste, toutes les commandes se lancent **à la racine du clone du dépôt**. « Session
  d'exploitation » = annexe A.

## Pourquoi cet ordre

1. **Prérequis** avant tout : sans base, application cPanel ni `.env`, ni le script de
   vérification ni le déploiement ne peuvent tourner.
2. **Vérifications** avant le déploiement : plusieurs contrôles sont bloquants (Python, glibc
   et roues binaires, version et mode de MariaDB, format de ligne InnoDB) et feraient échouer
   `deploy.sh` à mi-course.
3. **Déploiement** ensuite : il livre `deploy/cron.sh` et `deploy/restore.sh` et écrit
   `VENV_ACTIVATE`, dont dépendent le cron et la restauration ; certains contrôles manuels
   (M02 à M05, M09, M10) exigent l'application en ligne.
4. **Cron** avant la sauvegarde : `backup_db` est une commande du cron, et `jobs: ok`,
   `backup: ok` de `/api/v1/health` ne se constatent qu'avec lui ; 48 heures couvrent deux
   nuits de sauvegarde, de purge et de contrôle.
5. **Restauration testée** avant toute donnée, même fictive (D18) : c'est aussi le seul chemin
   de retour des étapes 7 et 10 (aucune commande de purge, les pièces comptables étant en
   ajout seul, RG-14).
6. **Borne de taille des envois** avant la charge : un envoi géant pourrait remplir le disque
   (R1b) ; on le mesure sur une base vide, avec une sauvegarde éprouvée.
7. **Charge** avant toute donnée réelle (D18), puis retour à l'état antérieur par
   restauration ; elle doit précéder la recette, car `seed_volume` refuse toute base qui
   contient un compte réel (les comptes des testeurs de la recette en sont).
8. **ZAP** dans la même fenêtre annoncée à o2switch que la charge, sur la base propre.
9. **Recette** sur l'édition de démonstration, une fois l'infrastructure éprouvée.
10. **Base propre** : la recette laisse des données fictives et, peut-être, des comptes de
    testeurs ; on revient à la sauvegarde d'avant la recette.
11. **Surveillance externe** sur la plateforme définitive (elle peut être posée dès l'étape 4,
    sondes en pause pendant les étapes 5 à 10, pour ne pas brouiller son historique).
12. **Check-list de mise en production** : elle récapitule les preuves des étapes précédentes
    et les points du commanditaire ; l'ouverture de l'appel se décide sur elle.

## Relevé d'exécution

| Étape | Date | Opérateur | Résultat (passé, échec) | Relevés (fichiers) | Reporté dans |
|---|---|---|---|---|---|
| 1. Prérequis | | | | | Fiche §0 |
| 2. Vérifications | | | | `check-o2switch-1.txt` | Fiche §2, §3, §5 |
| 3. Premier déploiement | | | | `deploy-1.txt`, `smoke-1.txt`, `smoke-2.txt`, `check-o2switch-2.txt` | Fiche |
| 4. Cron, 48 h | | | | | Fiche, bilan L9 |
| 5. Sauvegarde et restauration | | | | `pull-1.txt`, `restauration.txt` | Fiche H-9, bilan L9 |
| 6. Taille des envois (R1b) | | | | `r1b-*.txt` | Bilan L9 |
| 7. Charge | | | | `~/gestconf-charge/` | Bilan L9 |
| 8. ZAP | | | | `~/gestconf-zap/` | Bilan L9 |
| 9. Recette | | | | | Cahier de recette, bilan L9 |
| 10. Base propre | | | | | Fiche H-9, bilan L9 |
| 11. Surveillance externe | | | | | Check-list |
| 12. Mise en production | | | | | Check-list |

## Étape 1 — Prérequis

**1.1 Poste de l'opérateur.**

```bash
git clone <adresse du dépôt> gest-conf && cd gest-conf
git checkout <commit validé par l'équipe>
git status --porcelain                  # aucune ligne
node --version                          # >= 22.22.3 ou >= 24.15
python3 --version && rsync --version | head -n 1 && curl --version | head -n 1 && ssh -V
mkdir -p ~/gestconf-releves && chmod 700 ~/gestconf-releves
(cd backend && python3.12 -m venv .venv && .venv/bin/pip install -r requirements/dev.txt)
```

Attendu : versions conformes ; le venv du dépôt sert à générer les clés (1.5) et à une
restauration locale (5.6).

**1.2 Accès SSH par clé** (cPanel, gestion des clés SSH ; libellé exact non vérifié).

```bash
ssh <compte>@<serveur> 'echo connexion-ok; date; uname -sr'
```

Attendu : `connexion-ok` sans demande de mot de passe ; noter la date et le fuseau du serveur
(heures du cron).

**1.3 Base MariaDB** (cPanel › Bases de données MySQL ; `deploy/README.md`, §1, point 1) :
base et utilisateur, tous les privilèges sur la base. Mot de passe long et **ASCII** (V05 :
PyMySQL refuse un mot de passe non ASCII), caractères spéciaux encodés en `%XX` dans
`DATABASE_URL`. Noter les noms exacts affichés par cPanel (préfixe du compte probable).

**1.4 Application Python** (cPanel › Setup Python App ; `deploy/README.md`, §1, point 2) :
Python 3.12 (ou 3.13), racine `gestconf-app`, URL `<domaine>/api`, fichier
`passenger_wsgi.py`, point d'entrée `application`, variable
`DJANGO_SETTINGS_MODULE=config.settings.prod`. Noter le chemin du script `activate` affiché :
c'est `DEPLOY_VENV_ACTIVATE`. Ne saisir **aucun secret** dans les variables de cPanel (elles
finissent en clair dans un `.htaccess`, V24) : tout va dans le `.env`.

**1.5 Clés**, générées sur le poste :

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"          # DJANGO_SECRET_KEY
backend/.venv/bin/python -c \
  "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# -> GESTCONF_MFA_ENCRYPTION_KEYS ; relancer pour GESTCONF_SIGNING_ENCRYPTION_KEYS (PAdES seulement)
```

Conserver chaque clé **hors de l'hébergement et séparément des sauvegardes** (coffre de mots
de passe du commanditaire) ; jamais dans le dépôt, un ticket ou un e-mail.

**1.6 Fichier `.env`**, à partir de `backend/.env.example` :

```bash
(umask 077 && cp backend/.env.example ~/gestconf-prod.env)
# éditer ~/gestconf-prod.env (valeurs ci-dessous), puis :
scp ~/gestconf-prod.env <compte>@<serveur>:gestconf-app/.env
ssh <compte>@<serveur> 'chmod 600 ~/gestconf-app/.env && ls -l ~/gestconf-app/.env'
rm ~/gestconf-prod.env
```

Valeurs : `DJANGO_SECRET_KEY` ; `DATABASE_URL` ; `DJANGO_ALLOWED_HOSTS=<domaine>` ;
`DJANGO_CSRF_TRUSTED_ORIGINS=https://<domaine>` ; `GESTCONF_PUBLIC_URL=https://<domaine>` ;
`GESTCONF_EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL` et la clé du fournisseur (D10, compte ouvert
par le commanditaire), ou les réglages `EMAIL_*` du SMTP de l'hébergement (T2, étude §27 :
boîte cPanel, port 465 et `EMAIL_USE_SSL=true`) ; `GESTCONF_MFA_ENCRYPTION_KEYS` ; `GESTCONF_OPERATORS` (adresses de
l'opérateur) ; `GESTCONF_CRON_INTERVAL_SECONDS=300` (ajusté à l'étape 2) ;
`GESTCONF_TRUSTED_PROXY_COUNT=0` (mesuré à l'étape 3). **Laisser absents** :
`GESTCONF_DIAGNOSTICS`, `GESTCONF_RETENTION_ENFORCED`, `GESTCONF_ALLOW_FAKE_PAYMENTS` ;
`GESTCONF_PAYMENT_PROVIDER` vide (paiement manuel) jusqu'à l'étape 9.

Attendu : `-rw-------` sur `~/gestconf-app/.env`.

**1.7 HTTPS** : cPanel › Domaines, certificat AutoSSL valide et « Forcer la redirection
HTTPS » (`deploy/README.md`, §1, point 4).

```bash
curl -sSI https://<domaine>/ | head -n 1            # réponse sans erreur de certificat
curl -sI http://<domaine>/ | grep -i '^location'    # https://<domaine>/…
```

**1.8 Prévenir o2switch** (support) du test de charge (étape 7) et de l'analyse ZAP (étape 8) :
dates, adresse IP du poste, nature (200 utilisateurs simulés, analyse passive). Question 5 du
plan L9 : sans cela, le pare-feu peut bloquer l'adresse.

**Critère de passage** : 1.1 à 1.8 faits ; `.env` en 0600 ; clés conservées hors hébergement.
**À reporter** : fiche §0 (date, compte et serveur, commit, opérateur) ; référence du ticket
o2switch dans le bilan L9. **En cas d'échec** : accès SSH ou application Python impossibles :
interroger o2switch ; rien d'autre n'est possible sans eux.

## Étape 2 — Vérifications de l'hébergement (avant déploiement)

**2.1 Script en lecture seule** (fiche §1) :

```bash
ssh <compte>@<serveur> 'bash -s' < deploy/check-o2switch.sh \
  | tee ~/gestconf-releves/check-o2switch-1.txt
echo "code ${PIPESTATUS[0]}"
```

Attendu : récapitulatif final trié V00 à V29 ; **aucun `ÉCHEC`** sur les contrôles bloquants
ou structurants : V01, V02, V03, V05, V06, V09, V10, V11, V18, V21, V27, V28 ; V12 **ou** V15
OK (verrou) ; V19 **ou** V20 OK, selon le fournisseur retenu (ni l'un ni l'autre avec le SMTP de
l'hébergement, T2) ; V23 OK. V29 en échec n'est pas
bloquant pour le déploiement (paiement manuel seul) mais l'est pour le paiement en ligne.
V04, V22, V24 et V25 dépendent du code déployé : leur état définitif se relève à l'étape 3.

**2.2 Contrôles manuels possibles avant déploiement** (procédures de la fiche, §4) :

- **M01** fréquence minimale du cron (§4.1 : tâche sonde de 10 minutes, puis la supprimer) ;
- **M06** sauvegardes proposées par cPanel (§4.5) ;
- **M07** ressources du compte CloudLinux (§4.6) : CPU, mémoire, EP, NPROC, E/S ;
- **M08** recette (§4.7) **et seconde base** : créer dans cPanel une base vide
  `<compte>_gcrestau` (nom indicatif), y rattacher l'utilisateur ; noter si l'offre le
  permet. Elle sert aux étapes 5, 7 et 10. Possibilité non vérifiée à ce jour (plan L9 §9).
- **Complément de V18** (absent du script) : la restauration sur l'hébergement charge le dump
  avec le client `mariadb` (ou `mysql`) :

  ```bash
  ssh <compte>@<serveur> 'command -v mariadb || command -v mysql; \
    command -v mariadb-dump || command -v mysqldump'
  ```

  Noter les chemins : si l'un d'eux est hors de `/usr/bin` et `/bin`, le `PATH` réduit du cron
  pourrait ne pas le trouver (vérifié de fait par la première sauvegarde nocturne, étape 4).

**2.3 Décisions** (fiche §5) à proposer à l'équipe et au commanditaire : H-1 (V06 ; l'équipe
aligne l'image MariaDB de la CI), H-2 (V01, V22), H-3 (V02, V03), H-5 (V12, V15 ; reporter
dans `GESTCONF_COMMAND_LOCK` si `database`), H-6 (M01 ; reporter l'intervalle dans
`GESTCONF_CRON_INTERVAL_SECONDS`), H-7 (V19, V20), H-11 (M08). H-4, H-8, H-10 : étape 3 ;
H-9 : étape 5.

**Critère de passage** : fiche remplie pour V00 à V29 (premier passage), M01, M06, M07, M08 ;
aucun échec bloquant ; décisions H-1 à H-3, H-5 à H-7 et H-11 proposées.
**À reporter** : fiche §2 (« Obtenu », recopié du récapitulatif), §3, §5.
**En cas d'échec** : colonne « Conséquence / décision » de la fiche. V01, V02/V03, V06, V27
sont **bloquants** : arrêt, escalade à l'équipe et au commanditaire (repli possible : VPS,
étude §14.4). V18 absent : `backup_db` impossible, arrêt (la sauvegarde conditionne D18).

## Étape 3 — Premier déploiement et contrôles après déploiement

**3.1 Déploiement**, base vide, **sans publication du portail** (aucune édition courante :
`/api/v1/public/portal/site` répondrait 404 et le script s'arrêterait) et sans tests de fumée
intégrés (ils échoueraient sur `jobs` avant le premier passage de `run_jobs`) :

```bash
export DEPLOY_SSH=<compte>@<serveur>
export DEPLOY_VENV_ACTIVATE=<chemin relevé en 1.4 et V22>
unset DEPLOY_BASE_URL GESTCONF_PRERENDER_API_ORIGIN
SKIP_PORTAL=1 deploy/deploy.sh 2>&1 | tee ~/gestconf-releves/deploy-1.txt
echo "code ${PIPESTATUS[0]}"
```

Attendu : `code 0` ; dans la sortie, `backup_db : base vide, rien à sauvegarder.`, les
migrations appliquées, `SKIP_PORTAL=1 : portail rendu dans le navigateur…`, puis
`==> Déploiement <commit> terminé`.

**3.2 Premier passage de `run_jobs`** (vérifie aussi `VENV_ACTIVATE` et `cron.sh`) :

```bash
ssh <compte>@<serveur> '~/gestconf-app/deploy/cron.sh run_jobs --max-seconds 240; \
  echo "code $?"; tail -n 3 ~/gestconf-app/logs/cron-run_jobs.log'
```

Attendu : `code 0`, dernière ligne `… run_jobs : code de sortie 0`.

**3.3 Tests de fumée** :

```bash
deploy/smoke-test.sh https://<domaine> "$(git rev-parse --short HEAD)" \
  | tee ~/gestconf-releves/smoke-1.txt
```

Attendu : `Tous les tests de fumée sont passés.` ; seules lignes `INFO` admises : portail
rendu dans le navigateur, aucune sauvegarde encore.

**3.4 Second passage du script de vérification** (même commande qu'en 2.1, sortie
`check-o2switch-2.txt`). Attendu : V04, V22, V24 OK ; V25 OK (`mysql.W002` absent).

**3.5 M02** (fiche §4.2, points 2 et 3) : bloc CloudLinux intact, bloc GEST-CONF présent ;
redémarrer l'application dans cPanel, relancer le script : le bloc GEST-CONF a survécu.

**3.6 M03** (fiche §4.3, envois de 10, 50 et 100 Mo sur `/api/v1/health`). Depuis la revue de
sécurité (R1), Django refuse lui-même un corps de plus de 55 Mio : attendu **405** pour 10 et
50 Mo, **413** pour 100 Mo. Pour savoir qui répond 413, garder le corps de la réponse :

```bash
head -c 100M /dev/urandom > /tmp/upload-100
curl -s -o ~/gestconf-releves/m03-100.txt -w '%{http_code}\n' -X POST \
  -H 'Content-Type: application/octet-stream' --data-binary @/tmp/upload-100 \
  https://<domaine>/api/v1/health
rm -f /tmp/upload-100; head -c 300 ~/gestconf-releves/m03-100.txt; echo
```

JSON `{"code":"bad_request",…}` : refus par Django (Apache et Passenger ont accepté le corps) ;
page HTML : refus en amont (Apache). Autre code : pare-feu ou mandataire, à noter.

**3.7 M04, M05, M09** (fiche §4.4) : `GESTCONF_DIAGNOSTICS=1` dans le `.env`, redémarrer,
mesurer, reporter `GESTCONF_TRUSTED_PROXY_COUNT`, **retirer** `GESTCONF_DIAGNOSTICS`,
redémarrer, vérifier le 404. Redémarrage : `ssh <compte>@<serveur> 'touch
~/gestconf-app/tmp/restart.txt'`.

**3.8 M10** : relancer 3.3 (sortie `smoke-2.txt`) ; tout doit passer, dont « diagnostic
désactivé ».

**3.9 Journal de Passenger** : relever où s'écrivent les erreurs de Django (dossier de
l'application, journaux d'erreurs de cPanel ; non vérifié) ; le consigner dans le bilan L9
pour compléter `exploitation.md`, §8.5.

**Critère de passage** : déploiement en code 0 ; `run_jobs` en code 0 ; tests de fumée
entièrement passés en 3.3 et 3.8 ; V04, V22, V24, V25 OK ; M02, M03, M04, M05, M09, M10
relevés ; `GESTCONF_TRUSTED_PROXY_COUNT` mesuré ; `GESTCONF_DIAGNOSTICS` absent.
**À reporter** : fiche V04, V22, V24, V25 (après), M02 à M05, M09, M10 ; décisions H-4 (V09,
V25), H-8 (M04), H-10 (M03 ; taille maximale des dépôts, liée à Q15).
**En cas d'échec** : déploiement interrompu : `deploy/README.md`, « Échec en cours de
déploiement » (pas de retour arrière automatique ; corriger et relancer). Causes connues :
`pip` (V04), variable manquante (`check --deploy`), `mysql.W002` (V09), erreur 1709 à
`migrate` (V27), tables du cache (`cache: error`). Test de fumée en échec : son libellé,
puis `deploy/README.md`, §3. M04 impossible ou adresse forgée retenue : **R3 ouvert,
production bloquée** (fiche §4.4), interroger o2switch.

## Étape 4 — Crontab et surveillance de 48 heures

**4.1 Crontab** (cPanel › Tâches Cron) : les onze lignes de l'en-tête de `deploy/cron.sh`
(recopiées dans `exploitation.md`, §6), sans les modifier, sauf la ligne de `run_jobs` selon
H-6 (intervalle relevé par M01, `--max-seconds` inférieur à l'intervalle, et
`GESTCONF_CRON_INTERVAL_SECONDS` égal à l'intervalle dans le `.env`, puis redémarrage). Les
heures sont celles du serveur (1.2). Renseigner l'adresse e-mail des tâches cron de cPanel
(erreurs de `cron.sh` lui-même). Si `$HOME` n'est pas développé, écrire
`/home/<compte>/gestconf-app/deploy/cron.sh`.

**4.2 Premier contrôle** (15 minutes après) :

```bash
curl -s https://<domaine>/api/v1/health; echo
ssh <compte>@<serveur> 'tail -n 1 ~/gestconf-app/logs/cron-*.log'
```

Attendu : `"jobs":"ok"` ; `cron-run_jobs.log` se termine par `code de sortie 0` ; les
commandes horaires apparaissent après leur minute.

**4.3 Canal d'alerte et jalon J-tech** (session d'exploitation) :

```bash
python manage.py sendtestemail --admins
python manage.py send_test_email <adresse de l'opérateur>
# après le passage suivant de run_jobs :
python manage.py outbox --limit 5
```

Attendu : l'alerte de test arrive à chaque adresse de `GESTCONF_OPERATORS` ; l'e-mail de test
arrive, `outbox` le montre `sent`. Relever dans les en-têtes reçus le résultat SPF, DKIM et
DMARC. Leur validité (`pass`) dépend des DNS du commanditaire : si elle manque, l'étape passe
quand même (l'acheminement fonctionne), et le point reste **ouvert** dans la check-list.

**4.4 Surveillance de 48 heures** : deux contrôles par jour, dont un le matin (après 2 h 07,
3 h 17 et 3 h 47, heures du serveur) :

```bash
curl -s https://<domaine>/api/v1/health; echo
ssh <compte>@<serveur> 'grep -h "code de sortie" ~/gestconf-app/logs/cron-*.log \
  | grep -vc "code de sortie 0$"; ls -l ~/gestconf-app/var/backups/ | tail -n 4; \
  tail -n 15 ~/gestconf-app/logs/cron-cleanup.log; \
  tail -n 30 ~/gestconf-app/logs/cron-check_integrity.log'
```

Attendu : `jobs` à `ok` à chaque contrôle ; `backup` à `ok` dès le premier matin ; compteur
de passages en erreur à `0` ; un dump `gestconf-<date>.sql.gz` et son `.json` par nuit ;
`cleanup` affiche les durées D15 en `(simulation)` ; `check_integrity` affiche
`-> 0 anomalie(s)` partout et n'envoie aucune alerte (seule exception admise :
`core.backup_age` si `check_integrity` a tourné avant la toute première sauvegarde).

**Critère de passage** : 48 heures sans passage en erreur ; `jobs: ok` et `backup: ok` ;
alerte de test et e-mail de test reçus.
**À reporter** : fiche M01 (confirmé), H-5, H-6 ; bilan L9 (heures des contrôles, `jobs`,
`backup`, résultat SPF, DKIM, DMARC) ; check-list (« Cron configuré et heartbeat vérifié »).
**En cas d'échec** : `exploitation.md`, §9.2 (cron arrêté), §9.3 (sauvegarde en retard), §9.5
(e-mails). Rejouer les 48 heures après correction.

## Étape 5 — Sauvegarde, copie rapatriée, restauration chronométrée

**5.1 Sauvegarde fraîche** :

```bash
ssh <compte>@<serveur> '~/gestconf-app/deploy/cron.sh backup_db; echo "code $?"; \
  tail -n 3 ~/gestconf-app/logs/cron-backup_db.log; ls -l ~/gestconf-app/var/backups/; \
  stat -c "%a %n" ~/gestconf-app/var/backups'
```

Attendu : `code 0` ; `backup_db : …/gestconf-<date>.sql.gz (<n> octets)` ; fichiers en
`-rw-------` ; dossier en `700`.

**5.2 Copie hors hébergement** (poste de l'opérateur, dossier sur disque chiffré de
préférence). Sur une installation neuve, rien n'a encore été déposé et `var/files` n'existe
pas : `rsync` échouerait sur ce dossier distant absent, d'où sa création préalable (vide,
sans effet sur l'application, qui crée ses sous-dossiers au besoin) :

```bash
ssh <compte>@<serveur> 'mkdir -p ~/gestconf-app/var/files && chmod 700 ~/gestconf-app/var/files'
PULL_SSH=<compte>@<serveur> PULL_DEST=~/gestconf-copies deploy/pull-backups.sh 2>&1 \
  | tee ~/gestconf-releves/pull-1.txt
echo "code ${PIPESTATUS[0]}"
```

Attendu : `code 0`, `gestconf-<date>.sql.gz : empreinte conforme ; <n> fichiers au
manifeste.` puis `Instantané conforme au manifeste.`. Installer ensuite la ligne de crontab du
poste (`exploitation.md`, §7.2) : **entre 2 h 07 et 3 h 17, heures du serveur**, converties
dans le fuseau du poste.

**5.3 Seconde base** : celle créée en 2.2 (M08), vide ; vérifier son interclassement
`utf8mb4_unicode_ci` (phpMyAdmin › Opérations ; V10).

**5.4 Perte simulée** : on restaure **depuis la copie rapatriée**, renvoyée sur l'hébergement,
comme après la perte du serveur. Départ du chronomètre :

```bash
date -u +%FT%TZ | tee ~/gestconf-releves/restauration-debut.txt
D=gestconf-<date>                              # dump de 5.1
ssh <compte>@<serveur> 'mkdir -p ~/gestconf-restau-test && chmod 700 ~/gestconf-restau-test'
rsync -a ~/gestconf-copies/backups/$D.sql.gz ~/gestconf-copies/backups/$D.json \
  <compte>@<serveur>:gestconf-restau-test/
rsync -a ~/gestconf-copies/files/latest/ <compte>@<serveur>:gestconf-restau-test/instantane/
```

**5.5 Restauration dans la seconde base** (annexe B, cas 1 « test, sans repointage ») :

```bash
ssh <compte>@<serveur>
install -m 600 ~/gestconf-app/.env ~/gestconf-restau-test/.env
# éditer ~/gestconf-restau-test/.env (chemins absolus) :
#   DATABASE_URL=mysql://<utilisateur>:<mot de passe>@<hôte>:<port>/<compte>_gcrestau
#   GESTCONF_FILES_DIR=/home/<compte>/gestconf-restau-test/files        (modifier ou ajouter)
#   GESTCONF_PRIVATE_FILES_DIR=… : seulement s'il figure dans le .env (sous-dossier private)
GESTCONF_ENV_FILE=$HOME/gestconf-restau-test/.env ~/gestconf-app/deploy/restore.sh \
  ~/gestconf-restau-test/gestconf-<date>.sql.gz ~/gestconf-restau-test/instantane \
  2>&1 | tee ~/gestconf-restau-test/restauration.txt
```

Attendu : `restore_db : base restaurée depuis gestconf-<date>.sql.gz (…)` ; aucune ligne
`fichier absent`, `taille différente` ni `migrations en attente` ;
`restore_db : fichiers conformes au manifeste.` ; chaque ligne `check_integrity : … -> 0
anomalie(s)` (`core.backup_age` toléré, voir `exploitation.md`, §7.3) ; dernière ligne
`Restauration terminée en <m> min <s> s (objectif : moins de 4 h).`. Durée totale (de 5.4 à
cette ligne) **inférieure à 4 heures**. Rapatrier le relevé :
`scp <compte>@<serveur>:gestconf-restau-test/restauration.txt ~/gestconf-releves/`.

**5.6 Restauration locale (recommandée)** : prouve que la copie suffit sans l'hébergement.
Base locale neuve (`CREATE DATABASE gestconf_restau CHARACTER SET utf8mb4 COLLATE
utf8mb4_unicode_ci;`), dossier vide :

```bash
DATABASE_URL=mysql://<u>:<p>@127.0.0.1:3306/gestconf_restau \
GESTCONF_FILES_DIR=$HOME/gestconf-restau-local/files \
  deploy/restore.sh ~/gestconf-copies/backups/gestconf-<date>.sql.gz ~/gestconf-copies/files/latest
```

Mêmes critères qu'en 5.5. Supprimer ensuite la base et le dossier locaux.

**5.7 Nettoyage** : `ssh <compte>@<serveur> 'rm -rf ~/gestconf-restau-test'` (il contient une
copie du `.env`) ; vider la seconde base (cPanel : la supprimer puis la recréer vide) pour
l'étape 7.

**Critère de passage** : sauvegarde, copie vérifiée, restauration conforme en moins de
4 heures ; dossier de test supprimé.
**À reporter** : fiche M06 (point 3 : `mariadb-dump` éprouvé par `backup_db`), M08 (seconde
base possible ou non), H-9 (date, dump, durées, résultat) ; bilan L9 (test de restauration
documenté, étude §11.6 : date, dump, taille, durée du transfert, durée de `restore.sh`,
résultat) ; check-list (« Sauvegarde automatique et restauration testée »).
**En cas d'échec** : empreinte refusée : refaire 5.2. `n'est pas vide` : base ou dossier non
neufs. Chargement en échec : lire le message (client `mariadb` trop ancien pour la première
ligne `enable the sandbox mode` d'un dump récent, plan L9 §11). Seconde base refusée par
l'offre : faire 5.6 seulement, le consigner (M08, H-9), et faire valider par l'équipe et le
commanditaire que les retours des étapes 7 et 10 passeront par une base réinstallée (variante
de l'annexe B) ; sinon arrêt.

## Étape 6 — Borne de taille des envois (R1b)

La revue de sécurité (R1b) laisse ouvert un point : Passenger peut mettre un envoi en tampon
avant Django. On vérifie qu'un envoi de 100 Mo sur une route de dépôt est refusé (413) sans
consommer durablement d'espace disque.

```bash
head -c 100M /dev/urandom > /tmp/envoi-100M.bin     # Linux ; macOS : dd … bs=1m count=100
ssh <compte>@<serveur> 'df -Pk ~ /tmp; du -sk ~/gestconf-app/var ~/gestconf-app/tmp' \
  | tee ~/gestconf-releves/r1b-avant.txt
# terminal 2, pendant l'envoi (pic éventuel) :
#   ssh <compte>@<serveur> 'for i in $(seq 1 40); do df -Pk ~ /tmp | tail -n +2; sleep 1; done'
curl -s -o ~/gestconf-releves/r1b-reponse.txt -w '%{http_code} en %{time_total} s\n' \
  -X POST -H 'Content-Type: application/octet-stream' --data-binary @/tmp/envoi-100M.bin \
  https://<domaine>/api/v1/submissions/1/file | tee ~/gestconf-releves/r1b-code.txt
ssh <compte>@<serveur> 'df -Pk ~ /tmp; du -sk ~/gestconf-app/var ~/gestconf-app/tmp' \
  | tee ~/gestconf-releves/r1b-apres.txt
rm -f /tmp/envoi-100M.bin
```

Attendu : **413** ; corps JSON `{"code":"bad_request","message":"Requête trop volumineuse.",…}`
(Django) ou page 413 d'Apache ; espace libre et tailles de `var/` et `tmp/` identiques avant
et après, à quelques Mio près (activité normale) ; pic éventuel du terminal 2 noté.

Complément facultatif, sans critère (comportement de Passenger non vérifié) : même envoi en
`-H 'Transfer-Encoding: chunked'`, sans longueur annoncée ; noter le code et l'espace.

**Critère de passage** : 413 et espace disque inchangé.
**À reporter** : bilan L9 (code, temps, pic, espace avant et après) ; statut de R1b à mettre à
jour par l'équipe dans `L9-revue-securite.md` ; fiche M03 (complément).
**En cas d'échec** : autre code (2xx, 400, 401, 403, 5xx) ou espace non rendu : R1b confirmé,
arrêt. Interroger o2switch (`PassengerBufferUpload`, `LimitRequestBody`). Ne **pas** ajouter
`LimitRequestBody` au `.htaccess` sans accord d'o2switch : une directive refusée met tout le
portail en erreur 500 (revue, R1b) ; décision à prendre avec l'équipe.

## Étape 7 — Test de charge (avant toute donnée réelle)

Prérequis : o2switch prévenu (1.8) ; étapes 5 et 6 passées ; aucune donnée réelle. Référence :
[`loadtest/README.md`](../loadtest/README.md). Cible (étude §12) : 200 utilisateurs
simultanés, p95 < 500 ms hors PDF, moins de 1 % d'erreurs.

**7.1 Locust sur le poste** (README de la charge, §1) :

```bash
python3.12 -m venv ~/gestconf-loadtest
~/gestconf-loadtest/bin/pip install --require-hashes -r backend/requirements/loadtest.txt
~/gestconf-loadtest/bin/locust --version          # locust 2.46.7
```

**7.2 État d'avant le test** (session d'exploitation) :

```bash
python manage.py backup_db --required
ls -1t ~/gestconf-app/var/backups/gestconf-*.sql.gz | head -n 1     # noter : dump d'avant charge
python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["files"]["count"])' \
  ~/gestconf-app/var/backups/gestconf-<date>.json
```

Si le nombre de fichiers affiché est supérieur à 0, en garder l'état :
`mkdir -p ~/gestconf-avant-charge && cp -a ~/gestconf-app/var/files ~/gestconf-avant-charge/files`.
Lancer aussi `deploy/pull-backups.sh` depuis le poste (copie hors hébergement de ce point de
retour).

**7.3 Données de volume** (une dizaine de minutes en local, 528 s ; durée sur l'hébergement
inconnue) :

```bash
python manage.py seed_volume --confirm-fictitious
```

Attendu : lignes de progression, `seed_volume : terminé en <n> s.`, compteurs, éditions,
comptes du comité ; mot de passe et secret TOTP des comptes fictifs affichés une fois :
les garder pour 7.6 seulement, ne les recopier nulle part.

**7.4 Sessions pré-établies** (valables 12 heures : lancer le test dans la foulée) :

```bash
python manage.py loadtest_sessions --confirm-fictitious --output ~/gestconf-sessions.json
# poste de l'opérateur :
scp <compte>@<serveur>:gestconf-sessions.json ~/gestconf-sessions.json
chmod 600 ~/gestconf-sessions.json
```

Attendu, avec les valeurs par défaut : `committee : 2`, `reviewer : 60`, `author : 100`,
`participant : 150`, `newcomer : 100`, puis `loadtest_sessions : 412 sessions dans …`.

**7.5 Lancement** (poste ; rapports **hors du dépôt**, contrairement à l'exemple du README de
la charge, pour ne pas bloquer `deploy.sh`) :

```bash
mkdir -p ~/gestconf-charge
(cd loadtest && GESTCONF_SESSIONS=~/gestconf-sessions.json ~/gestconf-loadtest/bin/locust \
  --headless --host https://<domaine> \
  --users 200 --spawn-rate 2 --run-time 12m \
  --csv ~/gestconf-charge/charge --html ~/gestconf-charge/charge.html) \
  2>&1 | tee ~/gestconf-charge/locust.txt
echo "code ${PIPESTATUS[0]}"
```

Pendant le palier : cPanel › Utilisation des ressources (M07 : limites atteintes, erreurs
d'EP ou de mémoire) et `curl -s https://<domaine>/api/v1/health` depuis un autre terminal.

Ne **pas** publier le portail de l'édition fictive (`--portal-only`) : ses pages pré-rendues
resteraient en ligne après le retour arrière. Les pages des visiteurs sont de toute façon des
fichiers statiques servis par Apache (portail rendu dans le navigateur depuis l'étape 3).

Attendu : `code 0` et dernière ligne `Verdict : OBJECTIF ATTEINT : …`.

**7.6 Coût du hachage des mots de passe (R14)**, base de volume encore en place, après l'arrêt
de Locust : fenêtre de navigation privée, outils de développement › Réseau,
`https://<domaine>/compte/connexion`, connexion avec `auteur0001@fictif.invalid` et le mot de
passe de 7.3 (les auteurs fictifs n'ont pas de 2FA) ; noter la durée de la requête
`POST …/api/_allauth/browser/v1/auth/login` ; se déconnecter ; recommencer avec `auteur0002`
à `auteur0005`. Noter aussi la durée d'un `GET /api/v1/health` (référence). Le plan ne fixe
pas de seuil : relever les cinq mesures et leur médiane ; l'équipe les rapproche des limites
de M07 et du pic de connexions attendu.

**7.7 Révocation des sessions** :

```bash
python manage.py loadtest_sessions --revoke ~/gestconf-sessions.json && rm ~/gestconf-sessions.json
# poste de l'opérateur :
rm ~/gestconf-sessions.json
```

Attendu : `loadtest_sessions : <n> sessions supprimées.`

**7.8 Retour à l'état d'avant le test** : restaurer le dump de 7.2 dans une base neuve et y
repointer l'application (annexe B, cas 2 « avec repointage »). Les données fictives ne se
purgent pas (pièces comptables en ajout seul, RG-14). Attendu : critères de l'annexe B,
dont `False 0` au contrôle des données fictives.

**Critère de passage** : verdict `OBJECTIF ATTEINT` ; mesures R14 relevées ; sessions
révoquées ; base revenue à l'état d'avant le test, sans donnée fictive.
**À reporter** : bilan L9 (ligne du verdict, tableau des requêtes les plus lentes tiré de
`charge_stats.csv`, colonne `95%`, nombre d'utilisateurs atteint, erreurs de
`charge_failures.csv`, observations de M07, mesures R14, durée de `seed_volume`, durée de la
restauration) ; check-list (« Test de charge exécuté sur l'hébergement réel »).
**En cas d'échec** : **faire quand même 7.7 et 7.8**, puis arrêter. Verdict non atteint :
l'équipe analyse (`charge_stats.csv`, M07) ; repli de l'étude §14.4 (VPS) si les limites du
compte sont en cause. `seed_volume` refusé pour données réelles : un compte réel existe,
trouver lequel avant tout. `seed_volume` interrompu : restaurer le dump de 7.2 (annexe B,
cas 2), puis recommencer.

## Étape 8 — Analyse ZAP passive

Prérequis : o2switch prévenu ; base propre (étape 7). Plan : `deploy/zap/baseline.yaml`
(exploration en GET et analyse passive, aucune écriture). **Jamais** d'analyse active,
d'import OpenAPI (il enverrait des POST, PUT et DELETE), ni de `zap-full-scan.py` ou
`zap-api-scan.py` contre l'hébergement.

```bash
mkdir -p ~/gestconf-zap
GESTCONF_ZAP_TARGET=https://<domaine> GESTCONF_ZAP_REPORTS="$HOME/gestconf-zap" \
  zap.sh -cmd -autorun "$PWD/deploy/zap/baseline.yaml"
# variante Docker, lancée depuis ~/gestconf-zap (hors du dépôt) :
#   cd ~/gestconf-zap && docker run --rm -v "$PWD:/zap/wrk" -t zaproxy/zap-stable \
#     zap-baseline.py -t https://<domaine> -r zap-baseline.html
```

Contrôles de la revue (§7, points 4 et 5), dans la même étape :

```bash
ssh <compte>@<serveur> 'stat -c "%a %n" ~/gestconf-app/.env ~/gestconf-app/var \
  ~/gestconf-app/var/files ~/gestconf-app/var/backups; \
  find ~/public_html -maxdepth 3 -name "*.php"; \
  cd ~/public_html && find . -mindepth 1 -maxdepth 2 -type d \
    ! -exec test -e "{}/index.html" \; -print'
# pour chaque dossier listé en dernier (hors .well-known et cgi-bin) :
curl -s https://<domaine>/<dossier>/ | grep -c 'Index of'          # 0 attendu
```

Attendu : rapports `zap-baseline.html` et `zap-baseline.json` ; **aucune alerte de risque
élevé** ; chaque alerte moyenne ou faible corrigée ou acceptée par écrit ; valeur de l'en-tête
`Server` relevée (R16). `.env` en `600`, `var/backups` en `700` (`var/files` en `700` conseillé,
sinon `chmod 700 ~/gestconf-app/var/files`) ; aucun fichier PHP (ou seulement des fichiers de
cPanel identifiés) ; aucun index de dossier.

La base propre n'a pas d'édition courante : l'exploration du portail est courte. Pour une
couverture plus large, relancer la même analyse pendant l'étape 9, l'édition `DEMO` publiée.

**Critère de passage** : aucune alerte élevée ouverte ; contrôles de la revue conformes.
**À reporter** : bilan L9 (nombre d'alertes par niveau, liste et traitement de chacune,
en-tête `Server`) ; l'équipe met à jour `L9-revue-securite.md` (R16 et constats nouveaux).
**En cas d'échec** : alerte élevée : arrêt, correctif de l'équipe, redéploiement, nouvelle
analyse. Droits trop larges : `chmod`, puis recontrôle. Index de dossier visible : demander à
o2switch si `Options -Indexes` est permis, l'équipe l'ajoutant au bloc GEST-CONF.

## Étape 9 — Recette sur l'édition de démonstration

**9.1 Point de retour** (session d'exploitation) : `python manage.py backup_db --required` ;
noter le nom du dump (**base propre**) ; même contrôle du nombre de fichiers qu'en 7.2 et, s'il
est supérieur à 0, `mkdir -p ~/gestconf-avant-recette && cp -a ~/gestconf-app/var/files
~/gestconf-avant-recette/files` ; lancer `deploy/pull-backups.sh` depuis le poste.

**9.2 Paiement de la démo G**, **avant** `seed_demo` (qui ne propose le paiement en ligne que
si un fournisseur est configuré à son lancement) : soit le bac à sable CinetPay
(`GESTCONF_PAYMENT_PROVIDER=cinetpay`, clés de test, `CINETPAY_SANDBOX=true`), soit le
fournisseur factice déclaré pour la recette (`GESTCONF_PAYMENT_PROVIDER=fake` et
`GESTCONF_ALLOW_FAKE_PAYMENTS=true`) ; redémarrer. Noter le choix : il est défait à
l'étape 10. Sans fournisseur, les scénarios de paiement en ligne sont « sans objet ».

**9.3 Édition de démonstration** :

```bash
python manage.py seed_demo --confirm-fictitious
```

Attendu : `seed_demo : édition DEMO créée, courante sur le portail.`, la liste des comptes
`<nom>@fictif.invalid : <rôle>` (un par rôle), le mot de passe commun et le secret TOTP des
rôles de gestion, affichés une seule fois : les remettre aux testeurs par un canal sûr, ne pas
les recopier dans un document. Aucun e-mail n'atteint ces comptes (domaine réservé).

**9.4 Portail de démonstration** (démo C, programme public) :
`DEPLOY_BASE_URL=https://<domaine> deploy/deploy.sh --portal-only`, depuis le commit déployé.
Ces pages pré-rendues resteront en ligne jusqu'au redéploiement de l'étape 10.

**9.5 Démos A à I** selon [`L9-cahier-de-recette.md`](L9-cahier-de-recette.md) : A (compte),
B (double authentification, paramétrage, invitations), C (portail), D (soumission), E
(évaluation et décision), F (programme), G (inscriptions et paiements), H (jour J, sur
téléphones réels), I (logistique, partenaires, communication, rapports). La recette
fonctionnelle est faite par le commanditaire ; l'opérateur et l'équipe assistent. Une
anomalie = une ligne (gravité, correctif, commit). Un scénario qui crée un compte avec une
adresse réelle (réception d'e-mails) est admis : l'étape 10 l'efface.

**Critère de passage** : chaque scénario du cahier joué ; aucune anomalie bloquante ouverte
(les autres acceptées par écrit par le commanditaire).
**À reporter** : cahier de recette (résultat de chaque scénario, anomalies) ; bilan L9
(synthèse) ; check-list (« Test d'accès : un relecteur… », démo E).
**En cas d'échec** : anomalie bloquante : correctif de l'équipe, redéploiement
(`deploy/deploy.sh`), scénario rejoué. `seed_demo` refusé : données réelles présentes ou
édition `DEMO` existante : revenir à 9.1 par l'annexe B, cas 2.

## Étape 10 — Retour à une base propre

**10.1 Base** : restaurer le dump de 9.1 dans une base neuve et repointer (annexe B, cas 2,
instantané `~/gestconf-avant-recette` s'il existe), fichiers de la recette mis de côté.
Variante, réinstallation : `var/files` mis de côté de même (`mv`), `DATABASE_URL` repointé
vers une base neuve **vide**, redémarrage ; les tables sont créées par le déploiement de 10.3,
lancé alors **sans** `DEPLOY_BASE_URL`, suivi de `~/gestconf-app/deploy/cron.sh run_jobs` et
de `deploy/smoke-test.sh https://<domaine> <commit>`. Entre le repointage et ce déploiement,
les passages du cron échouent (tables absentes) : attendu, sans conséquence.

**10.2 Paiement** : défaire 9.2 dans le `.env` (retirer `GESTCONF_ALLOW_FAKE_PAYMENTS`,
`GESTCONF_PAYMENT_PROVIDER` vide jusqu'aux clés de production), redémarrer.

**10.3 Portail** : retirer les pages de l'édition `DEMO` par un déploiement complet sans
publication (le portail redevient rendu dans le navigateur), après un passage de `run_jobs`
depuis le repointage (sinon le test de fumée `jobs` du script échoue) :

```bash
export DEPLOY_BASE_URL=https://<domaine>
unset GESTCONF_PRERENDER_API_ORIGIN
SKIP_PORTAL=1 deploy/deploy.sh 2>&1 | tee ~/gestconf-releves/deploy-propre.txt
curl -s https://<domaine>/fr/ | grep -c 'data-gc-rendered'          # 0 attendu
```

**10.4 Contrôles** (session d'exploitation) :

```bash
python manage.py shell -c "from apps.conferences.models import Conference; \
from apps.accounts.models import User; \
print(Conference.objects.filter(slug='gestconf-fictif').exists(), \
User.objects.filter(email__iendswith='@fictif.invalid').count())"
python manage.py migrate --check; echo "code $?"
python manage.py check_integrity
~/gestconf-app/deploy/cron.sh backup_db
```

Attendu : `False 0` ; `code 0` ; `-> 0 anomalie(s)` partout ; nouvelle sauvegarde de la base
propre. Les testeurs suppriment les entrées TOTP des comptes `DEMO` de leurs applications.

**10.5 Sauvegardes de la période de test** : les dumps pris après `seed_volume` (7.3) ou après
`seed_demo` (9.3), sauvegardes nocturnes comprises, et leurs copies rapatriées, contiennent
des données fictives et des comptes de testeurs ; ceux de 7.2, 9.1, 10.3 et 10.4 sont propres.
Laisser les premiers à la rotation (au plus trois mois pour une mensuelle) ou les supprimer à
la main ; **jamais** une sauvegarde de la base propre.

**Critère de passage** : contrôles de 10.4 conformes ; portail sans page pré-rendue de démo ;
paiement de recette retiré ; sauvegarde de la base propre faite.
**À reporter** : fiche H-9 (seconde restauration) ; bilan L9 (date, variante, durées) ;
check-list (« Base propre »).
**En cas d'échec** : contrôle à `True` ou compteur non nul : la base n'est pas celle attendue
(mauvais dump ou `.env` non repointé) ; reprendre 10.1.

## Étape 11 — Surveillance externe

Service gratuit de type UptimeRobot ou Better Stack (conditions de l'offre gratuite, usage
commercial compris, et intervalle minimal **non vérifiés**), compte au nom du commanditaire,
alertes vers l'opérateur :

| Sonde | Adresse | Condition | Intervalle |
|---|---|---|---|
| Portail | `https://<domaine>/fr/` | code 200 | 5 min |
| API | `https://<domaine>/api/v1/health` | mot-clé `"status":"ok"` présent (un 503 alerte aussi) | 5 min |
| File de tâches (conseillée) | `https://<domaine>/api/v1/health` | mot-clé `"jobs":"ok"` présent | 5 min |
| Sauvegarde (conseillée) | `https://<domaine>/api/v1/health` | mot-clé `"backup":"ok"` présent | 5 min |

Copier la forme exacte des mots-clés depuis `curl -s https://<domaine>/api/v1/health`. Tester
une alerte (mot-clé volontairement faux quelques minutes, ou fonction de test du service) et
son retour à la normale.

**Critère de passage** : sondes « en service » ; alerte de test et retour reçus.
**À reporter** : check-list (« Supervision et alertes actives » : capture des sondes, date du
test) ; nom du service dans le bilan L9.
**En cas d'échec** : sonde en échec alors que `curl` répond : pare-feu d'o2switch vis-à-vis des
adresses du service, à interroger.

## Étape 12 — Check-list de mise en production

Remplir [`L9-mise-en-production.md`](L9-mise-en-production.md) ligne à ligne, avec les preuves
des étapes 1 à 11 et les points du commanditaire (pages légales, DNS d'envoi, clés de
paiement de production et paiement réel de petit montant, quota d'e-mails, durées de
conservation, notice d'information définitive). La création de la conférence et de l'édition
réelles (`create_conference`, `create_edition --admin-email … --current`), première donnée
réelle, n'intervient qu'à ce stade. **L'ouverture de l'appel est une décision du
commanditaire, prise sur cette check-list.**

## Annexe A — Session d'exploitation

```bash
ssh <compte>@<serveur>
cd ~/gestconf-app
source "$(cat VENV_ACTIVATE)"
export DJANGO_SETTINGS_MODULE=config.settings.prod
```

Sans `DJANGO_SETTINGS_MODULE`, `manage.py` prend les réglages de développement.

## Annexe B — Restaurer dans une base neuve sur l'hébergement

Principe : `restore.sh` lit la configuration de production ; on lui donne une **copie du
`.env`** (0600) dont seules les lignes utiles changent, désignée par `GESTCONF_ENV_FILE`, pour
ne jamais écrire de mot de passe sur une ligne de commande. `restore_db` refuse une base qui
contient des tables et un dossier de fichiers non vide.

**Préparation commune** :

1. cPanel › Bases de données MySQL : base neuve (ou base supprimée puis recréée), utilisateur
   rattaché avec tous les privilèges, interclassement `utf8mb4_unicode_ci` (V10).
2. Nombre de fichiers du manifeste :
   `python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["files"]["count"])' <dump>.json`.
   S'il est supérieur à 0, il faut un instantané : dossier contenant `files/` (copie de
   `var/files`, ou `<PULL_DEST>/files/latest` renvoyé par `rsync`), et `private/` si
   `GESTCONF_PRIVATE_FILES_DIR` est hors de `GESTCONF_FILES_DIR`.

**Cas 1 — test, sans repointage** (étape 5) : copie du `.env` avec `DATABASE_URL` vers la base
neuve et `GESTCONF_FILES_DIR` vers un dossier de test vide (chemins absolus) ; lancer
`GESTCONF_ENV_FILE=<copie> ~/gestconf-app/deploy/restore.sh <dump> [<instantané>]` ; supprimer
ensuite la copie, le dossier de test et la base.

**Cas 2 — retour arrière, avec repointage** (étapes 7, 9 et 10) ; les chemins des fichiers ne
changent pas, seule la base change :

```bash
mv ~/gestconf-app/var/files ~/gestconf-app/var/files-ecartes-<date>   # met de côté
mkdir -m 700 ~/gestconf-app/var/files    # vide : cible de la restauration, et pull-backups.sh
install -m 600 ~/gestconf-app/.env ~/gestconf-restauration.env
# éditer ~/gestconf-restauration.env : DATABASE_URL -> base neuve (seule modification)
GESTCONF_ENV_FILE=$HOME/gestconf-restauration.env ~/gestconf-app/deploy/restore.sh \
  ~/gestconf-app/var/backups/gestconf-<date>.sql.gz [<instantané>]
# si la restauration est conforme : repointage
cp -p ~/gestconf-app/.env ~/gestconf-env-avant-restauration
install -m 600 ~/gestconf-restauration.env ~/gestconf-app/.env
touch ~/gestconf-app/tmp/restart.txt
```

Puis, une fois `run_jobs` repassé (un intervalle de cron) :

```bash
curl -s https://<domaine>/api/v1/health; echo                 # database et cache ok, jobs ok
deploy/smoke-test.sh https://<domaine> <commit>                # depuis le poste
```

Contrôle des données fictives, `python manage.py migrate --check` et `check_integrity` : comme
en 10.4 (attendu `False 0`, `code 0`, `-> 0 anomalie(s)`). Le cron suit sans changement (il
lit le même `.env`) ; `pull-backups.sh` aussi (chemins inchangés).

Nettoyage, une fois la plateforme vérifiée : cPanel, suppression de l'ancienne base ;
`rm -rf ~/gestconf-app/var/files-ecartes-<date> ~/gestconf-avant-charge
~/gestconf-avant-recette ~/gestconf-restauration.env ~/gestconf-env-avant-restauration`.

**Critères** : ceux de 5.5 pour la restauration ; santé `ok`, tests de fumée passés, `False 0`
après repointage. **En cas d'échec avant repointage** : rien n'a changé pour la plateforme
(supprimer la base neuve ; remplacer `var/files` par `var/files-ecartes-<date>`). **Après
repointage** : remettre `~/gestconf-env-avant-restauration` en place
(`install -m 600 … ~/gestconf-app/.env`), redémarrer, puis analyser.
