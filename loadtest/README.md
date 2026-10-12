# Test de charge (plan L9, S5 ; étude §12)

Objectif de l'étude : **200 utilisateurs simultanés, p95 < 500 ms hors exports et PDF, moins de
1 % d'erreurs**. Scénarios : `locustfile.py` (visiteurs, auteurs, relecteurs, participants,
comité) ; la commande se termine par un **verdict** et un code de sortie non nul si l'objectif
n'est pas atteint.

Le test se lance **depuis le poste de l'opérateur, jamais depuis l'hébergement**, sur une base
**sans aucune donnée réelle** (D18), après avoir **prévenu o2switch** (question 5 du plan).

## 1. Installation (poste de l'opérateur, Linux ou macOS)

Environnement séparé, dépendances verrouillées à empreintes (`backend/requirements/loadtest.txt`,
compilé sous Linux et Python 3.12 ; sous Windows, passer par WSL : `pywin32` manquerait au
verrou).

```bash
python3.12 -m venv ~/gestconf-loadtest
~/gestconf-loadtest/bin/pip install --require-hashes -r backend/requirements/loadtest.txt
~/gestconf-loadtest/bin/locust --version          # locust 2.46.7
```

## 2. Préparation (sur l'hébergement, en SSH, dans le dossier de l'application)

```bash
source "$(cat VENV_ACTIVATE)"
export DJANGO_SETTINGS_MODULE=config.settings.prod
python manage.py backup_db --required             # sauvegarde d'AVANT le test (à restaurer après)
python manage.py seed_volume --confirm-fictitious # ~10 min ; note le mot de passe et le secret TOTP affichés
python manage.py loadtest_sessions --confirm-fictitious --output ~/gestconf-sessions.json
```

- `seed_volume` refuse une base qui contient un compte, une soumission ou une inscription
  réels ; aucun e-mail ne part (adresses en `@fictif.invalid`).
- `loadtest_sessions` ouvre une session par compte fictif (2FA validée pour le comité et les
  relecteurs) : le test ne se connecte jamais, sinon les limites de débit de la connexion
  (par adresse IP) l'arrêteraient. Valeurs par défaut : 2 comptes du comité, 60 relecteurs,
  100 auteurs, 150 participants, 100 nouveaux inscrits (`--reviewers 60`, etc.).
- Le fichier contient des **cookies de session** : mode 0600, hors de `public_html`, copié sur
  le poste par `scp`, **jamais versionné**, supprimé après le test.

```bash
scp compte@serveur:gestconf-sessions.json ~/gestconf-sessions.json   # depuis le poste
```

## 3. Lancement (depuis le poste)

Montée progressive puis palier de 10 minutes à 200 utilisateurs :

```bash
cd loadtest
GESTCONF_SESSIONS=~/gestconf-sessions.json ~/gestconf-loadtest/bin/locust \
  --headless --host https://conference.exemple.org \
  --users 200 --spawn-rate 2 --run-time 12m \
  --csv resultats/charge --html resultats/charge.html
```

Variables facultatives :

| Variable | Défaut | Rôle |
|---|---|---|
| `GESTCONF_PAGES` | `/fr/,/en/,/fr/programme,/fr/inscription,/fr/partenaires` | pages pré-rendues des visiteurs (vide : aucune) |
| `GESTCONF_P95_MS` | `500` | cible du p95 en millisecondes |
| `GESTCONF_MAX_FAILURE_RATIO` | `0.01` | taux d'erreurs maximal |

Répartition des utilisateurs simulés (poids) : visiteurs 50, auteurs 15, relecteurs 10,
participants 10, nouveaux inscrits 5, comité 5. Les visiteurs gardent le bandeau 60 s et
l'édition courante 300 s, comme un navigateur (`Cache-Control`) ; tous viennent de l'adresse
IP du poste, comme les participants derrière le Wi-Fi du lieu : le bandeau est limité à
600 requêtes par minute et par adresse.

## 4. Lecture du résultat

- Dernière ligne : `Verdict : OBJECTIF ATTEINT` ou `OBJECTIF NON ATTEINT`, avec le p95 et le
  taux d'erreurs **hors requêtes marquées « (PDF) »** (commande d'inscription, qui émet la pro
  forma), rapportées à part comme l'étude §12 le prévoit.
- `resultats/charge_stats.csv` : une ligne par requête nommée (colonne `95%`) ; une requête
  lente se lit ici, pas dans la moyenne globale.
- `resultats/charge.html` : courbes du débit, des temps et des utilisateurs.
- Coller dans le bilan du lot : la ligne du verdict, le tableau des requêtes les plus lentes,
  le nombre d'utilisateurs atteint et les erreurs (`charge_failures.csv`).

Le coût du hachage du mot de passe à la connexion (R14) se mesure **à part** : quelques
connexions réelles chronométrées depuis le navigateur (étape 3 du runbook).

## 5. Après le test (sur l'hébergement)

```bash
python manage.py loadtest_sessions --revoke ~/gestconf-sessions.json && rm ~/gestconf-sessions.json
```

Puis **revenir à l'état d'avant le test** : restaurer la sauvegarde prise à l'étape 2 dans une
base neuve (`deploy/restore.sh`, voir `deploy/README.md`) et y repointer l'application, ou
réinstaller une base vide. Les données fictives ne se purgent pas : leurs pièces comptables
sont numérotées en ajout seul (RG-14).

## 6. Essai local (développeur)

Contre `runserver` et une base MariaDB dédiée (jamais la base de développement) :

```bash
# backend/ : base « gestconf_volume » vide, migrée
DATABASE_URL=mysql://…/gestconf_volume python manage.py seed_volume --confirm-fictitious
DATABASE_URL=mysql://…/gestconf_volume python manage.py loadtest_sessions --confirm-fictitious --output /tmp/sessions.json
DATABASE_URL=mysql://…/gestconf_volume python manage.py runserver --noreload

# loadtest/ : pas de pages pré-rendues derrière runserver
GESTCONF_PAGES= GESTCONF_SESSIONS=/tmp/sessions.json locust --headless \
  --host http://localhost:8000 --users 50 --spawn-rate 5 --run-time 2m
```

Le serveur de développement n'est pas un serveur de production : l'essai local vérifie les
scénarios, pas la tenue en charge.
