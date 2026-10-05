# Lot L1 « Socle » : plan final proposé, à valider avant tout code

> **Historique des révisions.**
> - **v1** (5 octobre 2026) : synthèse de trois plans concurrents.
> - **v2** (5 octobre 2026) : **corrections après relecture adverse.** Les 21 points et les 11 manques de la relecture ont été repris un par un et revérifiés dans le code installé, avec quatre essais. Un point est réfuté (§3.1, noms d'énumérations), un autre est appliqué par une solution plus stricte que celle proposée (RG-20). *Complément v3 : un troisième écart n'était pas déclaré. Le point 11 a été appliqué plus largement que proposé : le registre `IDENTITY_FIELDS` est lui aussi reporté, faute de consommateur en L1 (§5.4).* Les sept corrections majeures :
>   1. **RG-20** : allauth.mfa interdit d'ajouter une adresse à un compte protégé par la 2FA (vérifié par essai ; précisé en v3 : en mode « lien » seulement, voir D6). L'adresse invitée est désormais rattachée au compte par un lien de confirmation propre au service (§5.7).
>   2. **CSRF sous DRF** : l'échec ne passe jamais par `CSRF_FAILURE_VIEW` et renvoie `permission_denied` (vérifié par essai). Le code `csrf_failed` est maintenant produit par notre `SessionAuthentication` et par une permission dédiée aux POST anonymes (§4.6).
>   3. **Anti-énumération** : la voie rapide d'envoi ne concerne plus que les e-mails envoyés dans tous les cas. Le hachage est égalisé à l'inscription, où un écart de 750 ms contre 8 ms a été mesuré (§4.3, §8.3).
>   4. **`pending_key`** : remplacée par une empreinte SHA-256 de longueur fixe. Les invitations échues expirent dès la création suivante (§3.3).
>   5. **Session** : la limite de 12 h absolues est imposée par un middleware, car Django fait glisser l'expiration. `ACCOUNT_SESSION_REMEMBER` est sans effet en *headless* (D12).
>   6. **Anonymisation** : l'adresse est aussi effacée du registre d'envoi, des invitations traitées, des clichés d'audit et des sessions. Un test de balayage le vérifie (§4.9).
>   7. **Charge** : réestimée à **22 à 27,5 j-h**, avec L1.4 et L1.7 à 4–5 j-h. La variante courte devient un scénario de repli décidé d'avance (§13).
> - **v3** (5 octobre 2026) : **corrections après une seconde relecture adverse** (un point majeur, sept mineurs). Tous sont appliqués, après vérification dans le code installé et sept essais jetables. Aucun n'est réfuté ; deux sont appliqués plus largement que proposé (points 1 et 8). Les corrections :
>   1. **Réauthentification des adresses e-mail (majeur).** La v2 affirmait à tort qu'allauth l'exige déjà. Il ne l'exige que si `ACCOUNT_REAUTHENTICATION_REQUIRED` vaut `True` (défaut `False`), et l'ajout d'une adresse n'est notifié à personne. Essai : depuis une session ouverte, sans mot de passe, on ajoute une adresse, puis `password/request` envoie le lien de réinitialisation à cette adresse, **même non vérifiée**. Corrections : réglage activé, `RecentAuthRequired` sur la liaison RG-20, notification « adresse ajoutée » à l'adresse principale, aucune réinitialisation vers une adresse secondaire non vérifiée, refus d'accepter une invitation que l'on a soi-même envoyée (D12, §4.2, §4.3, §4.11, §5.7).
>   2. **Blocage d'ajout d'adresse par allauth.mfa.** Il est aussi levé par la vérification par code. Cette solution native devient l'option (b) de D6. La recommandation reste le lien de liaison (a), pour une raison établie par essai : en mode code, le renvoi du code n'envoie rien quand l'inscription visait un compte existant, ce qui recréerait un oracle temporel avec la voie rapide.
>   3. **Liste des éditions de gestion.** Elle devient une vue à part, `ManageEditionListView`, hors de `ManageViewSet` et sans 2FA (D3, §5.3, §5.9).
>   4. **Quota d'invitations.** Son dépassement lève `QuotaExceeded`, traduite en 429 avec `Retry-After`. La limite `invitation_create` ne s'applique qu'à la création, pas à la consultation de la liste (§4.7, §9.1).
>   5. **Voie rapide.** Elle est choisie par gabarit, et non plus par priorité, et plafonnée à 3 envois par requête (§8.3).
>   6. **Anonymisation.** Le message libre des invitations et l'objet des e-mails sont aussi traités (§4.9).
>   7. **Historique v2 complété** (report du registre `IDENTITY_FIELDS`). La liste des champs d'identité et la conception du contrôle RG-04 (champs imbriqués, recherche par valeurs) sont conservées pour L4 (§5.4).
>   8. **Noms d'énumérations.** La liste des surcharges est complétée et contrôlée par un méta-test. Une surcharge commune, `ServiceStatus`, est nécessaire : `database` et `cache` partagent le même jeu de choix, ce qui déclenche un avertissement, constaté par essai (§3.1, §9.5).
>   9. **Deux incohérences relevées au passage.** `RoleInvitation.invited_by` devient nullable, car `create_edition --admin-email` crée une invitation sans invitant (§3.3). `RecentAuthRequired` est livrée en L1.5, dont les endpoints en ont besoin, et non plus en L1.6 (§13).
>
>   Charge : **22,75 à 28 j-h** (+0,25 sur L1.3 et +0,25 sur L1.5).
> - **v4** (5 octobre 2026) : **six corrections mineures après une troisième relecture adverse**, sans effet sur la charge : répartition de la hausse de L1.5 (D6, §13) ; e-mail de liaison d'adresse ajouté à la voie rapide (§8.3, §10.2, §12.1) ; code `invitation_self_accept` (§5.7, §9.1, §12.1) ; durée de conservation des invitations annulées (D15, §3.3, §8.4) ; test d'audit fondé sur les valeurs (§7.5) ; conception du contrôle RG-04 conservée pour L4 (§5.4).

> **Statut : validé par le commanditaire le 5 octobre 2026 (« OK D1–D18 »).** Les recommandations des décisions D1 à D18 s'appliquent.
>
> **Statut initial.** Ce document était une proposition. `CLAUDE.md` exige un plan validé avant toute modification large : modèle de données, permissions, workflow de statuts. **Aucun code ne sera écrit avant votre accord** : seul ce document a été ajouté au dépôt.
>
> **Date.** 5 octobre 2026 (version 4).
>
> **Sources.**
> - L'étude v1.0, qui fait foi, et `CLAUDE.md`.
> - Le code L0 (`backend/`, `web/`, `deploy/`, CI).
> - Trois rapports préparatoires : les exigences de l'étude, les bibliothèques installées et testées (y compris sur MariaDB 10.11.14 en local), et l'intégration au code L0.
> - Deux relectures adverses sourcées (v2 et v3).
>
> **Construction.** Trois plans concurrents ont été rédigés, puis fusionnés :
> - le plan « MVP » sert de base, pour la discipline de périmètre, la charge et les jalons ;
> - le plan « architecture » apporte l'exactitude technique et des abstractions minimales mais justifiées ;
> - le plan « sécurité » apporte le modèle de menaces, la précision des flux d'authentification et les matrices de droits.
>
> **Conventions.**
> - **(vérifié)** : comportement lu dans le code installé.
> - **(vérifié par essai)** : comportement constaté en exécutant le code installé (projet jetable, hors dépôt).
> - **(à vérifier)** : rien n'est encore établi. On ne s'en servira pas avant de l'avoir vérifié.
>
> **Points revérifiés pour ce plan dans le code installé** (allauth 65.19.7, Django 5.2.17, DRF 3.18.1, drf-spectacular 0.30.0, cryptography 50.0.2, `@angular/build` 22.2.1) :
> - `manage.py check` sans `--database` ne lance pas les contrôles de contraintes (W036) ;
> - les enregistrements d'authentification de la session portent un horodatage `at` ;
> - `ACCOUNT_REAUTHENTICATION_TIMEOUT` vaut 300 s par défaut ;
> - `ACCOUNT_EMAIL_NOTIFICATIONS` vaut `False` par défaut, et ces notifications passent par `send_mail` ;
> - le réglage `ACCOUNT_EMAIL_UNKNOWN_ACCOUNTS` existe (défaut `True`) ;
> - `ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION` vaut `False` par défaut ;
> - la désactivation du TOTP exige une réauthentification récente ;
> - le marqueur `{key}` de `HEADLESS_FRONTEND_URLS` peut figurer n'importe où dans l'URL, y compris après `#` ;
> - le délai `confirm_email` vaut 1/180 s par adresse ;
> - la clé de réinitialisation de mot de passe repose sur le générateur de Django, valable 3 jours par défaut (`PASSWORD_RESET_TIMEOUT`) ;
> - la durée de session Django vaut 14 jours par défaut ;
> - `Fernet` et `MultiFernet` fonctionnent en aller-retour ;
> - `ENUM_NAME_OVERRIDES` et `POSTPROCESSING_HOOKS` existent dans drf-spectacular ;
> - le réglage `NUM_PROXIES` existe dans DRF ;
> - par défaut, `OrderingFilter` autorise le tri sur les champs du sérialiseur ;
> - MariaDB prend en charge les contraintes `CHECK` ;
> - `deploy/deploy.sh` lance `npx ng build` sans injecter la CSP.
>
> **Ajoutés en v2 :**
> - allauth.mfa refuse d'ajouter une adresse à un compte qui a la 2FA (`add_email_blocked`) tant que `MFA_ALLOW_UNVERIFIED_EMAIL` vaut `False`, la valeur par défaut. Le flux *headless* est concerné (vérifié par essai). **Précisé en v3 :** ce blocage ne vaut qu'en mode « lien ». Il est aussi levé quand `ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED` vaut `True` (vérifié, `mfa/signals.py:51-58`) ;
> - allauth refuse d'activer le TOTP (409 `unverified_email`) tant que le compte porte une adresse non vérifiée (vérifié par essai) ;
> - sous DRF, un échec CSRF lève `PermissionDenied`, donc le code `permission_denied`, sans passer par `CSRF_FAILURE_VIEW` (vérifié par essai). `csrf_protect` est sans effet sur une vue DRF, déjà marquée `csrf_exempt` (vérifié) ;
> - DRF exécute authentification, permissions et limites de débit dans `initial()`, avant `get_queryset()` (vérifié) ;
> - la date d'expiration d'une session en base est recalculée à chaque enregistrement (vérifié par essai : une réauthentification la repousse) ;
> - la connexion *headless* n'appelle pas `set_expiry` : `ACCOUNT_SESSION_REMEMBER` est sans effet, et le cookie de session garde `max-age=SESSION_COOKIE_AGE` (vérifié par essai) ;
> - l'inscription prend environ 750 ms pour une adresse nouvelle contre environ 8 ms pour une adresse existante, car seul un nouveau compte calcule un hachage PBKDF2. La réponse est pourtant identique (401) (vérifié par essai, SQLite, poste local) ;
> - en mode « lien », `auth/email/verify/resend` répond 409 : il ne sert qu'au mode « code ». Le lien est renvoyé par une nouvelle connexion, une fois la fenêtre de 180 s passée (vérifié par essai) ;
> - avec `EMAIL_UNKNOWN_ACCOUNTS=False`, `password/request` n'envoie rien pour une adresse inconnue (vérifié). `transaction.on_commit` s'exécute immédiatement hors transaction (vérifié) ;
> - les contextes des e-mails d'allauth contiennent `user`, `request`, `current_site`, et `uid`/`key` pour la réinitialisation (vérifié) ;
> - les enregistrements d'authentification de la session contiennent l'adresse e-mail saisie (vérifié) ;
> - allauth authentifie par toute adresse **vérifiée** du compte, principale ou non (vérifié) ;
> - drf-spectacular renomme `StatusEnum` en `HealthStatusEnum` **sans avertissement** quand un second champ `status` apparaît, avec un code de sortie 0 malgré `--fail-on-warn` (vérifié par essai) ;
> - `MFAAdapter.build_totp_url` et `build_totp_svg` existent. Le second utilise `qrcode`, installé par l'extra `mfa` (vérifié) ;
> - `DatabaseCache` exécute un `COUNT(*)` à chaque écriture. Au-delà de `MAX_ENTRIES`, il supprime les entrées expirées, puis un tiers des clés par ordre alphabétique (vérifié) ;
> - l'avertissement Django `mysql.W002` signale un `sql_mode` non strict (vérifié) ;
> - `django.core.signing.dumps` / `loads(max_age=…)` existent (vérifié) ;
> - `@angular/build` 22.2.1 accepte `inject: false` sur une entrée de `styles` (vérifié dans le schéma du builder).
>
> **Ajoutés en v3 :**
> - `ACCOUNT_REAUTHENTICATION_REQUIRED` vaut `False` par défaut (`account/app_settings.py:549-550`). L'ajout et la suppression d'une adresse, ainsi que le choix de l'adresse principale, n'exigent une réauthentification que s'il vaut `True` (`account/internal/flows/manage_email.py:23, 60, 85`). Sans ce réglage, `POST account/email` ajoute une adresse sans réauthentification récente ; avec lui, la réponse est 401 avec le flux `reauthenticate`, et rien n'est ajouté (vérifié par essai) ;
> - l'ajout d'une adresse n'est notifié à personne. Pour les adresses, `send_notification_mail` n'est appelé qu'à la suppression (`email_deleted`) et au changement d'adresse principale (`email_changed`) (vérifié). Le signal `email_added` est émis à l'ajout en mode lien, et après la saisie du code en mode code (vérifié par essai) ;
> - `password/request` envoie le lien de réinitialisation à une adresse **non vérifiée** du compte quand aucune adresse vérifiée identique n'existe (`filter_users_by_email(prefer_verified=True)` ; vérifié par essai) ;
> - le changement de mot de passe *headless* exige l'ancien mot de passe (`current_password`), pas une réauthentification récente. Il notifie l'adresse principale (`password_changed`) (vérifié) ;
> - les flux 2FA (activation et désactivation du TOTP, génération et consultation des codes de secours) exigent toujours une réauthentification récente, quel que soit ce réglage (vérifié) ;
> - en mode « code », `on_add_email` d'allauth.mfa ne bloque pas l'ajout : l'adresse n'est enregistrée, déjà vérifiée, qu'après la saisie du code (`account/forms.py:559-567` ; vérifié par essai sur un compte 2FA) ;
> - en mode « code » toujours : l'état de vérification est rangé dans la session ; le code vaut 15 min (`EMAIL_VERIFICATION_BY_CODE_TIMEOUT`) et autorise 3 essais ; une saisie depuis une autre session est refusée (409) ; le renvoi répond 409 sauf si `ACCOUNT_EMAIL_VERIFICATION_SUPPORTS_RESEND` vaut `True` (2 renvois) ; après une perte de session, une nouvelle connexion envoie un nouveau code, passé un délai de 10 s (avant : 400 `too_many_login_attempts`) ; la saisie du code à l'inscription connecte la personne (vérifié par essai) ;
> - en mode « code », `auth/email/verify/resend` répond 200 dans les deux cas, mais n'envoie **rien** quand l'inscription visait un compte existant (`skip_enumeration_mails`), alors qu'un nouveau compte reçoit un code (vérifié par essai). Le premier envoi et le renvoi utilisent le même gabarit (vérifié) ;
> - en mode « lien », le lien de vérification est valable 3 jours (`ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS`, vérifié) ;
> - DRF : `ScopedRateThrottle` lit `throttle_scope` sans tenir compte de la méthode ; `get_throttles()` peut être surchargée ; `self.action` est posé par `initialize_request`, avant `initial()` ; `Throttled(wait=…)` donne le code `throttled` et l'en-tête `Retry-After` (vérifié) ;
> - drf-spectacular : une surcharge `ENUM_NAME_OVERRIDES` s'applique à un **jeu de choix**, pas à un champ. Deux champs de noms différents qui partagent le même jeu (`database` et `cache` : `ok`, `error`) déclenchent l'avertissement « multiple names for the same choice set », donc l'échec avec `--fail-on-warn`. Une surcharge commune le supprime (vérifié par essai). Les choix vides ou nuls produisent les composants `BlankEnum` et `NullEnum` (vérifié) ;
> - `DatabaseEnum` et `StatusEnum` ne sont utilisés que dans le client généré (vérifié).

## En bref

| | |
|---|---|
| **Ce que livre L1** | Un compte unique : inscription, vérification de l'e-mail, mot de passe oublié, profil, consentements, export et anonymisation. Des rôles rattachés à une édition et attribués par invitation. Une 2FA TOTP imposée côté serveur aux rôles de gestion. Le paramétrage minimal de l'édition. Le journal d'audit (RG-17). Une file de tâches et d'e-mails pilotée par cron. Le kit UI, les écrans de compte (portail) et les écrans de gestion (paramétrage, membres, audit). La correction des dettes L0 |
| **Jalons** | **J-tech (≈ j5)** : sur o2switch, un e-mail réel part par le cron. **Démo A (≈ j13)** : parcours de compte complet sur l'hébergement réel. **Démo B (≈ j23)** : un administrateur d'édition protégé par la 2FA paramètre et publie l'édition, puis invite le comité, qui accepte. **Fin de L1 (≈ j25)** |
| **Charge** | **22,75 à 28 j-h**, contre 15 à 20 dans l'étude (§14.3). L1.4 et L1.7 ont été réestimées à 4–5 j-h chacune ; les corrections de sécurité de la v3 ajoutent 0,5 j-h. Environ 7 à 9 j-h sont explicitement reportés vers L2, L3 et L4, de même que le déploiement continu (écart de périmètre à valider, D18). Une variante courte, d'environ 20,5 à 25,75 j-h, sert de **scénario de repli décidé d'avance** (§13) |
| **Décisions** | 18 questions (§2). Cinq bloquent le démarrage : **D1** (autorité de plateforme), **D2** (bibliothèque 2FA, qui modifie la stack de `CLAUDE.md`), **D3** (périmètre de la 2FA), **D4** (contrat d'authentification), **D18** (périmètre, charge et repli). Pour les autres, la recommandation sert d'hypothèse de travail réversible tant que vous n'avez pas répondu |
| **Prérequis** | Un accès cPanel/SSH à o2switch (étape L1.0). Un nom de domaine, ou un sous-domaine provisoire, pour l'expédition des e-mails (D10) |

---

## 1. Objectif et périmètre

### 1.1 Objectif

Livrer le socle sur lequel L2, L3 et L4 (le MVP) se construiront sans refonte :
- un compte unique avec adresse vérifiée ;
- des droits par édition vérifiés **côté serveur** et testés case par case (règles n° 2 et 5) ;
- une édition paramétrable sans admin Django (règle n° 1) ;
- un journal d'audit ;
- une file de tâches compatible avec le cron d'un hébergement mutualisé (règle n° 9) ;
- l'i18n FR/EN de bout en bout ;
- un kit UI.

**Principe de tri.** L1 ne contient que deux sortes d'éléments :
- **(a)** ce dont L2, L3 et L4 ont besoin pour démarrer ;
- **(b)** ce qui coûterait cher à ajouter une fois de vrais utilisateurs inscrits (consentements, 2FA, contrat d'API).

Une abstraction n'entre en L1 que si elle a **au moins un consommateur réel en L1 et un consommateur identifié ensuite**. Le reste est reporté, avec son lot cible. La v2 applique ce principe à la préparation spécifique de RG-04 et à `Consent.edition`, toutes deux reportées (§1.3).

**Critère de fin global (démo B, sur o2switch).**
1. L'opérateur crée la conférence et l'édition par commande, puis invite le premier administrateur d'édition (`ADMIN`).
2. Celui-ci crée son compte, vérifie son adresse, active la 2FA, paramètre l'édition en FR/EN et la publie.
3. Il invite un président du comité scientifique (`SC_CHAIR`). Celui-ci crée son compte, accepte, active la 2FA, puis invite à son tour un relecteur (`SC_MEMBER`).
4. Le relecteur accepte, puis reçoit un refus (403) sur le paramétrage.
5. Le journal d'audit montre chaque étape : qui, quoi, quand, avant/après.
6. Les e-mails sont réellement reçus.

### 1.2 Inclus dans L1

| Élément | Pourquoi en L1 |
|---|---|
| **Comptes** via `django-allauth` en mode *headless*, client `browser` seul : inscription, vérification obligatoire de l'e-mail, connexion, déconnexion, mot de passe oublié et changement, réauthentification, `GET/PATCH /me`, langue initialisée à l'inscription puis mémorisée | Les auteurs (L3) et les relecteurs (L4) en ont besoin. Ce sont des flux de sécurité à ne pas réécrire à la main |
| **Profil** : titre, nom, prénom, institution, département, pays ISO, ORCID saisi à la main avec contrôle de sa clé, biographie en texte brut | L3 a besoin d'un profil complet (affiliation, pays) |
| **Consentements horodatés et versionnés** | Les ajouter après l'arrivée d'utilisateurs réels obligerait à relancer tout le monde |
| **2FA TOTP + codes de secours** (`allauth.mfa`, D2), imposée côté serveur aux rôles de gestion (D3) | L'imposer en pleine campagne serait coûteux. Les rôles de gestion verront l'identité des auteurs dès L3 |
| **Conférence, édition, tracks, types de communication, dates clés, confidentialité**, statut de l'édition, service de calendrier | L2 affiche ces données ; L3 en dépend (type, track, fenêtre de l'appel) |
| **`UserRole` par édition, invitations par e-mail** (acceptation et refus tracés), révocation, service `grant_role` idempotent | L4 doit inviter les relecteurs ; L3 attribue `AUTHOR` |
| **Cadre de permissions par édition** : table rôles → capacités, classes DRF, filtrage des querysets, sérialiseurs par rôle, test de complétude de la matrice | Le contrôle des droits coûterait cher à reprendre endpoint par endpoint. RG-04 (L4) s'appuiera sur ces mécanismes génériques |
| **Journal d'audit (RG-17)** : modèle en ajout seul, service `record`, consultation par édition | RG-02 (L3), les décisions et la levée d'anonymat (L4) s'y branchent |
| **File `Job` + `run_jobs` par cron, registre d'envoi `OutboxEmail`**, fournisseur transactionnel, e-mails de compte FR/EN, classe de commande verrouillée commune | Les e-mails de compte sont indispensables. On lève tôt deux risques d'hébergement : le cron et la délivrabilité |
| **Export de ses données et anonymisation de son compte**, avec un registre « données personnelles » extensible | Fixe la conception dès le départ (FK `RESTRICT`, anonymisation plutôt que suppression). Chaque lot ajoutera ses données |
| **Kit UI (Angular Material)**, `AuthService`, intercepteurs, gardes de route, sélecteurs d'édition et de rôle | Sert à tous les écrans de L2 à L4 |
| **Contrat d'API** : 401 uniforme, erreurs JSON y compris pour un échec CSRF (allauth **et** DRF), catalogue de codes d'erreur, noms d'énumérations stables, type `ApiError` | Un contrat qui change après coup casse le client généré et tous les écrans |
| **Dettes L0** : CSP non posée par `deploy.sh` (vérifié), limitation de débit inopérante, cache propre à chaque processus, vérifications o2switch restées ouvertes | Corrections de sécurité, préalables à tout le reste |

### 1.3 Exclu de L1 (reporté)

| Élément | Raison | Lot cible |
|---|---|---|
| Connexion ORCID (OAuth) | Classée P2 (M2). Exige l'extra `socialaccount` et l'ouverture de la directive CSP `form-action`. En L1, seul le champ `orcid` est saisi, avec contrôle de sa clé | V1 (P2), après le MVP |
| Photo de profil, réseaux professionnels, classe « fichier public » | Les photos publiques contredisent la règle n° 8 (B11). Inutiles avant le portail | L2 |
| Annuaire public des comités | Le consentement est prêt en L1 ; l'affichage relève du portail | L2 |
| Contenus du portail, texte riche (`nh3`) | Aucun texte riche en L1 | L2 |
| `GET /public/key-dates` séparé | Les dates publiques sont incluses dans `/public/editions/current` (§9.3) | L2 si besoin |
| Anti-robots (Turnstile, hCaptcha…) | Tiers, modification de la CSP, transfert de données (D16) | Avant l'ouverture de l'appel (L3) |
| Modèles d'e-mails modifiables par édition, écran « file d'envoi », webhooks de rebond | En L1, les e-mails de compte sont des gabarits versionnés ; la file se consulte par commande | L3 |
| Notifications dans l'application (cloche) | Premier événement concerné : « soumission déposée » (A2) | L3 |
| Compteurs de numérotation (`GC26-0123`) | Aucun consommateur en L1. Le préfixe `Edition.code` est créé dès L1 | L3 |
| Stockage privé des fichiers ; formats, taille, article complet par type de communication ; langues des soumissions | Dépendent du stockage, de Q5 et de Q6 (ambiguïté C13). Colonnes ajoutées de façon additive | L3 |
| `Consent.edition` (consentements propres à une édition) | Aucun consentement d'édition avant L3 : la colonne n'aurait aucun consommateur. Elle sera ajoutée par une migration additive (nullable) | L3 |
| Gel de `double_blind` et du code après l'ouverture de l'appel (RG-19 proposée) ; états automatiques déclenchés par les dates | La vraie condition, « une soumission existe », n'apparaît qu'en L3. En L1, ces changements sont audités | L3, L4 |
| **Préparation spécifique de RG-04** : registre `IDENTITY_FIELDS`, classe `AnonymizedSerializer` et son méta-test, utilitaire `assert_no_identity_leak` | Aucun consommateur en L1 : aucun sérialiseur relecteur n'existe, et un méta-test sur une classe sans sous-classe ne teste rien. L1 livre les mécanismes génériques dont RG-04 aura besoin (§5.4). La liste des champs d'identité établie en v1 est conservée au §5.4, comme donnée d'entrée de L4 | Début de L4, avant le premier endpoint relecteur |
| Grilles d'évaluation, seuils, charge maximale, RG-07, président de track, expertises et disponibilités | Consommés par l'évaluation. Les expertises seront relationnelles, pas en JSON (§8.3) | L4 |
| Indicateurs du tableau de bord (US-12) | Ils n'existent qu'avec des soumissions. L1 livre un accueil récapitulatif | L4 |
| Écritures « partielles » du CO selon sa fonction | Q12 non tranchée ; le CO a seulement la lecture en L1 (D8) | L5, L6 |
| Invitation aux rôles `SPEAKER`, `SESSION_CHAIR`, `SPONSOR`, `VOLUNTEER` | Valeurs déclarées dans l'énumération dès L1, invitation activée dans leur lot | L5 à L8 |
| Fil d'activité non sensible du CO (M11) | À distinguer du journal d'audit (B7) | L8 |
| Écrans « Utilisateurs » et « Conférences / Éditions », exports RGPD lancés par un administrateur | Remplacés par des commandes `manage.py` auditées (D1) | L8 si besoin |
| Purge RG-18 des données d'édition selon une durée de conservation | Dépend du cadre légal (Q14). Aucune donnée d'édition à purger avant L3 | L3 (champ), L8 (purge) |
| Sentry ou équivalent | Transfert à un tiers (D17) | L9 |
| E2E Playwright, audit d'accessibilité automatisé (axe) | Le premier parcours E2E significatif est celui de l'auteur (A6 prévoit l'E2E en L9) | L3 |
| **Déploiement continu depuis la CI (CD)**. **Écart de périmètre à valider** : l'étude (§14.1) place « CI/CD » dans L1 | Il faut stocker une clé SSH de production chez un tiers, et l'accès SSH depuis les runners n'est pas vérifié. L1 garde l'intégration continue (tests, contrôles, artefact de build). Voir D18 | Étape dédiée avant l'ouverture de l'appel (L3), idéalement en tête de L2 |
| Changement d'adresse principale (`ACCOUNT_CHANGE_EMAIL`), WebAuthn, « faire confiance à cet appareil » | P2 ou P3 | Après le MVP |

### 1.4 Prérequis préparés pour L2–L4

| Brique livrée en L1 | Consommateur en L1 | Consommateurs ultérieurs |
|---|---|---|
| `Actor` (acteur, canal, IP, identifiant de requête), passé aux services à la place de la requête | `grant_role`, invitations, paramétrage | `transition(submission, to_state, actor)` (règle n° 4, L3), décisions (L4) |
| `core.audit.record()` et `snapshot()` (liste blanche de champs) | Rôles, paramétrage, connexions, 2FA | RG-02 (L3), levée d'anonymat et décisions (L4) |
| `DomainError`, traduite en HTTP, et catalogue de codes d'erreur | Toutes les règles de service L1 | Tous les services |
| Table rôles → capacités, `HasCapability`, `EditionScopedViewMixin` (édition chargée avant les permissions), point d'extension `scope_queryset()`, sérialiseur choisi selon les capacités | Endpoints `/v1/manage/editions/{id}/…` (membres et invitations filtrés par rôle) | Toutes les vues par édition. **RG-04 (L4)** : le relecteur ne voit que ses affectations, avec un sérialiseur dédié |
| Harnais « matrice des droits » et test de complétude des routes | Endpoints `/manage` | Chaque lot y ajoute ses lignes |
| Tri et filtres toujours explicites (méta-test contre `"__all__"`) | Audit, membres, invitations | RG-04 (L4) : pas de tri sur un champ caché |
| File `Job` (registre, `run_jobs`, verrou, reprise) | Envoi des e-mails | Relances (L3, L4), PDF (L7) |
| Classe de commande verrouillée `LockedCommand` | `run_jobs`, `cleanup`, `check_integrity` | `send_reminders` (L3, L4), `sync_payments` (L6), `backup_db` |
| `OutboxEmail` et rendu dans la langue du destinataire | Vérification, réinitialisation, invitations | Notifications de statut (L3, L4) |
| Registre « données personnelles », avec test d'introspection des FK vers `User` et test de balayage après anonymisation | Profil, consentements, rôles, invitations, e-mails, sessions | Soumissions (L3), évaluations (L4), factures avec conservation légale (L6) |
| Convention de la « clé d'unicité nullable » (§3.1), stockée en empreinte de longueur fixe | Une seule invitation en attente par personne et par rôle | Unicité d'une affectation active (L4) |
| `Edition.code`, `Track`, `SubmissionType`, `KeyDate`, service `key_date(edition, code)` et `is_call_open(edition, at)` | Paramétrage, édition publique | Formulaire de soumission, RG-02 (L3) |
| `GET /v1/public/editions/current` (lecture minimale) | Test de fumée de §11.4 | Pages du portail (L2) |
| Coque `gestion`, kit UI, `AuthService`, normalisation des erreurs | Écrans L1 | Tous les écrans de L2 à L4 |

---

## 2. Décisions à valider par le commanditaire

Ces décisions vous reviennent. Chacune porte une recommandation argumentée. Vous pouvez répondre « OK D1–D18 », ou corriger un point précis.

### 2.0 Récapitulatif

| # | Question | Recommandation | Bloque |
|---|---|---|---|
| D1 | Qui a autorité sur la plateforme ? | Pas de rôle global : commandes `manage.py` auditées, exécutées par l'opérateur | **Démarrage** (L1.5) |
| D2 | Quelle bibliothèque pour la 2FA ? | `allauth.mfa` au lieu de `django-otp` (modifie `CLAUDE.md`) | **Démarrage** (L1.6, vérification en L1.0) |
| D3 | 2FA : quel lot, quels rôles, à quel moment ? | L1 ; `ADMIN`, `CHAIR`, `SC_CHAIR`, `OC_MEMBER` ; vérifiée à l'accès à `/manage/editions/{id}/…` (pas pour la liste des éditions) ; `SC_MEMBER` tranché avant L4 | **Démarrage** |
| D4 | Contrat des endpoints d'authentification ? | Chemins allauth, 401 uniforme, `csrf_failed` sur allauth et DRF, façade TypeScript manuelle avec tests de contrat | **Démarrage** (L1.1, L1.3) |
| D5 | Comment désigner l'édition dans l'API ? | Dans le chemin : `/v1/manage/editions/{edition_id}/…` | L1.5 |
| D6 | Statut des rôles et invitations ? Rattachement d'une adresse invitée à un compte 2FA ? | Table d'invitations séparée ; `UserRole` en `active`/`revoked` ; RG-20 proposée (adresse contrôlée) ; pour un compte 2FA invité à une autre adresse, lien de liaison (a) plutôt que vérification par code (b) | L1.5 (L1.3 et L1.4 si (b)) |
| D7 | Qui attribue quel rôle ? Quand attribuer `AUTHOR` et `ATTENDEE` ? | Matrice du §5.5 ; `AUTHOR` au premier brouillon (L3), `ATTENDEE` à l'inscription confirmée (L6) | L1.5 |
| D8 | Droits du CO et du président du CS sur le paramétrage ? | CO en lecture seule ; président du CS en lecture (écart avec §3.3, B20) | L1.5 |
| D9 | Kit UI ? | Angular Material 22 (MIT) | L1.4 |
| D10 | Fournisseur d'e-mails et domaine d'expédition ? | `django-anymail` avec Brevo ou Mailjet, à choisir | **J-tech** (L1.2) |
| D11 | Où se connecte-t-on ? | Pages de compte dans le portail (`/compte/*`) ; la gestion redirige | L1.4 |
| D12 | Durée de session et réauthentification ? | 12 h absolues, imposées par un middleware ; session fermée avec le navigateur ; réauthentification de moins de 5 min pour les actions sensibles, y compris la gestion des adresses e-mail (`ACCOUNT_REAUTHENTICATION_REQUIRED`) | L1.3 |
| D13 | Comment saisir les échéances ? | Heure locale de l'édition, convertie côté serveur ; clôture à 23 h 59 heure de l'édition | L1.5 |
| D14 | Comment gérer les contenus bilingues ? | Colonnes `_fr` / `_en` ; EN obligatoire pour publier | L1.5 |
| D15 | Données personnelles : cadre, notice, durées, anonymisation ? | Notice v0 provisoire ; anonymisation immédiate après réauthentification ; journal conservé | Mise en production |
| D16 | Anti-robots ? | Reporté, à trancher avant l'ouverture de l'appel | L3 |
| D17 | Remontée des erreurs ? | E-mail minimal aux opérateurs ; Sentry reporté | L1.2 |
| D18 | Périmètre, charge, repli, exploitation (CI/CD, recette, sauvegardes) ? | Ce plan (22,75 à 28 j-h) ; variante courte (20,5 à 25,75 j-h) en repli déclenché par seuils ; CD hors de L1 (écart à valider) ; aucune donnée réelle avant une restauration testée | **Démarrage** |

### D1. Autorité de plateforme

**Le problème.** L'étude se contredit (A3). §3.1 décrit un « administrateur technique » global. §3.2 et la règle n° 5 rattachent tous les rôles à une édition. §7.3 prévoit `create_platform_admin`. Il faut donc décider qui crée la conférence et les éditions, et qui gère les comptes, communs à toutes les éditions.

**Options.**
- **(a) Rôle global implicite** (`is_superuser`). Exclu par la règle n° 5.
- **(b) Rôle de plateforme explicite** : table dédiée, attribuée par commande, 2FA, audit, écrans propres. Environ +2 à 3 j-h.
- **(c) Commandes `manage.py` seulement**, exécutées par la personne qui a l'accès SSH. Chaque commande est auditée, avec un motif obligatoire pour les actions sensibles. Commandes prévues :
  - `create_conference`, `create_edition --admin-email` (attribue le rôle `ADMIN` si un compte vérifié existe, sinon envoie une invitation) ;
  - `set_current_edition` ;
  - `grant_role`, `revoke_role` ;
  - `reset_mfa`, `deactivate_user`, `anonymize_user`, `export_user_data` ;
  - `audit_query`.

**Recommandation : (c).**
- Aucun endpoint ne permet d'agir sur le compte d'autrui : c'est la plus petite surface d'attaque.
- Elle supprime l'élévation de privilèges entre éditions : un `ADMIN` 2026 ne peut ni désactiver un `CHAIR` 2027, ni réinitialiser sa 2FA.
- Elle convient à une seule conférence (hypothèse §15.2), avec une édition créée une fois par an.

**Impact.**
- `create_platform_admin` est remplacée par les commandes ci-dessus.
- L'`ADMIN` devient un administrateur **d'édition**.
- Pas d'écran « Utilisateurs » global en L1.
- Les événements sans édition (connexions) se consultent par `audit_query`.
- Passage à (b) possible plus tard, si Q2 conclut à plusieurs conférences.

### D2. Bibliothèque de 2FA

**Options.**
- **(a) `django-otp`**, imposée par §7.2, A4 et `CLAUDE.md`. Elle n'offre aucune intégration avec allauth *headless* (vérifié). Il faudrait écrire nous-mêmes l'étape de connexion, ses endpoints, l'enrôlement, les codes de secours et la réauthentification : environ +2 à 4 j-h de code de sécurité maison.
- **(b) `allauth.mfa`**. TOTP, codes de secours et réauthentification sont exposés en JSON et intégrés au flux de connexion *headless* (vérifié de bout en bout sur MariaDB).

**Recommandation : (b), sans WebAuthn.** Trois compléments sont obligatoires :
1. **chiffrer le secret TOTP**, stocké en clair par défaut (vérifié) ;
2. utiliser un **cache partagé en base** pour l'anti-rejeu des codes ;
3. activer **`ACCOUNT_EMAIL_NOTIFICATIONS=True`**, faux par défaut (vérifié), pour alerter l'utilisateur quand sa 2FA est désactivée.

**Deux comportements d'allauth.mfa à connaître** (vérifiés par essai) :
- en mode « lien », celui que ce plan retient pour vérifier les adresses (§4.2), un compte protégé par la 2FA **ne peut plus ajouter d'adresse e-mail** (`add_email_blocked`). Le blocage est levé par `MFA_ALLOW_UNVERIFIED_EMAIL=True` **ou** par la vérification par code (`ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED=True`) (vérifié ; la v2 n'indiquait que le premier). Le cas de RG-20 se traite donc soit par un mécanisme propre, soit par le mode « code » : c'est l'option à trancher dans D6 (§5.7) ;
- le TOTP **ne s'active pas** tant que le compte porte une adresse non vérifiée (409 `unverified_email`). L'écran d'enrôlement doit le signaler (§10.2).

**Impact.**
- **Modifie la stack imposée de `CLAUDE.md`** : votre accord est requis. §7.2 et A4 sont à mettre à jour.
- Dépendance binaire : `django-allauth[mfa]` tire `fido2` et `cryptography`, même sans WebAuthn, car `allauth.headless` et `allauth.mfa` l'importent dès qu'ils sont ensemble (vérifié). Le paquet précompilé manylinux2014 existe ; son installation sur o2switch reste à confirmer en L1.0.
- L'extra `mfa` installe aussi `qrcode` (licence BSD, pur Python, vérifié). Il servira au QR code d'enrôlement sans dépendance supplémentaire (§10.2).
- L'extra `headless`, qui tire PyJWT, n'est pas nécessaire en client navigateur (vérifié : parcours complet sans PyJWT).
- **Repli si `cryptography` ne s'installe pas** : allauth *headless* sans `mfa`, plus `django-otp` et une étape maison, pour +3 à 4 j-h.

### D3. 2FA : lot, rôles, moment

**Le problème.**
- M2 classe la 2FA en P2, alors que §14.1 la place en L1 (P1). §1.2, §7.2 et §9.3 la disent obligatoire.
- « Comités » inclut 30 à 100 relecteurs externes, et §14.4 relève un risque d'adoption.

**Recommandation.**
- **Livrer la 2FA en L1.**
- **L'imposer à `ADMIN`, `CHAIR`, `SC_CHAIR`, `OC_MEMBER`.** La liste est codée en dur (`MFA_REQUIRED_ROLES`).
- **La vérifier à chaque requête de gestion** (*step-up*) plutôt qu'à la connexion. Un auteur n'est donc jamais gêné.
- **Exception : la liste des éditions du sélecteur** (`GET /v1/manage/editions`) n'exige pas la session MFA. Elle ne renvoie que des champs non sensibles (identifiant, code, titres, année, statut), et chaque édition exige ensuite la 2FA (§5.3). L'exiger obligerait à valider la 2FA avant même de choisir une édition, sans rien protéger de plus.
- **`SC_MEMBER`** : proposée sans être imposée, et décision à prendre **avant L4**. En L1, les relecteurs n'ont d'ailleurs accès à aucun endpoint. Si l'on retient le double aveugle, ils ne voient pas les identités, mais un relecteur compromis expose des travaux inédits. L'ajout tient en une ligne.
- **En cas de perte du téléphone** : codes de secours, sinon `reset_mfa` par l'opérateur, après vérification d'identité hors bande (procédure à valider), avec motif et audit.

**Impact :** environ 1,5 à 2 j-h. Reporter la 2FA au début de L4 ferait gagner ce temps, mais les rôles de gestion verraient des données personnelles sans 2FA dès L3. **Déconseillé.**

### D4. Contrat des endpoints d'authentification

**Le problème.** allauth *headless* diffère de §9.1 et §9.2 sur quatre points (vérifié) :
- les chemins sont de la forme `…/browser/v1/auth/login` ;
- la déconnexion se fait par `DELETE auth/session` ;
- l'enveloppe d'erreur est `{status, data, meta, errors:[{message, code, param}]}` ;
- un utilisateur non connecté reçoit 401. **Pour allauth, un 401 est une réponse normale du protocole** : amorçage d'un visiteur anonyme, flux en attente (`verify_email`, `mfa_authenticate`, `reauthenticate`), réponse à la déconnexion.

De plus, ces vues sont absentes du schéma drf-spectacular.

**Recommandation.**
- **Chemins :** garder allauth tel quel, monté sous `/api/_allauth/browser/v1/…`. Réécrire des vues DRF serait dangereux : DRF ne contrôle pas le CSRF d'un POST anonyme (vérifié).
- **401 uniforme pour notre API :** une classe `SessionAuthentication` du projet dont `authenticate_header()` renvoie `"Session"`. DRF répond alors 401 (vérifié). Sous `/api/v1/`, Angular n'a ainsi qu'un seul signal « session absente ou expirée ». Sous `/api/_allauth/`, c'est la façade qui lit `data.flows` (§10.1).
- **Échec CSRF :** `csrf_failed` en JSON sur les deux familles, par deux mécanismes distincts (§4.6) : la vue d'échec CSRF de Django pour allauth, notre `SessionAuthentication` et une permission dédiée pour DRF.
- **Client TypeScript :** une **façade écrite à la main** pour la quinzaine d'appels allauth. Elle est verrouillée par des tests de contrat côté serveur, sur les champs réellement consommés, et par une version figée d'allauth. Un second client généré ajouterait environ 1 j-h et une seconde chaîne de génération (doublons de noms dans ng-openapi-gen, **à vérifier**).
- **Format d'erreur :** l'intercepteur Angular normalise les deux formats vers `{code, message, fields}`.

**Impact.**
- Écart assumé avec §9.1 et §9.2.
- Le test L0 `test_unauthenticated_access` passe de 403 à 401.
- La règle « client généré » s'applique à notre API, pas à celle d'allauth.

### D5. Désignation de l'édition dans l'API

**Recommandation.**
- Toute ressource d'édition est sous `/v1/manage/editions/{edition_id}/…`. C'est la **seule** source : un en-tête, un paramètre ou une valeur du corps qui désignerait une édition est ignoré.
- Un utilisateur **sans rôle actif** dans l'édition reçoit **404**. On ne révèle pas ainsi l'existence des éditions en brouillon.
- Un membre sans la capacité requise reçoit **403**.
- Un objet d'une autre édition donne 404.
- **L'ordre des réponses est fixé et testé** : anonyme 401, puis non-membre 404, puis membre sans capacité 403, puis rôle sensible sans 2FA 403 (`mfa_enrollment_required` ou `mfa_required`). Pour le garantir, l'édition est chargée avant les permissions (§5.3).
- Jamais d'« édition active » mémorisée côté serveur : ce serait un état implicite.

**Impact :** §9.2 est à mettre à jour (`/manage/...` et `/sc/...` n'y précisent pas l'édition).

### D6. Rôles et invitations

**Le problème.** Le modèle de §8.2 (`user_role.status` = `invited`, `active` ou `declined`) pose quatre difficultés :
- il exige un compte existant pour inviter ;
- l'unicité bloque une ré-invitation après un refus ;
- une ligne `invited` est un piège : un filtre oublié accorderait des droits ;
- une personne ne peut pas avoir deux fonctions au CO.

**Recommandation.**
- **Table `RoleInvitation` séparée**, adressée à un e-mail, avec ou sans compte existant. Jeton haché, expiration à 14 jours.
- **`UserRole` en `active` ou `revoked` seulement.** Une ligne n'existe qu'après acceptation ou attribution : **un invité ne détient aucun droit, par construction.**
- **Unicité (`user`, `edition`, `role`, `oc_function`)**, avec `oc_function` NOT NULL valant `""` par défaut.
- **RG-20 proposée** : une invitation ne s'accepte que depuis un compte qui **contrôle l'adresse invitée**. Deux cas :
  - une adresse vérifiée du compte correspond ;
  - sinon, la personne doit d'abord prouver qu'elle contrôle l'adresse invitée et la rattacher à son compte, selon l'option retenue ci-dessous (§5.7).

  Le jeton d'invitation **seul** ne suffit jamais. Sinon, un lien transféré ou retrouvé dans un historique deviendrait un titre au porteur pour le rôle.
- **Question (précisée en v3) : comment rattacher l'adresse invitée à un compte protégé par la 2FA ?** Les personnes concernées sont justement celles qui ont la 2FA, par exemple un `CHAIR` invité dans une autre édition, à une autre adresse. En mode « lien », allauth.mfa leur refuse l'ajout d'adresse (vérifié par essai) : c'est pourquoi la proposition de la v1, « ajouter l'adresse à son compte par allauth », ne fonctionne pas telle quelle. Deux options :
  - **(a) Lien de liaison propre au service** (§5.7). Un lien signé, envoyé à l'adresse invitée et lié au compte demandeur, ajoute l'adresse comme vérifiée, puis accepte l'invitation. Il applique les mêmes protections que l'ajout d'adresse par allauth, tel que ce plan le configure (§4.2) : réauthentification récente, limite de 3 adresses, refus d'une adresse vérifiée sur un autre compte, notification à l'adresse principale. Coût : environ 0,75 j-h, dont 0,1 à 0,15 en v3 pour la réauthentification et la notification (la hausse de 0,25 j-h de L1.5 en v3 couvre aussi quatre autres travaux, voir §13). L'inscription garde le mode « lien » : un lien valable 3 jours, utilisable depuis n'importe quel appareil.
  - **(b) Vérification par code d'allauth pour toutes les adresses** (`ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED=True`). allauth.mfa ne bloque plus l'ajout, et la garde qu'il porte reste respectée : l'adresse n'est enregistrée qu'une fois le code saisi, donc toujours vérifiée (vérifié par essai sur un compte 2FA). Le cas (c) de RG-20 devient « ajoutez l'adresse dans `/compte/securite`, puis acceptez », sans jeton signé ni création maison d'`EmailAddress`. Le renvoi `auth/email/verify/resend` devient utilisable, et la saisie du code à l'inscription connecte directement la personne (vérifié par essai). **Contreparties :**
    - la vérification à l'inscription passe aussi en mode code, pour tous les comptes. Le code se saisit dans **le même navigateur**, car l'état est rangé dans la session ; il vaut 15 min (réglable) et autorise 3 essais. Si la session est perdue, une nouvelle connexion envoie un nouveau code (vérifié par essai). Comme la fréquence du cron est inconnue (R5), un code envoyé par le cron après un échec de la voie rapide pourrait expirer avant d'arriver ;
    - **le renvoi recrée un oracle temporel.** Il répond 200 dans les deux cas, mais n'envoie rien quand l'inscription visait un compte existant, alors qu'un nouveau compte reçoit un code (vérifié par essai). Le premier envoi et le renvoi utilisent le même gabarit : la voie rapide, choisie par gabarit (§8.3), ne peut pas les distinguer. Il faudrait soit exclure le renvoi de la voie rapide (le code risque alors d'expirer avant le passage du cron), soit désactiver le renvoi, ce qui ramène à « renvoyer = se reconnecter » ;
    - charge : environ −0,75 j-h sur L1.5, mais une reprise de L1.3 et L1.4 (réglages, écrans de vérification et d'ajout d'adresse, tests). Gain net estimé entre 0 et 0,5 j-h.

  **Recommandation : (a).** On ne change pas le parcours d'inscription de tous les auteurs pour un cas rare, celui d'un compte 2FA invité à une autre adresse. Le mécanisme propre reste étroit, et la v3 lui donne les mêmes protections qu'à l'ajout d'adresse par allauth. Le principal avantage de (b), le renvoi natif, est en partie illusoire à cause de l'oracle temporel. **Dans les deux cas, RG-20 est conservée** : le jeton d'invitation seul ne suffit jamais. Si vous préférez (b), la décision doit être prise avant L1.3, car elle change la configuration d'allauth et les écrans de L1.4.
- Les invitations vivent dans `accounts`. L'application `committees` (L4) ne portera que les données propres aux comités, ce qui évite un doublon (§7.3).

### D7. Qui attribue quel rôle, et attribution automatique

**Recommandation.**
- Matrice d'attribution du §5.5 :
  - `ADMIN` et `CHAIR` ne sont attribués que par un `ADMIN`, après réauthentification, ou par commande ;
  - `SC_MEMBER` peut aussi être attribué par le `SC_CHAIR` ;
  - `AUTHOR` et `ATTENDEE` sont attribués par le système uniquement.
- Le dernier `ADMIN` actif d'une édition ne peut être révoqué que par commande.
- On ne modifie jamais ses propres rôles.

**Moments d'attribution automatique** (B4), figés dans leur lot :
- `AUTHOR` : à la création du premier brouillon de soumission dans l'édition (L3). Pour un co-auteur rattaché à un compte : à trancher en L3 ;
- `ATTENDEE` : à l'inscription confirmée (L6), c'est-à-dire gratuite validée ou paiement confirmé par webhook vérifié (RG-15).

L1 livre uniquement le service `grant_role` et ses tests. **Les droits sur ses propres objets viennent de la propriété, pas du rôle.**

### D8. Droits du CO et du président du CS sur le paramétrage

**Le problème.**
- §3.3 donne au CO « L/E (partiel) » sans définir ce qui est partiel (Q12).
- Les fonctions du CO divergent entre §3.1 et M8 (A6).
- §3.3 refuse tout accès au président du CS (« — »), alors qu'il pilotera l'évaluation (B20).

**Recommandation.**
- **En L1, `OC_MEMBER` n'a que la lecture du paramétrage**, quelle que soit sa fonction (refus par défaut).
- `oc_function` reçoit l'union des deux listes : `finance`, `program`, `logistics`, `communication`, `external_relations`, `volunteers`, `secretariat`.
- Les écritures partielles seront attribuées fonction par fonction, dans le lot qui crée l'objet : programme en L5, finances en L6.
- **`SC_CHAIR`** : lecture du paramétrage (tracks, types, dates, confidentialité). C'est un écart avec §3.3, à confirmer. **Sans réponse, on applique §3.3 tel quel (aucun accès au paramétrage)** : le `SC_CHAIR` n'a alors que les capacités `members.*`, limitées au CS, et la gestion l'amène directement sur l'écran « Membres » (§10.3). La démo B fonctionne dans les deux cas.

### D9. Kit UI

**Options.**
- **Angular Material et CDK 22.2.1** : licence MIT, compatibles Angular 22 (vérifié).
- **PrimeNG 22** : seule version compatible Angular 22, sous licence commerciale « PrimeUI » avec clé obligatoire (vérifié). La licence Community est soumise à des seuils et l'ingénierie inverse est interdite. La version 21, sous MIT, ne supporte pas Angular 22.

**Recommandation : Angular Material.**
- Aucune licence à gérer.
- Styles compatibles avec la CSP actuelle (`style-src 'self' 'unsafe-inline'`) ; jeton `CSP_NONCE` disponible pour durcir plus tard (vérifié).
- Thème sobre jusqu'à ce que l'identité visuelle soit connue (Q15). Il n'alourdit pas les pages publiques du portail (§10.5).

### D10. Fournisseur d'e-mails transactionnels et domaine

**Options.**
- **`django-anymail` 15.2** avec Brevo ou Mailjet (licence BSD-3 ; aucune dépendance supplémentaire pour ces extras, vérifié).
- **SMTP d'o2switch**, par le backend natif de Django. Réputation de l'IP mutualisée et quotas non vérifiés.

**Recommandation.** anymail avec Brevo ou Mailjet, au choix, selon le compte que l'institution peut ouvrir. Quotas, prix, localisation des données et contrat de sous-traitance sont **à vérifier**. SMTP d'o2switch en secours seulement.

**Impact.**
- Il faut un **nom de domaine** pour SPF, DKIM et DMARC (Q15).
- Sans fournisseur, ni la vérification d'adresse ni les invitations ne fonctionnent en production.
- En attendant, le développement utilise le backend `console`, et les tests le backend `locmem`.

### D11. Où se connecte-t-on ?

**Recommandation.**
- Tous les écrans de compte sont dans le **portail**, sous `/compte/*`. Ils sont rendus côté client (pas de pré-rendu, car ils lisent des jetons) et marqués `noindex`. Les segments en français suivent les noms d'écrans de §7.4.
- `/gestion/` redirige vers `/compte/connexion?next=/gestion/…`. Le paramètre `next` n'accepte qu'un chemin relatif commençant par `/compte/` ou `/gestion/`, et refuse `//`, `\`, les schémas et les caractères de contrôle. Cela évite les redirections ouvertes.
- La session est unique pour les deux applications : cookies sur le chemin `/` (vérifié).

L'emplacement de l'espace évaluateur (Q16) n'est pas tranché par L1.

### D12. Sessions et réauthentification

**Le problème découvert en v2.** Django ne connaît pas d'expiration absolue. À chaque enregistrement de la session, la date d'expiration en base est recalculée à « maintenant + `SESSION_COOKIE_AGE` ». C'est le cas d'une réauthentification, d'un passage par l'étape 2FA ou d'un changement d'état d'un flux (vérifié par essai : une réauthentification repousse l'échéance). Une session volée pourrait donc être prolongée au-delà de la durée annoncée.

**Recommandation.**
- **Durée de session de 12 h absolues**, pour tous les rôles (la valeur par défaut de Django est 14 jours, vérifié), **imposée par un middleware** `AbsoluteSessionTimeoutMiddleware` :
  - à la connexion, un récepteur du signal Django `user_logged_in` pose l'horodatage `gc_login_at` dans la session. Ce signal est émis par `login()` après le renouvellement de la clé de session (vérifié), et allauth passe par `login()` (vérifié) ;
  - à chaque requête authentifiée, au-delà de 12 h, le middleware appelle `logout()` et la requête continue en anonyme. Le client reçoit donc 401, sous `/api/v1/` comme sous allauth. Audit `auth.session_expired` ;
  - une session authentifiée sans horodatage (créée avant le déploiement) est fermée de la même façon : échec fermé ;
  - `SESSION_COOKIE_AGE=43200` reste la borne du cookie et de la ligne en base. Le middleware ne dépend pas des structures internes d'allauth.
- **Pas d'expiration glissante supplémentaire** (`SESSION_SAVE_EVERY_REQUEST` reste à `False`), qui écrirait en base à chaque requête.
- **Pas de « se souvenir de moi ».** `ACCOUNT_SESSION_REMEMBER` est **sans effet en *headless***. La vue de connexion n'appelle pas `set_expiry`, et le cookie garde `max-age=43200` (vérifié par essai). On règle donc `SESSION_EXPIRE_AT_BROWSER_CLOSE=True` (réglage Django) : le cookie n'a plus de date, et la limite de 12 h reste appliquée côté serveur. Certains navigateurs restaurent les cookies de session au redémarrage : c'est précisément pourquoi la limite serveur est nécessaire.
- **Réauthentification récente, de moins de 5 min** (`ACCOUNT_REAUTHENTICATION_TIMEOUT`, 300 s par défaut, vérifié), pour :
  - l'export de ses données et l'anonymisation de son compte ;
  - la révocation d'un rôle et l'invitation d'un `ADMIN` ou d'un `CHAIR` ;
  - la publication ou l'archivage de l'édition, et la modification de la confidentialité ;
  - **la gestion des adresses e-mail** (ajout, suppression, choix de l'adresse principale) et **la liaison d'une adresse invitée** (RG-20, §5.7). Ajouté en v3.

  **Ce qu'allauth impose, et ce qu'il n'impose pas (corrigé en v3).** La v2 affirmait qu'allauth exige déjà une réauthentification pour le mot de passe, les adresses e-mail et la 2FA. C'est vrai seulement pour la 2FA : activation et désactivation du TOTP, codes de secours (vérifié). Pour les adresses, allauth ne l'exige que si `ACCOUNT_REAUTHENTICATION_REQUIRED` vaut `True`, alors que la valeur par défaut est `False` (vérifié) : le plan active ce réglage (§4.2). Le changement de mot de passe, lui, exige l'ancien mot de passe, ce qui protège au moins autant (vérifié).

  **Pourquoi c'est important.** Sans ce réglage, une session volée d'un compte sans 2FA (auteur, relecteur) suffit pour ajouter une adresse de l'attaquant, sans connaître le mot de passe. `password/request` envoie ensuite le lien de réinitialisation à cette adresse, même non vérifiée (vérifié par essai). L'attaquant obtient ainsi une prise de contrôle durable, au-delà des 12 h de la session (§4.11). D'où aussi deux défenses en profondeur : la notification de tout ajout d'adresse à l'adresse principale, et aucune réinitialisation vers une adresse secondaire non vérifiée (§4.2).

### D13. Saisie des échéances

**Recommandation.**
- L'API accepte `at_local` : date et heure **sans fuseau**, interprétées dans le fuseau de l'édition par le serveur avec `zoneinfo` et `tzdata` (paquet pur Python, licence **à vérifier**).
- `at` est stocké en UTC ; l'API renvoie `at` et `at_local`.
- Une heure inexistante ou ambiguë au changement d'heure renvoie une erreur.
- Clôture proposée à **23 h 59, heure de l'édition**, sans AoE (B15). Le fuseau est affiché à côté de la date.

**Pourquoi.** Angular n'a besoin d'aucune bibliothèque de fuseaux, et la règle de conversion n'existe qu'à un seul endroit.

**Écart à valider.** `CLAUDE.md` dit « conversion en fuseau de l'édition côté interface ». Ici, l'affichage reste converti dans le navigateur (`Intl.DateTimeFormat`), mais la saisie est convertie côté serveur.

### D14. Contenus bilingues

**Recommandation.**
- Des colonnes `_fr` / `_en` pour tous les libellés éditoriaux paramétrés, comme `track.name_fr/en` dans §8.2. Cela corrige l'incohérence relevée en B13.
- Le français est obligatoire. L'anglais est facultatif en brouillon, mais **obligatoire pour publier** l'édition.
- Aucune dépendance de traduction de modèles. Une troisième langue demanderait une migration (Q6).

### D15. Données personnelles

**À fournir par vous (Q14) :**
- le cadre légal : loi ivoirienne 2013-450 (ARTCI), RGPD, ou les deux ;
- la compatibilité avec un hébergement en France ;
- le texte de la notice d'information ;
- les durées de conservation.

Une notice « v0 » provisoire sert aux démos. Le texte définitif bloque l'ouverture de l'appel (L3), pas L1.

**Recommandations.**
- **Notice d'information** affichée à l'inscription. Sa prise de connaissance est enregistrée à la première connexion. Ce n'est pas un consentement : le compte repose sur l'exécution du service, ce qui reste **à confirmer** avec le cadre retenu.
- **Consentements facultatifs** (`directory_listing`, utilisé en L2) : désactivés par défaut, retirables.
- **Anonymisation immédiate** après réauthentification et phrase de confirmation. Elle est refusée si la personne détient un rôle actif autre qu'`AUTHOR` ou `ATTENDEE` dans une édition non archivée : elle doit d'abord transmettre ses responsabilités. Un délai de grâce de 7 jours, annulable, est possible en option (+0,5 j-h).
- **Journal d'audit conservé** après anonymisation (intérêt légitime). Il ne contient que des identifiants, qui deviennent pseudonymes, et jamais l'adresse en clair (§7.2).
- **Durées proposées par défaut**, modifiables par constantes. Les purges qui en dépendent tournent en simulation (`--dry-run`) tant que vous ne les avez pas validées.

| Donnée | Durée proposée |
|---|---|
| Corps des e-mails contenant un lien à jeton | Purgés dès l'envoi (au plus 24 h en cas d'échec) |
| Autres corps d'e-mails / métadonnées d'envoi | 30 jours / 12 mois (adresse et objet remplacés dès l'anonymisation du compte) |
| IP et user-agent dans l'audit et les consentements | 6 mois |
| Lignes du journal d'audit | 3 ans |
| Invitations expirées, refusées ou annulées | Adresse et message effacés après 12 mois (immédiatement à l'anonymisation du compte). Invitations acceptées : adresse conservée tant que le compte existe, effacée à son anonymisation (§4.9) |
| Sessions | 12 h au plus ; supprimées à l'anonymisation |
| Tâches terminées | 30 jours |

### D16. Anti-robots

**Recommandation.** Ne pas l'intégrer en L1, qui n'est pas ouvert au public. La CSP actuelle (`frame-src 'none'`, scripts à empreintes) bloquerait d'ailleurs les fournisseurs, qui sont des tiers recevant des données. En L1, on compense par :
- la vérification d'e-mail obligatoire ;
- la limitation de débit ;
- l'anti-énumération, y compris par le temps de réponse (§4.11) ;
- un plafond global d'envoi d'e-mails.

Le fournisseur sera choisi avant l'ouverture de l'appel (L3).

### D17. Remontée des erreurs

**Options.**
- **Sentry ou équivalent** : transfère à un tiers des données qui peuvent être personnelles.
- **E-mail minimal aux opérateurs** : type d'exception, chemin, identifiant de requête, sans corps, en-têtes ni cookies, limité à N par heure.

**Recommandation : l'e-mail minimal.** Le gestionnaire standard de Django (`AdminEmailHandler`) joint le détail de la requête : il n'est pas utilisé tel quel. Le mécanisme exact sera précisé en L1.2. Sentry est reporté en L9, sur décision.

### D18. Périmètre, charge, repli et exploitation

**Périmètre et charge.** Recommandation : **ce plan, 22,75 à 28 j-h**, avec les reports du §1.3.
- La v1 annonçait 19 à 23 j-h. La relecture a montré que les écrans (L1.4 et L1.7) étaient sous-estimés : environ 0,25 j-h par écran, tests et i18n compris, alors que l'étude attribue 30 à 35 % de la charge aux écrans qui remplacent l'admin (§14.3). Ils sont réestimés à 4–5 j-h chacun. Les corrections de sécurité de la v2 ajoutent environ 1,5 j-h, celles de la v3 environ 0,5 j-h (§13).
- **Variante courte, d'environ 20,5 à 25,75 j-h : scénario de repli décidé d'avance.** Ses trois réductions (§13) s'appliquent **sans nouvelle décision** si J-tech n'est pas atteint à j7, ou la démo A à j15. Votre accord sur cette règle est demandé dès maintenant. La 2FA, la matrice des droits et le verrouillage des dépendances ne sont jamais réduits.

**Déploiement : écart de périmètre à valider.**
- L'étude (§14.1) place « CI/CD » dans L1. Ce plan livre l'**intégration continue** : tests, contrôles, build et artefact. Il **sort de L1 le déploiement continu** (CD).
- Pourquoi : il faudrait stocker une clé SSH de production chez GitHub, et l'acceptation par o2switch du SSH depuis les IP dynamiques des runners n'est **pas vérifiée**.
- En L1, on garde le `deploy.sh` manuel, corrigé (§11) : aucune clé SSH de production n'est stockée sur GitHub.
- **Lot de destination proposé :** une étape dédiée **avant l'ouverture de l'appel (L3)**, idéalement en tête de L2. À partir de L3, des déploiements fréquents touchent des données réelles, et un déploiement reproductible devient nécessaire. La forme serait un job `workflow_dispatch` avec environnement protégé et clé restreinte par `authorized_keys`, pour environ 0,5 à 1 j-h (estimation **à confirmer** après la vérification SSH).
- Cet écart est inscrit dans les mises à jour de l'étude (§15, point 15).

**Recette.** Second dossier ou sous-domaine, marqué `noindex`, sans donnée réelle. **À vérifier** sur o2switch (§11.2).

**Sauvegardes.** **Aucune donnée réelle** (vrais membres du comité) avant une sauvegarde et une restauration testées sur o2switch. `mysqldump` et les sauvegardes cPanel ne sont pas vérifiés. Si vous souhaitez inviter le vrai comité pendant L1, ce travail entre en L1 (+0,5 à 1 j-h).

---

## 3. Modèle de données

### 3.1 Conventions et contraintes MariaDB (et pourquoi)

**Clés et héritage.**
- Toutes les tables métier ont une clé primaire BIGINT et héritent de `TimeStampedModel` (`created_at`, `updated_at`).
- Exception : les tables en ajout seul (`AuditLog`, `Consent`) n'ont pas de `updated_at`. Leurs seules modifications passent par des méthodes nommées et auditées (§7.1).

**Clés étrangères en `on_delete=RESTRICT`.** Une donnée personnelle n'est jamais supprimée physiquement : elle est anonymisée. Les éditions sont archivées, jamais supprimées. C'est ce qui garantit la traçabilité.

**Tables tierces : exceptions documentées.**
- `account_emailaddress` et `mfa_authenticator` (allauth) ont une clé INT et des FK en CASCADE. On les supprime explicitement à l'anonymisation.
- Il **ne faut pas** définir `ALLAUTH_DEFAULT_AUTO_FIELD` : `makemigrations --check` réclamerait alors une migration dans site-packages, et la CI échouerait (vérifié).

**Pas d'unicité conditionnelle (`UniqueConstraint(condition=…)`).** MariaDB ne la supporte pas. Django émet l'avertissement W036 et ne crée **pas** la contrainte (vérifié), alors qu'elle s'applique sous SQLite : les tests locaux passeraient à tort. On utilise à la place la **« clé d'unicité nullable »** :
- une colonne `CharField(null=True, unique=True)` reçoit une valeur seulement quand l'unicité doit s'appliquer, et vaut NULL sinon ;
- MariaDB considère les NULL comme distincts, donc les lignes à NULL ne se gênent pas ;
- c'est la seule exception justifiée (`# noqa: DJ001`) à la règle ruff qui interdit les `CharField` nullables ;
- un méta-test interdit `UniqueConstraint(condition=…)` dans `apps/`.

**Clés de longueur fixe.** Une clé composée de valeurs saisies (adresse e-mail de 254 caractères au plus, identifiants…) n'est jamais stockée telle quelle. On stocke son **empreinte SHA-256** en hexadécimal (`Char(64)`). La longueur est fixe, ce qui évite deux écueils, selon le `sql_mode` de MariaDB, que nous ne connaissons pas encore (à vérifier en L1.0) :
- en mode strict, l'erreur 1406 « données trop longues », donc une 500 ;
- sinon, une troncature silencieuse, qui ferait entrer deux clés différentes en collision.

**À l'inverse, pas de NULL dans une unicité composite.** Comme les NULL sont distincts, un index unique contenant une colonne NULL ne protège rien. D'où `oc_function` en NOT NULL, avec `""` par défaut.

**Contraintes `CHECK`.** MariaDB les gère (vérifié). Un test en CI vérifie leur présence réelle par introspection (`SHOW CREATE TABLE`).

**Texte et JSON.**
- Les champs texte ne sont jamais nullables (`blank=True, default=""`).
- Le JSON (`longtext` avec `CHECK (json_valid)`) est réservé aux données qu'on n'interroge pas (§8.3).

**Énumérations.** Ce sont des `TextChoices`, aux valeurs en anglais. Chaque **jeu de choix** exposé par l'API reçoit une entrée `ENUM_NAME_OVERRIDES`, et un méta-test le vérifie (§9.5). Voici pourquoi.
- Dès qu'un second champ `status` aux choix différents apparaît, par exemple `UserRole.status`, drf-spectacular renomme `StatusEnum` en `HealthStatusEnum` **sans avertissement**. Le code de sortie reste 0 même avec `--fail-on-warn` (vérifié par essai), et le type TypeScript `StatusEnum` disparaît du client généré.
- Deux autres cas produisent un avertissement, donc un échec de la CI avec `--fail-on-warn` (lu dans `drf_spectacular/hooks.py:93-110` ; précisé en v3) :
  - « collision » : un même nom de champ porte plusieurs jeux de choix, et l'un d'eux sert dans plusieurs composants. Exemple prévisible : `role`, restreint aux 5 rôles invitables dans le sérialiseur d'invitation, mais complet dans la liste des rôles et dans `/me` ;
  - « plusieurs noms pour un même jeu » : deux champs de noms différents partagent le même jeu de choix. Exemple constaté par essai : `cache` (`ok`, `error`), ajouté à `/health` au §8.4, à côté de `database`, qui a les mêmes valeurs.
- Une surcharge s'applique à un jeu de choix, pas à un champ (vérifié) : `database` et `cache` reçoivent donc une surcharge commune, `ServiceStatus`.
- `StatusEnum` et `DatabaseEnum` ne sont importés aujourd'hui que par le client généré, pas par du code écrit à la main (vérifié). Les renommer en `HealthStatus` et `ServiceStatus` ne coûte donc rien maintenant, et coûterait plus tard.

**Dates.** En UTC (voir D13).

### 3.2 Applications et sens des dépendances

```text
core            TimeStampedModel, Actor, DomainError, audit, Job, LockedCommand, battement de cœur
accounts        User, Profile, Consent, UserRole, RoleInvitation, rôles → capacités, adaptateurs allauth,
                expiration absolue des sessions
conferences     Conference, Edition, Track, SubmissionType, KeyDate
communications  OutboxEmail (en L3 : modèles d'e-mails, notifications)
```

Une application n'importe d'une autre que ses `services` et ses modèles, en lecture. Elle n'importe jamais ses vues ni ses sérialiseurs. Les clés étrangères entre applications sont déclarées par chaîne.

### 3.3 Application `accounts`

**`User`** : table existante, migration `0001` **intacte**. On ajoute en `0002` :

| Champ | Type | Remarque |
|---|---|---|
| `anonymized_at` | DateTime, null | Marque l'anonymisation (M2, RG-18). Le compte ne peut plus se connecter |

Le champ existant `locale` (défaut `fr`, modèle L0) est désormais **initialisé à l'inscription** avec la langue de la requête (§4.3).

Écarts avec §8.2 :
- **pas d'`email_verified_at` ni de `totp_enabled`**, qui doublonnent `EmailAddress.verified` et `mfa_authenticator` (B1). `/me` les calcule, et l'horodatage de la vérification figure dans l'audit ;
- **`User` n'a pas `PermissionsMixin`** : `has_perm` n'existe pas. `DjangoModelPermissions` et `has_perm` sont donc interdits, et un méta-test le vérifie.

**`Profile`** (nouvelle)

| Champ | Type | Contraintes |
|---|---|---|
| `user` | OneToOne → User, clé primaire | RESTRICT |
| `title` | Char(8) : `""`, `dr`, `pr`, `mr`, `ms` | Le « titre » de M2 remplace la `civility` de §8.2 (C1). Liste à valider |
| `first_name`, `last_name` | Char(150) | Index (`last_name`, `first_name`) |
| `institution`, `department` | Char(255) | — |
| `country` | Char(2) | ISO 3166-1 alpha-2, validé contre une liste versionnée (utile pour le tarif en L6) |
| `orcid` | Char(19) | Format `0000-0000-0000-000X` et clé ISO 7064 MOD 11-2. Indexé, non unique |
| `bio` | Text | 2 000 caractères au plus, texte brut. Aucun assainisseur HTML nécessaire en L1 |

Une propriété `is_complete` (nom, prénom, institution, pays) alimente `profile_complete` dans `/me` dès L1, et servira de prérequis en L3. Le profil est créé à la première écriture : son absence signifie « profil incomplet ».

**`Consent`** (nouvelle, en ajout seul : mêmes protections que le journal d'audit, deux exceptions nommées, §7.1)

| Champ | Type | Contraintes |
|---|---|---|
| `user` | FK → User | RESTRICT |
| `kind` | Char(32) | `privacy_notice` (prise de connaissance) et `directory_listing`. L2 ajoutera `photo_publication`, L3 les consentements de publication |
| `granted` | Bool | Un retrait est une nouvelle ligne à `False` |
| `text_version` | Char(32) | Version du texte présenté. Les textes sont versionnés dans le dépôt, en FR et EN |
| `recorded_at` | DateTime | — |
| `source` | Char(16) | `first_login`, `account`, `command` |
| `ip` | GenericIP, null | Preuve. Effacée selon D15 et à l'anonymisation, uniquement par `purge_network_before(date)` et `redact_network_for_user(user)` |

- **Index :** (`user`, `kind`, `recorded_at`).
- **État courant :** la dernière ligne de chaque (`user`, `kind`).
- **Pas de colonne `edition` en L1** : les consentements propres à une édition n'apparaissent qu'en L3, qui l'ajoutera par une migration additive (§1.3).
- **Écart avec §8.2** (`consent_directory`, `consent_at`) : un seul champ ne permet pas d'avoir plusieurs consentements, leur retrait et la version du texte (B10).

**`UserRole`** (nouvelle)

| Champ | Type | Contraintes |
|---|---|---|
| `user` | FK → User | RESTRICT |
| `edition` | FK → Edition | RESTRICT |
| `role` | Char(16), `Role` | Les 11 rôles de §3.2 : `ADMIN`, `CHAIR`, `OC_MEMBER`, `SC_CHAIR`, `SC_MEMBER`, `AUTHOR`, `SPEAKER`, `SESSION_CHAIR`, `ATTENDEE`, `SPONSOR`, `VOLUNTEER` |
| `oc_function` | Char(32), défaut `""` | CHECK : non vide si et seulement si `role = OC_MEMBER` (D8) |
| `status` | Char(8) : `active`, `revoked` | Seul `active` donne des droits |
| `source` | Char(16) : `invitation`, `command`, `system` | — |
| `granted_at`, `granted_by` | DateTime, FK → User null | `granted_by` null = commande ou système |
| `revoked_at`, `revoked_by`, `revoke_reason` | DateTime null, FK null, Text | Motif obligatoire |
| `invitation` | FK → RoleInvitation, null | Traçabilité |

- **Unicité :** (`user`, `edition`, `role`, `oc_function`). Elle est réelle sur MariaDB, puisqu'aucune colonne n'est NULL.
- **Index :** (`edition`, `role`, `status`) et (`user`, `status`).
- **Réattribution après révocation :** la même ligne est réactivée. L'historique est dans l'audit, qui tient lieu d'historisation (§8.3).

**`RoleInvitation`** (nouvelle)

| Champ | Type | Contraintes |
|---|---|---|
| `edition` | FK → Edition | RESTRICT |
| `email` | Email(254) | Normalisé en minuscules, comme `UserManager`. **Exclu des `AUDIT_FIELDS`** : l'audit ne garde que l'adresse masquée (§7.2). Effacé à l'anonymisation du destinataire (§4.9) |
| `role`, `oc_function` | Comme `UserRole` | Même CHECK. Rôles invitables en L1 : `ADMIN`, `CHAIR`, `SC_CHAIR`, `OC_MEMBER`, `SC_MEMBER` |
| `token_hash` | Char(64), unique | SHA-256 d'un jeton `secrets.token_urlsafe(32)`. **Le jeton en clair n'est jamais stocké** |
| `status` | Char(12) : `pending`, `accepted`, `declined`, `cancelled`, `expired` | Modifié uniquement par le service |
| `pending_key` | Char(64), **null, unique** | `sha256(f"{edition_id}:{email}:{role}:{oc_function}")` en hexadécimal tant que l'invitation est en attente, NULL ensuite. **La base garantit une seule invitation en attente**, sans verrou applicatif et quelle que soit la longueur de l'adresse |
| `invited_by` | FK → User, null | RESTRICT. Null quand l'invitation est créée par commande (`create_edition --admin-email`), comme `UserRole.granted_by` (cohérence corrigée en v3) |
| `expires_at` | DateTime | 14 jours par défaut |
| `locale` | Char(8) | Langue de l'e-mail |
| `message` | Text | 1 000 caractères au plus, texte brut. Vidé à l'anonymisation du destinataire ou de l'invitant, et 12 mois après une invitation expirée, refusée ou annulée (§4.9, D15) |
| `send_count`, `last_sent_at` | SmallInt, DateTime | Renvois limités |
| `responded_at`, `accepted_by` | DateTime null, FK → User null | RESTRICT |

**Index :** (`edition`, `status`), (`email`, `status`) et (`invited_by`, `created_at`), ce dernier pour le quota d'invitations (§4.7).

**Expiration à la volée.** Sans précaution, une invitation échue garderait sa `pending_key` jusqu'au passage quotidien de `cleanup`, et bloquerait pendant 24 h au plus une nouvelle invitation légitime. Le service de création commence donc par passer en `expired`, avec `pending_key` à NULL, les invitations en attente échues qui ont la même clé, dans la même transaction et avec audit `invitation.expired`.

### 3.4 Application `conferences` (nouvelle)

**`Conference`** : créée par commande (D1).
- `slug` unique ;
- `name_fr`, `name_en` ;
- `description_fr`, `description_en`, en texte brut ;
- `current_edition` : FK → Edition, null, RESTRICT, ajoutée en `0002` pour rompre la dépendance circulaire.

Désigner l'édition courante par une clé étrangère évite une unicité conditionnelle (« une seule édition courante »), impossible sur MariaDB.

**`Edition`**

| Champ | Type | Contraintes |
|---|---|---|
| `conference` | FK | RESTRICT |
| `code` | Char(12), unique | `^[A-Z][A-Z0-9]{1,11}$`, par exemple `GC26`. Préfixe des références en L3 |
| `slug` | Slug | Unique avec `conference` |
| `year` | PositiveSmallInt | — |
| `title_fr`/`_en`, `theme_fr`/`_en` | Char(255) / Char(500) | EN obligatoire pour publier (D14) |
| `start_date`, `end_date` | Date | CHECK `end_date >= start_date` |
| `venue`, `city` | Char(255), Char(128) | — |
| `country` | Char(2) | ISO |
| `timezone` | Char(64) | Validé par `zoneinfo`. Défaut proposé : `Africa/Abidjan` |
| `double_blind` | Bool | Défaut `True` (§15.2) |
| `reviewers_per_submission` | PositiveSmallInt | Défaut 2, CHECK entre 1 et 10 |
| `status` | Char(10) : `draft`, `published`, `archived` | Transitions par un service unique (§6.3). Les valeurs sont absentes de §8.2 (B12) |
| `published_at`, `archived_at` | DateTime, null | — |

**Index :** (`conference`, `status`).

Les autres paramètres sont ajoutés **en colonnes typées dans leur lot** : langues des soumissions (L3), seuils et charge maximale (L4), devise (L6), conservation (L3 ou L8). On n'utilise pas de table générique clé-valeur, qui ne serait ni typée, ni validée, ni lisible dans le schéma OpenAPI.

**`Track`, `SubmissionType`, `KeyDate`**

| Entité | Champs | Contraintes |
|---|---|---|
| `Track` | `edition` (FK RESTRICT), `code` (Slug 32), `name_fr/en` (Char 255), `description_fr/en` (Text), `position`, `is_active` | Unicité (`edition`, `code`). Index (`edition`, `position`). Pas de `chair_user` en L1 : aucun rôle ni droit n'est défini (B5) |
| `SubmissionType` | `edition`, `code` (`oral`, `poster`, `workshop`, `symposium`, `panel`…), `label_fr/en`, `description_fr/en`, `default_duration_min` (null, pour les posters), `abstract_max_words` (défaut 300), `position`, `is_active` | Unicité (`edition`, `code`). CHECK sur le nombre de mots, entre 50 et 2 000. Formats, taille et article complet viendront en L3 (Q5) |
| `KeyDate` | `edition`, `code` (Slug 32), `at` (UTC), `label_fr/en` (obligatoires pour un code libre), `is_public` (défaut `True`), `position` | Unicité (`edition`, `code`). Index (`edition`, `at`) |

**Codes réservés de `KeyDate`.** Le code métier connaît leur signification :
- `call_open`, `call_close` ;
- `review_deadline` (absent des exemples de §8.2, B15) ;
- `notification`, `camera_ready` ;
- `registration_open`, `early_bird_end`, `registration_close`.

Les autres codes sont libres, pour affichage seulement.

**Ordre contrôlé :**
- `call_open < call_close ≤ review_deadline ≤ notification ≤ camera_ready` ;
- `registration_open < early_bird_end ≤ registration_close`.

**Suppression.** Un track ou un type utilisé ne se supprime pas (409 `in_use` à partir de L3) : on le désactive.

### 3.5 Application `core`

**`AuditLog`** : en ajout seul. Détail du service au §7.

| Champ | Type | Remarque |
|---|---|---|
| `at` | DateTime (UTC), indexé | — |
| `actor` | FK → User, null, RESTRICT | Null = système. Après anonymisation, pointe vers le compte anonymisé |
| `actor_kind` | Char(8) : `user`, `command`, `system` | — |
| `actor_label` | Char(64) | **Seulement** pour les commandes et les tâches, par exemple `cli:<utilisateur système>` ou `job:email.send`. Jamais l'e-mail d'un utilisateur, qui survivrait à l'anonymisation |
| `edition` | FK → Edition, null, RESTRICT | Ajout par rapport à §8.2 (B8) : permet de limiter la lecture d'un président à son édition |
| `action` | Char(64) | Code `domaine.verbe`, par exemple `role.revoked` |
| `object_type`, `object_id` | Char(64) | — |
| `before`, `after` | JSON, null | **Liste blanche** de champs par modèle. Jamais de mot de passe, de secret TOTP, de jeton, d'adresse e-mail en clair ni de donnée de profil |
| `reason` | Text | Motif : obligatoire pour les révocations, les commandes sensibles et, en L3, les dérogations (RG-02) |
| `request_id` | Char(32) | Corrélation avec les journaux du serveur |
| `ip`, `user_agent` | GenericIP null, Char(255) | Purgés après la durée fixée en D15 |

**Index :** (`edition`, `at`), (`actor`, `at`), (`object_type`, `object_id`), (`action`, `at`).

**`Job`**

| Champ | Type | Contraintes |
|---|---|---|
| `kind` | Char(64) | Clé du registre `@register_job("…")` |
| `payload` | JSON | Identifiants et scalaires seulement, **jamais de secret** |
| `status` | Char(10) : `pending`, `running`, `succeeded`, `failed`, `cancelled` | — |
| `priority` | SmallInt | 0 pour les e-mails de sécurité et ceux de la voie rapide, 100 par défaut, 200 pour les envois de masse. Ne sert qu'à ordonner le cron : la voie rapide est choisie par gabarit, pas par priorité (§8.3) |
| `run_at` | DateTime | — |
| `attempts`, `max_attempts` | SmallInt | 0 et 5 |
| `locked_at`, `locked_by` | DateTime null, Char(64) (`hôte:pid`) | — |
| `finished_at` | DateTime null | — |
| `last_error` | Text | Tronqué à 2 000 caractères, sans donnée personnelle ni secret |
| `dedup_key` | Char(128), **null, unique** | Clé d'idempotence facultative, construite par le code (jamais à partir d'une adresse) |
| `edition` | FK → Edition, null | — |

**Index :** (`status`, `priority`, `run_at`).

**`CronHeartbeat`** : `name` (unique), `last_started_at`, `last_finished_at`, `last_status`, `last_duration_ms`, `processed_count`.

**Table de cache `gestconf_cache`.** Elle est créée par `createcachetable`, pas par une migration. Son fonctionnement a une conséquence de sécurité (vérifié dans le code de Django) :
- chaque écriture (`set`, `add`) commence par un `SELECT COUNT(*)` ;
- au-delà de `MAX_ENTRIES` entrées, Django supprime d'abord les entrées expirées. S'il en reste trop, il supprime **un tiers des clés restantes par ordre alphabétique**, sans distinguer leur rôle.

Un attaquant qui multiplie les clés (adresses différentes pour `reset_password`, nombreuses IP) pourrait ainsi faire disparaître des compteurs de limitation de débit ou des clés anti-rejeu TOTP. D'où trois mesures :
- `MAX_ENTRIES=50000`. La valeur par défaut de 300 purgerait les compteurs en usage normal, et 10 000 (v1) laisse peu de marge. Le coût du `COUNT(*)` dépend du nombre réel de lignes, pas de ce plafond ;
- une purge des entrées expirées à chaque passage de `run_jobs` (§8.2), qui garde la table petite ;
- une alerte de `check_integrity` au-delà de 20 000 entrées (§8.4).

Le risque résiduel est documenté au §4.11 (R18).

### 3.6 Application `communications` (nouvelle, réduite en L1)

**`OutboxEmail`**

| Champ | Type | Contraintes |
|---|---|---|
| `to_email` | Email | Remplacé par l'adresse anonymisée à l'anonymisation du destinataire (§4.9) |
| `to_user`, `edition` | FK, null | RESTRICT |
| `template_code` | Char(64) | Par exemple `account.email_confirmation`, `role.invitation` |
| `locale` | Char(8) | — |
| `subject`, `body_text`, `body_html` | Char(255), Text, Text | **Rendus pendant la requête** : hors requête (cron), allauth ne sait pas construire les URL (vérifié). L'objet ne contient aucune donnée de personne (règle des gabarits, §8.3) ; il est remplacé par `[anonymisé]` à l'anonymisation du destinataire (§4.9) |
| `is_sensitive` | Bool | Vrai pour les liens de vérification, de réinitialisation, d'invitation et de liaison d'adresse. **Corps purgé dès l'envoi** |
| `status` | Char(10) : `queued`, `sending`, `sent`, `failed`, `cancelled` | — |
| `attempts`, `last_error` | — | — |
| `scheduled_at`, `sent_at`, `purged_at` | DateTime | — |
| `provider_message_id` | Char(255) | — |
| `idempotency_key` | Char(128), null, unique | — |

**Index :** (`status`, `scheduled_at`), (`to_user`, `created_at`), (`to_email`), ce dernier pour l'anonymisation des envois sans compte.

**Pourquoi purger.** Sinon, un simple accès en lecture à la base suffirait pour réinitialiser des mots de passe ou accepter des invitations.

### 3.7 Écarts avec §8 (récapitulatif)

| §8.2 / §8.3 | Ce plan | Raison |
|---|---|---|
| `user.email_verified_at`, `totp_enabled` | Retirés ; ajout de `anonymized_at` | Doublons avec les tables allauth (B1) ; RG-18 |
| `profile.civility`, `photo`, `expertise_keywords` (JSON), `consent_directory`, `consent_at` | `title` ; photo en L2 ; expertises en L4, en relationnel ; table `consent` (colonne `edition` en L3) | M2 ; B11 ; §8.3 (le JSON n'est pas fait pour une donnée interrogée) ; B10 |
| `user_role.status` = invited, active, declined ; unicité (user, edition, role) | `active`/`revoked` + table `role_invitation` ; unicité incluant `oc_function` | D6 ; NULL distincts sous MariaDB |
| `edition` sans code, statut non défini, monolingue | `code`, `slug`, statuts définis, `_fr`/`_en`, `conference.current_edition` | B12, B13, « édition courante » |
| `track.chair_user_id` | Reporté | B5 |
| `key_date.label` | `label_fr/en`, `is_public`, `position`, code `review_deadline` | B13, B15 |
| `audit_log` | Ajout de `edition`, `actor_kind`, `actor_label`, `reason`, `request_id`, `user_agent` | B8 |
| `job` | Ajout de `priority`, `max_attempts`, `finished_at`, `locked_by`, `dedup_key`, `edition` | C3 |
| `outbox_email` (`template`, `context`) | Contenu rendu dans la requête, `locale`, `edition`, `is_sensitive`, purge, `idempotency_key` | C2 ; jetons à protéger ; pas de requête HTTP dans le cron |
| `email_template`, `notification`, compteurs | Reportés en L3 | §1.3 |
| BIGINT partout, RESTRICT par défaut | Sauf les tables d'allauth (INT, CASCADE) | Imposé par la bibliothèque (C7), piège de migration vérifié |

### 3.8 Stratégie de migration

**Principes.**
- `accounts/0001` reste **intact**.
- Toutes les migrations sont **additives** : chaque colonne nouvelle est nullable ou a une valeur par défaut, rien n'est supprimé en L1.
- Une préoccupation par migration.

**Ordre, aligné sur les étapes du §13.** Les tables transverses (`core`, `communications`) sont créées en L1.2, **avant** l'application `conferences` (L1.5). Leurs FK vers `Edition` sont donc ajoutées dans une seconde migration. Les trois plans d'origine plaçaient cette FK dès `core/0001`, ce qui était incohérent avec leur propre ordre d'étapes.

| Étape | Migrations |
|---|---|
| L1.2 | `core/0001` (`AuditLog`, `Job`, `CronHeartbeat`, sans FK d'édition) ; `communications/0001` (`OutboxEmail`, sans FK d'édition) |
| L1.3 | `accounts/0002` (`anonymized_at`, `Profile`, `Consent`) ; migrations d'allauth `account` |
| L1.5 | `conferences/0001` ; `conferences/0002` (`current_edition`) ; `accounts/0003` (`UserRole`, `RoleInvitation`) ; `core/0002` et `communications/0002` (FK `edition`, nullables) |
| L1.6 | Migrations d'allauth `mfa` |
| L3 | `Consent.edition` (FK nullable), migration additive |

**Données existantes.** Aucune migration de données. La commande `sync_email_addresses --verified` crée les `EmailAddress(verified=True, primary=True)` des comptes créés par commande en L0, s'il y en a. Sans cette ligne, la connexion répond 401 avec le flux `verify_email` (vérifié). Les commandes de création la créent elles-mêmes.

**Déploiement.**
- Le DDL de MariaDB n'est pas transactionnel : `deploy.sh` sauvegarde la base avant `migrate`, dès qu'il existe des données réelles.
- Puis `createcachetable`.
- Les migrations sont testées dans les deux sens en CI, sur MariaDB 10.11, puis sur la version réelle d'o2switch dès qu'elle est connue.

**Avertissements W036.**
- `manage.py check` sans `--database` ne lance pas ces contrôles (vérifié, Django 5.2). Le `check --deploy --fail-level WARNING` de la CI n'est donc **pas** concerné, et il n'est pas nécessaire de les réduire au silence.
- Ils s'affichent en revanche pendant `migrate`. Les invariants qu'ils représentent sont testés sur MariaDB (§12.3).
- En L1.0, on lance une fois `check --database default` sur o2switch, pour lire l'avertissement `mysql.W002` (mode strict absent, §14.2).

---

## 4. Authentification et sécurité

### 4.1 Pourquoi allauth *headless* et des sessions

**Le choix de l'étude.** `CLAUDE.md` et §7.2 imposent des sessions et le CSRF, sans jeton dans le navigateur. La raison : un cookie `HttpOnly` n'est pas lisible par un script injecté, alors qu'un jeton en `localStorage` l'est.

**Ce qu'apporte allauth *headless*.** Il fournit les flux (inscription, vérification, réinitialisation, 2FA) en JSON pour une SPA, sur ce même mécanisme de session. Écrire ces flux à la main serait la principale source de failles.

**Ce qu'il faut ajouter :**
- un cache partagé ;
- un adaptateur qui met les e-mails en file, filtre leur contexte, initialise la langue, égalise le temps de l'inscription et chiffre le secret TOTP ;
- une permission DRF qui impose la 2FA ;
- un middleware d'expiration absolue des sessions ;
- la réauthentification pour la gestion des adresses, et une notification à chaque ajout d'adresse : allauth n'impose ni l'une ni l'autre par défaut (ajouté en v3) ;
- un contrôle CSRF qui renvoie le bon code d'erreur sous DRF.

### 4.2 Configuration (`config/settings/base.py`)

Réglages validés par les essais (vérifié), sauf mention contraire.

**Applications et middleware.**
- `INSTALLED_APPS` : ajouter `allauth`, `allauth.account`, `allauth.headless` et `allauth.mfa` (L1.6), placées **après** les applications du projet pour que les gabarits du projet priment.
- `MIDDLEWARE` :
  - `LocaleMiddleware`, après `SessionMiddleware` et avant `CommonMiddleware` ;
  - `apps.accounts.middleware.AbsoluteSessionTimeoutMiddleware`, juste après `AuthenticationMiddleware` (D12) ;
  - `allauth.account.middleware.AccountMiddleware`, obligatoire, en fin de liste.
- `AUTHENTICATION_BACKENDS = ["allauth.account.auth_backends.AuthenticationBackend"]`.

**Compte.**
- `ACCOUNT_LOGIN_METHODS={"email"}`.
- `ACCOUNT_SIGNUP_FIELDS=["email*","password1*"]` : la confirmation du mot de passe se fait dans Angular.
- `ACCOUNT_USER_MODEL_USERNAME_FIELD=None`.
- `ACCOUNT_EMAIL_VERIFICATION="mandatory"`, en mode **lien** : `ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED` reste à `False`, la valeur par défaut. C'est l'option (a) de D6 ; l'option (b) le passerait à `True`.
- `ACCOUNT_PREVENT_ENUMERATION=True` (valeur par défaut).
- `ACCOUNT_EMAIL_NOTIFICATIONS=True` : alertes de sécurité. Faux par défaut (vérifié).
- `ACCOUNT_EMAIL_UNKNOWN_ACCOUNTS=False` (le réglage existe, défaut `True`, vérifié). Ainsi, la plateforme ne peut pas servir à envoyer des e-mails à des adresses quelconques, et la réponse reste identique. L'effet sur le temps de réponse est traité au §8.3.
- `ACCOUNT_LOGIN_BY_CODE_ENABLED=False` (valeur par défaut).
- `ACCOUNT_MAX_EMAIL_ADDRESSES=3` (défaut : illimité, vérifié). Cette limite vaut pour les adresses ajoutées par l'utilisateur. Le rattachement d'une adresse invitée (RG-20, §5.7) applique la même limite par `EmailAddress.objects.can_add_email` (vérifié).
- `ACCOUNT_CHANGE_EMAIL=False` (valeur par défaut, vérifié).
- **`ACCOUNT_REAUTHENTICATION_REQUIRED=True`** (défaut `False`, vérifié ; ajouté en v3). L'ajout et la suppression d'une adresse, ainsi que le choix de l'adresse principale, exigent alors une réauthentification récente ; sinon, allauth répond 401 avec le flux `reauthenticate` (vérifié par essai). Sans ce réglage, une session volée suffit pour ajouter une adresse, puis réinitialiser le mot de passe par elle (D12, §4.11). Test : `test_add_email_requires_recent_reauth`.
- `ACCOUNT_EMAIL_SUBJECT_PREFIX`.
- **`ACCOUNT_SESSION_REMEMBER` n'est pas utilisé** : il est sans effet en *headless* (vérifié par essai, D12).

**Sessions (D12).**
- `SESSION_COOKIE_AGE=43200` (12 h).
- `SESSION_EXPIRE_AT_BROWSER_CLOSE=True`.
- Limite absolue imposée par le middleware ci-dessus.

**Headless.**
- `HEADLESS_ONLY=True`.
- **`HEADLESS_CLIENTS=("browser",)`** : le client `app`, présent par défaut, utilise des jetons et des vues exemptées de CSRF.
- `HEADLESS_SERVE_SPECIFICATION=False` (valeur par défaut).
- `HEADLESS_FRONTEND_URLS` en URL **absolues**, construites à partir de `GESTCONF_PUBLIC_URL`, avec la clé dans le fragment : `…/compte/verifier-email#{key}`. Le marqueur est remplacé où qu'il soit dans l'URL, et une URL absolue n'est pas complétée avec l'en-tête `Host` (vérifié). Clés concernées : `account_confirm_email`, `account_reset_password`, `account_reset_password_from_key`, `account_signup`.

**MFA (L1.6).**
- `MFA_SUPPORTED_TYPES=["totp","recovery_codes"]`.
- `MFA_TRUST_ENABLED=False` (valeur par défaut).
- `MFA_ALLOW_UNVERIFIED_EMAIL=False` (valeur par défaut, vérifié). Le passer à `True` lèverait le blocage d'ajout d'adresse des comptes 2FA, mais aussi la garde qui empêche d'activer la 2FA avec une adresse non vérifiée (les deux contrôles lisent ce réglage, vérifié), et cela sans analyse de risque. **Le blocage est aussi levé par le mode « code »** (`ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED=True`), et cette fois sans affaiblir la garde : l'adresse n'est enregistrée qu'après la saisie du code, donc toujours vérifiée (vérifié : `mfa/signals.py:51-58`, `account/forms.py:559-567` ; essai sur un compte 2FA). C'est l'option (b) de D6. Avec l'option (a), recommandée, RG-20 passe par un lien de confirmation (§5.7).
- `MFA_TOTP_ISSUER` réglé selon Q15 : par défaut vide, l'hôte s'affiche alors dans l'application TOTP.
- `MFA_ADAPTER="apps.accounts.adapters.MFAAdapter"`.

**Cache, CSRF, langues.**
- `CACHES` : `DatabaseCache` (`gestconf_cache`, `MAX_ENTRIES=50000`, §3.5). **Obligatoire** : les limites de débit d'allauth et de DRF ainsi que l'anti-rejeu TOTP (`cache.add`) passent par le cache (vérifié). Avec le cache par défaut, propre à chaque processus Passenger, un code TOTP pourrait être rejoué sur un autre processus.
- `CSRF_FAILURE_VIEW="apps.core.views.csrf_failure"`, qui répond en JSON `{code:"csrf_failed"}` au lieu de la page HTML de Django constatée aujourd'hui. **Elle ne couvre que les vues protégées par le middleware CSRF, donc allauth.** Sous DRF, voir §4.6.
- `LOCALE_PATHS`.

**DRF et OpenAPI.**
- `REST_FRAMEWORK` : `apps.core.authentication.SessionAuthentication` (401 et `csrf_failed`) ; `ScopedRateThrottle` ; `NUM_PROXIES` selon la mesure faite en L1.0.
- `SPECTACULAR_SETTINGS` : `ENUM_NAME_OVERRIDES` et composant `ApiError`.

**Adaptateurs** (`apps/accounts/adapters.py`).
- **`AccountAdapter.send_mail`** :
  - construit d'abord un **contexte en liste blanche** de chaînes (§8.3), car allauth y place des objets de l'ORM et la requête (vérifié) ;
  - rend le message sous `translation.override(langue du destinataire)` : `User.locale` si l'adresse appartient à un compte, sinon la langue de la requête ;
  - le met en file (§8) au lieu de l'envoyer de façon synchrone (comportement actuel, vérifié) ;
  - **ne met pas en file la réinitialisation du mot de passe vers une adresse secondaire non vérifiée** (ajouté en v3). allauth l'enverrait (vérifié par essai) : une adresse ajoutée, même jamais vérifiée, suffirait alors pour reprendre le compte. La réponse de `password/request` reste identique, et cet e-mail n'emprunte jamais la voie rapide, donc l'écart de temps reste négligeable (§4.11). L'adresse d'inscription, même non vérifiée, reste servie, pour ne pas bloquer une personne qui n'a jamais validé son compte.

  Les notifications de sécurité (`send_notification_mail`) passent aussi par `send_mail` (vérifié). Les gabarits FR/EN surchargent `account/email/*` et `mfa/email/*` ; sinon on obtiendrait « Bonjour, c'est testserver ! ».
- **Récepteur du signal `email_added`** (allauth, branché dans `AccountsConfig.ready()` ; ajouté en v3). Il met en file un e-mail « une adresse a été ajoutée à votre compte » vers l'adresse principale, quand celle-ci est distincte de l'adresse ajoutée. allauth n'envoie aucune notification à l'ajout (vérifié). Le signal est émis à l'ajout en mode lien, et après la saisie du code en mode code (vérifié par essai). Gabarit du projet `account/email/email_added`, en FR/EN, avec le contexte en liste blanche : l'adresse ajoutée figure dans le corps, jamais dans l'objet. Le même gabarit sert à la liaison RG-20 (§5.7). Audit `account.email_added`. Test : `test_email_added_notifies_primary`.
- **`AccountAdapter.save_user`** pose `user.locale` à partir de `translation.get_language()`, fournie par `LocaleMiddleware` à partir de l'en-tête `Accept-Language` qu'envoie l'intercepteur. La valeur est ramenée à `fr` ou `en`. Ainsi, l'e-mail de vérification part dans la langue du visiteur.
- **`AccountAdapter.send_account_already_exists_mail`** calcule un hachage de mot de passe factice (`make_password` d'une valeur aléatoire) avant d'appeler l'implémentation d'allauth. Le chemin « compte existant » coûte alors autant que la création d'un compte (§4.3, §4.11). Le point d'appel a été lu dans le code ; le test de comptage des hachages confirmera la chaîne d'appel complète (L1.3).
- **`MFAAdapter.encrypt` / `decrypt`** : chiffrent le secret TOTP et les codes de secours avec `MultiFernet` (`cryptography`, aller-retour vérifié). La clé est dans `GESTCONF_MFA_ENCRYPTION_KEYS` (la première chiffre, toutes déchiffrent). La rotation (`MultiFernet.rotate`) est **à vérifier**.

**Adresse IP du client.** Une seule variable d'environnement, `GESTCONF_TRUSTED_PROXY_COUNT`, alimente `NUM_PROXIES` (DRF), `ALLAUTH_TRUSTED_PROXY_COUNT` et la fonction `core.http.client_ip()` utilisée par l'audit. Les trois restent ainsi cohérents. Sa valeur est mesurée en L1.0.

### 4.3 Flux

Préfixe des appels allauth : `/api/_allauth/browser/v1/`.

| Flux | Déroulement | Remarques |
|---|---|---|
| **Amorçage** | `GET auth/session` | Pose le cookie `csrftoken` (vérifié). Répond 401 si l'utilisateur n'est pas connecté : c'est un état normal, pas une erreur (§10.1). Appelé au démarrage de la gestion et, dans le portail, dans `afterNextRender` |
| **Inscription** | `POST auth/signup {email, password}` | Crée le compte avec une adresse non vérifiée. La langue de la requête est enregistrée dans `User.locale` (§4.2). L'e-mail de vérification est mis en file, et la réponse est 401 avec le flux `verify_email`. Si l'adresse existe déjà, allauth envoie un e-mail « compte existant » (vérifié). **Réponse identique dans les deux cas** (vérifié par essai : 401). **Temps de réponse très différent** sans parade : environ 750 ms pour une adresse nouvelle, 8 ms pour une adresse existante (vérifié par essai), car seul le nouveau compte est haché. Parade : hachage factice dans le chemin « compte existant » (§4.2), testé par comptage. Audit `account.signed_up` |
| **Vérification de l'e-mail** | Lien `/compte/verifier-email#<clé>`, puis `POST auth/email/verify {key}` | **Renvoi du lien.** En mode lien, `auth/email/verify/resend` répond 409 : il ne sert qu'au mode « code » (vérifié par essai). Le lien est renvoyé quand la personne **se reconnecte** (`POST auth/login`), au plus une fois toutes les 180 s par adresse (vérifié par essai). L'écran « consultez vos e-mails » propose donc « renvoyer » sous la forme d'un formulaire de connexion. `ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION` est faux par défaut (vérifié). Le comportement quand une connexion est en attente dans la même session est **à vérifier par test**. Audit `account.email_confirmed` |
| **Connexion** | `POST auth/login` → 200, ou 401 avec le flux `verify_email` ou `mfa_authenticate` → `POST auth/2fa/authenticate {code}` | Django renouvelle la clé de session à la connexion ; un récepteur de `user_logged_in` pose `gc_login_at` (D12). Une adresse secondaire vérifiée permet aussi de se connecter (vérifié). Audit `auth.login` et `auth.login_failed` |
| **Première connexion** | `GET /v1/me` renvoie `privacy_notice_pending` | Écran d'accueil : prise de connaissance de la notice et profil minimal. **Pas de blocage global côté serveur** : les lots qui en ont besoin vérifient eux-mêmes leurs prérequis (L3 : profil complet pour soumettre) |
| **Déconnexion** | `DELETE auth/session` | Répond 401 (vérifié). Angular recharge ensuite la page entière (`location.assign`) pour vider l'état des deux applications. Audit `auth.logout` |
| **Expiration** | Middleware d'expiration absolue (D12) | Au-delà de 12 h depuis la connexion : `logout()`, puis 401 à la requête suivante. Audit `auth.session_expired` |
| **Mot de passe oublié** | `POST auth/password/request`, puis lien `/compte/reinitialiser#<clé>`, puis `GET auth/password/reset` avec l'en-tête `X-Password-Reset-Key`, puis `POST` | Réponse identique que le compte existe ou non. **Aucun envoi pendant la requête** : cet e-mail n'emprunte pas la voie rapide (§8.3) et attend le cron, pour ne pas créer d'écart de temps. L'écran prévient que l'e-mail peut prendre quelques minutes. Clé fondée sur le générateur de Django (vérifié) : valable `PASSWORD_RESET_TIMEOUT`, soit 3 jours par défaut, ramené à **2 h** proposées ; à usage unique, car le hachage dépend de l'état du mot de passe (**à confirmer par test**). Aucun lien n'est envoyé vers une adresse secondaire non vérifiée (§4.2, ajouté en v3). Audit |
| **Changement de mot de passe** | `account/password/change` | Exige l'ancien mot de passe (`current_password`), pas une réauthentification récente (vérifié). Notification `password_changed` à l'adresse principale. Les autres sessions sont invalidées, car le hachage de session change (**test**). *Corrigé en v3 : la v2 annonçait une réauthentification* |
| **Adresses e-mail** | `account/email` : ajout, suppression, choix de l'adresse principale | Réauthentification récente exigée grâce à `ACCOUNT_REAUTHENTICATION_REQUIRED=True` (§4.2) : sinon, 401 avec le flux `reauthenticate` (vérifié par essai), que la façade traite comme les autres réauthentifications (§10.1). allauth notifie la suppression et le changement d'adresse principale, mais pas l'ajout (vérifié) : notre récepteur d'`email_added` s'en charge (§4.2). En mode lien, un compte protégé par la 2FA **ne peut pas ajouter d'adresse** (`add_email_blocked`, vérifié par essai) : voir D6 et §5.7. *Corrigé en v3 : la v2 croyait la réauthentification et la notification déjà assurées par allauth* |
| **Enrôlement 2FA** | `GET account/authenticators/totp` (404 avec `meta.secret` et `totp_url`), puis `POST {code}` | Exige une réauthentification récente et génère 10 codes de secours (vérifié). Refusé (409 `unverified_email`) tant que le compte porte une adresse non vérifiée (vérifié par essai) : l'écran propose de la vérifier ou de la supprimer. **Il faut ensuite `POST auth/2fa/reauthenticate`**, car l'activation n'inscrit pas `mfa` dans la session (constaté). QR code : `GET /v1/me/totp-qr` (§10.2) |
| **Réauthentification** | `auth/reauthenticate` (mot de passe) ou `auth/2fa/reauthenticate` | Côté DRF, `RecentAuthRequired` répond 403 `reauthentication_required`. Angular ouvre alors une fenêtre de dialogue et rejoue la requête **une seule fois**. Côté allauth, la même fenêtre s'ouvre sur un 401 qui porte le flux `reauthenticate` ou `mfa_reauthenticate` |
| **Perte d'appareil** | Code de secours, puis réenrôlement. À défaut : `reset_mfa --email --reason` par l'opérateur | Vérification d'identité hors bande (procédure à valider). Audit et e-mail à l'utilisateur |

### 4.4 Imposer la 2FA côté serveur

allauth n'impose pas l'enrôlement : il n'existe aucun réglage natif (vérifié). On ajoute la permission DRF **`MfaVerified`**, appliquée d'office, par `ManageViewSet`, à toutes les vues `/v1/manage/editions/{edition_id}/…`. Elle s'exécute après le chargement de l'édition (§5.3). La liste des éditions du sélecteur, qui n'a pas d'édition dans son chemin, n'est pas concernée (D3, §5.3).

Pour un utilisateur qui détient, **dans l'édition du chemin**, un rôle de `MFA_REQUIRED_ROLES` :
1. si `allauth.mfa.utils.is_mfa_enabled(user)` est faux (vérifié), réponse 403 `mfa_enrollment_required` ;
2. si `allauth.account.authentication.get_authentication_records(request)` (API publique, vérifiée) ne contient aucune entrée de méthode `mfa`, réponse 403 `mfa_required` ;
3. sinon, l'accès est accordé.

La lecture de la session passe par une fonction unique, `session_has_mfa(request)`, ce qui facilite les tests.

**Suppression du TOTP par l'utilisateur.**
- Le `DELETE` *headless* ignore `can_delete_authenticator` (vérifié). Mais :
  - il exige une réauthentification récente (vérifié) ;
  - il déclenche une notification e-mail (vérifié, avec `ACCOUNT_EMAIL_NOTIFICATIONS=True`) ;
  - il est audité ;
  - la règle 1 s'applique **à chaque requête** : la personne doit se réenrôler avant de revenir dans `/manage`.
- **Recommandation :** s'en tenir à ces protections.
- **Option** (+0,25 à 0,5 j-h) : un middleware qui refuse ce `DELETE` aux rôles sensibles. Il gêne un attaquant qui connaît le mot de passe **et** détient la session, mais oblige à passer par l'opérateur en cas de changement de téléphone.

### 4.5 Réauthentification côté DRF

`RecentAuthRequired` lit `get_authentication_records(request)[-1]["at"]`. Elle protège les actions sensibles de D12, dont, depuis la v3, la liaison d'une adresse invitée (§5.7). Cet horodatage `time.time()` est écrit à chaque authentification (vérifié). La permission le compare à `ACCOUNT_REAUTHENTICATION_TIMEOUT`.

La structure de ces enregistrements est interne à allauth : un test la fige, pour détecter un changement lors d'une montée de version. On n'utilise pas les fonctions `internal` d'allauth. La même règle vaut pour la clé de session `mfa.totp.secret` lue par l'endpoint du QR code (§10.2).

### 4.6 CSRF, cookies, en-têtes

**Cookies.**
- Le cookie `csrftoken` est lisible par Angular, qui le renvoie dans l'en-tête `X-CSRFToken` (configuration L0, compatible, vérifié).
- Le cookie de session est `HttpOnly`, `Secure` et `SameSite=Lax`, sur le chemin `/` : une seule session pour le portail et la gestion. Il n'a pas de date d'expiration (`SESSION_EXPIRE_AT_BROWSER_CLOSE`), et le serveur impose 12 h absolues (D12).

**Où le CSRF est contrôlé, et quel code renvoyer.** Il y a trois cas distincts, et chacun a son test.
1. **Vues allauth.** Ce sont des vues Django ordinaires, protégées par le middleware CSRF (vérifié). Un échec passe par `CSRF_FAILURE_VIEW`, qui répond 403 `{code:"csrf_failed"}`.
2. **Vues DRF avec une session authentifiée.** `APIView.as_view()` exempte la vue du middleware (`csrf_exempt`, vérifié). Le contrôle est fait par `SessionAuthentication.enforce_csrf`, qui lève `PermissionDenied("CSRF Failed: …")`. Le gestionnaire L0 le traduit en `permission_denied` (vérifié par essai), et **`CSRF_FAILURE_VIEW` n'est jamais appelée**. Notre `apps.core.authentication.SessionAuthentication`, déjà prévue pour le 401, surcharge donc `enforce_csrf`. Elle lance le même contrôle (`CSRFCheck`) mais lève `CsrfFailed`, une `APIException` avec `status_code=403` et `default_code="csrf_failed"`. Sans cela, l'intercepteur Angular ne déclencherait jamais sa nouvelle tentative sur `/v1/me` ou `/v1/manage/…`.
3. **POST DRF anonymes** (`invitations/lookup`, `invitations/decline`). DRF ne contrôle le CSRF que pour une session authentifiée (vérifié). Ajouter `csrf_protect` serait **sans effet** : le décorateur transmet au middleware la vue déjà marquée `csrf_exempt`, et celui-ci sort aussitôt (vérifié dans le code). On utilise une permission **`CsrfEnforced`** qui appelle explicitement le même contrôle, même pour un anonyme, et lève `CsrfFailed`. Ces endpoints sont en outre protégés par le jeton secret qu'ils exigent.

On n'écrit jamais de vue d'authentification « maison » en DRF.

**Tests.** Le client de test de Django et `APIClient` désactivent le contrôle CSRF par défaut (vérifié). Les tests CSRF utilisent donc `enforce_csrf_checks=True`.

**Domaine.**
- `CSRF_TRUSTED_ORIGINS` contient uniquement le domaine de production.
- Pas de CORS (domaine unique).

**En-têtes.**
- `X-Robots-Tag: noindex` sur `/api/`.
- `robots.txt` dans le portail : `Disallow: /api/`, `/gestion/`, `/compte/`.
- `Referrer-Policy: same-origin`.

### 4.7 Limitation de débit et « verrouillage progressif »

| Portée | Valeur | Réponse |
|---|---|---|
| allauth `login` | 30/min par IP (défaut, vérifié) | 429 |
| allauth `login_failed` | `10/m/ip,5/300s/key` (défaut, vérifié) | 400 `too_many_login_attempts` (vérifié) |
| allauth `signup` | `20/m/ip` (défaut) ; resserrement proposé : `20/m/ip,100/3600s/ip` | 429 |
| allauth `reset_password` | `20/m/ip,5/m/key` (défaut) ; resserrement proposé : `20/m/ip,3/3600s/key` | 429 |
| allauth `confirm_email` | 1/180 s par adresse (défaut, vérifié) | 429, ou renvoi silencieusement ignoré à la reconnexion |
| DRF `invitation` (consultation, acceptation, refus) | 10/min par IP | 429 `throttled` |
| DRF `invitation_link` (demande d'un lien de liaison d'adresse, RG-20) | 3/heure par utilisateur | 429 `throttled` |
| DRF `invitation_create` | 20 créations/heure par utilisateur, **sur la seule action `create`**. `ScopedRateThrottle` ne distingue pas les méthodes (vérifié), alors que la même vue sert la liste (GET) : la vue surcharge donc `get_throttles()` selon `self.action`, posé avant les contrôles (vérifié). `ScopedRateThrottle` compte aussi des **requêtes**, or une requête peut porter 50 adresses. Le service applique donc en plus un **quota de 100 adresses par heure et par utilisateur**, par une requête de comptage sur `RoleInvitation` (`invited_by`, `created_at`), et lève `QuotaExceeded` (§9.1) | 429 `throttled`, avec `Retry-After` |
| DRF `data_export`, `account_deletion` | 3/heure par utilisateur | 429 |
| Envoi d'e-mails | Plafond global configurable (300 par heure) | Report en file |

**Pourquoi un quota d'invitations.** Un compte de comité compromis pourrait sinon envoyer du hameçonnage depuis le domaine de la conférence : 50 adresses par appel et un message libre.

**Pas de limitation DRF globale** (`anon`, `user`) : avec un cache en base, chaque requête de l'API coûterait des écritures sur l'hébergement mutualisé. Les taux déclarés en L0 sans classe (donc inopérants) sont remplacés par ces portées.

**« Verrouillage progressif » (§9.3).**
- Il correspond au blocage **temporaire** par compte d'allauth : 5 échecs en 5 minutes.
- **Pas de verrouillage permanent ni exponentiel**, pour éviter qu'un tiers bloque les comptes du comité juste avant une échéance (B18).
- Au-delà de 10 échecs par heure sur un compte sensible : audit et alerte e-mail.

**Prérequis bloquant pour la production : mesurer l'IP réelle derrière Passenger (L1.0).** Si `REMOTE_ADDR` est celle d'un proxy, tous les utilisateurs partagent le même compteur, ce qui provoque un blocage général. Le cas des campus derrière une seule adresse NAT est à surveiller (Q13).

### 4.8 Consentements

- **Notice d'information** (`privacy_notice`, versionnée) : affichée à l'inscription, prise de connaissance enregistrée à la première connexion. Chaque nouvelle version fait réapparaître la demande, signalée par `/me`.
- **Consentements facultatifs** : désactivés par défaut, retirables à tout moment, chaque action ajoutant une ligne.
- Tout enregistrement est audité.
- La table est en ajout seul. Seules ses deux méthodes nommées et auditées effacent l'IP (§7.1).

### 4.9 Export et anonymisation du compte

**Registre `core.personal_data`.** Chaque application déclare, dans `AppConfig.ready()`, une fonction `export(user) -> dict` et une fonction `anonymize(user, actor)`.

Deux tests garantissent que le registre est complet.
- **Introspection.** Le test liste tous les modèles ayant une FK vers `User` ou un `EmailField`. Il échoue si l'un d'eux n'est ni enregistré, ni exempté avec une justification. Chaque lot futur est ainsi **obligé** de traiter le RGPD pour ses propres données.
- **Balayage.** Un registre peut exister et pourtant ne pas tout effacer. Après `anonymize_user`, ce test parcourt **toutes les colonnes texte de tous les modèles**, tables tierces comprises, par introspection. Il échoue si l'une contient l'adresse, le nom ou le prénom d'origine. `django_session` est vérifiée après décodage. **Les fabriques du test injectent volontairement le nom et l'adresse dans les champs de texte libre**, notamment `RoleInvitation.message` et `OutboxEmail.subject` : sinon, le balayage n'aurait rien à détecter (ajouté en v3).

**`GET /v1/me/data-export`.**
- JSON synchrone en L1, le volume étant faible.
- Contenu : compte, profil, adresses, état de la 2FA sans aucun secret, rôles, invitations reçues, consentements, et ses propres actions dans l'audit sur 12 mois.
- Exige une réauthentification, limité en débit, audité.
- Deviendra un `Job` produisant une archive quand les fichiers arriveront (L3).

**`POST /v1/me/anonymization`.**
- Exige une réauthentification et une phrase de confirmation.
- **Refusé** (`account_has_active_duties`) si la personne détient un rôle actif autre qu'`AUTHOR` ou `ATTENDEE` dans une édition non archivée, ou si elle est le dernier `ADMIN`.
- **Effets**, dans une seule transaction :
  - e-mail remplacé par `anonymized-<id>@anonymized.invalid` ;
  - mot de passe rendu inutilisable, `is_active` à faux, `anonymized_at` renseigné ;
  - suppression des `EmailAddress` (et, par cascade, de leurs confirmations) et des authentificateurs MFA ;
  - profil vidé ;
  - rôles passés à `revoked` ;
  - **invitations** : celles adressées à l'une de ses adresses ou acceptées par ce compte (`accepted_by`) voient leur `email` remplacé par l'adresse anonymisée et leur `message` vidé, **quel que soit leur statut**. Celles en attente sont en outre annulées. Celles qu'il a **envoyées** (`invited_by`) voient aussi leur `message` vidé, car ce texte libre porte souvent la signature de l'invitant (ajouté en v3) ;
  - **registre d'envoi** : dans toutes les lignes `OutboxEmail` liées, par `to_user` ou par l'une de ses adresses, `to_email` est remplacé par l'adresse anonymisée et `subject` par `[anonymisé]`. Les corps encore présents sont purgés. L'objet ne devrait contenir aucune donnée de personne (règle des gabarits, §8.3), mais un gabarit futur pourrait l'enfreindre : on l'efface par prudence (ajouté en v3) ;
  - **sessions supprimées** : leurs enregistrements d'authentification contiennent l'adresse saisie à la connexion (vérifié). Les sessions non expirées sont décodées (`get_decoded()`), et celles du compte sont supprimées. Leur nombre reste faible ;
  - IP des consentements effacée (`Consent.redact_network_for_user`) ;
  - IP et user-agent de ses entrées d'audit effacés (`AuditLog.redact_network_for_user`). Les clichés `before`/`after` ne contiennent jamais l'adresse en clair (§7.2).
- Les sessions deviennent de toute façon invalides, car le hachage du mot de passe change (**test**).
- Le journal d'audit et les consentements sont conservés comme preuves (D15).
- L'action est auditée (`account.anonymized`), sans donnée personnelle.

**Demandes reçues par courrier ou e-mail :** commandes `export_user_data` et `anonymize_user --reason`, exécutées par l'opérateur.

### 4.10 Secrets et chiffrement

**Nouvelles variables**, documentées sans valeur dans `.env.example` :
- `GESTCONF_PUBLIC_URL` ;
- `GESTCONF_MFA_ENCRYPTION_KEYS` ;
- `GESTCONF_TRUSTED_PROXY_COUNT` ;
- `DEFAULT_FROM_EMAIL` ;
- clé du fournisseur d'e-mails ;
- `ADMINS`, pour les opérateurs (D17).

**Rotation**, documentée dans `deploy/README.md` :
- `SECRET_KEY` via `SECRET_KEY_FALLBACKS` (vérifié). Les liens signés de RG-20 (§5.7) dépendent de `SECRET_KEY` : une rotation les invalide au plus tôt après leur heure de validité ;
- clé MFA via `MultiFernet` et une commande `rotate_mfa_keys` (rechiffrement **à vérifier**).

**Perte de la clé MFA.** Toutes les 2FA deviennent inutilisables et chacun doit se réenrôler. La clé est donc sauvegardée **hors de l'hébergement, séparément des sauvegardes de la base**. Sinon, le chiffrement ne protège pas contre le vol d'une sauvegarde.

### 4.11 Menaces couvertes et limites assumées

| Menace | Mesures L1 | Preuve (test) |
|---|---|---|
| Force brute, bourrage d'identifiants | Limites allauth par IP et par compte, cache partagé, 2FA des rôles sensibles, mots de passe d'au moins 12 caractères avec liste noire (L0) | `too_many_login_attempts` ; test sur MariaDB |
| Énumération de comptes (contenu des réponses) | `PREVENT_ENUMERATION`, `EMAIL_UNKNOWN_ACCOUNTS=False`, adresse masquée dans les invitations | Réponses comparées entre adresse connue et inconnue |
| Énumération de comptes (temps de réponse) | Hachage factice dans le chemin « compte existant » de l'inscription ; voie rapide d'envoi réservée aux e-mails envoyés dans tous les cas, donc jamais pour `password/request` (§8.3) | Pour `signup` et `password/request`, adresse connue ou inconnue : même nombre d'appels au backend d'e-mail pendant la requête (zéro pour `password/request`) et même nombre de hachages de mot de passe |
| Vol ou fixation de session | Cookies `HttpOnly`, `Secure`, `Lax` ; clé de session renouvelée à la connexion ; **12 h absolues imposées par middleware** ; invalidation au changement de mot de passe | L'ancien cookie reçoit 401 après déconnexion ; une session modifiée à 11 h 59 est refusée à 12 h 01 ; une session sans horodatage est fermée |
| Session volée → ajout d'une adresse → réinitialisation du mot de passe : prise de contrôle durable, au-delà des 12 h de la session (ajouté en v3) | `ACCOUNT_REAUTHENTICATION_REQUIRED=True` ; `RecentAuthRequired` sur `link-email` et `accept {link}` (RG-20) ; notification « adresse ajoutée » à l'adresse principale (récepteur `email_added` et liaison RG-20) ; aucune réinitialisation vers une adresse secondaire non vérifiée ; refus d'accepter une invitation que l'on a soi-même envoyée. Avec une session volée de `SC_CHAIR` ou de `CHAIR`, déjà validée par la 2FA, la liaison RG-20 aurait permis, sans ces mesures, de s'inviter à sa propre adresse puis de la lier au compte de la victime | `test_add_email_requires_recent_reauth` (401 `reauthenticate`, aucune adresse ajoutée) ; `test_rg20_link_requires_recent_reauth_and_notifies_primary` ; `test_email_added_notifies_primary` ; `test_password_reset_not_sent_to_unverified_secondary_address` ; `test_inviter_cannot_accept_own_invitation` |
| CSRF | Middleware sur allauth ; `SessionAuthentication` du projet sous DRF ; permission `CsrfEnforced` pour les POST anonymes ; client `app` désactivé ; réponses en JSON | POST sans jeton → 403 `csrf_failed`, testé séparément sur allauth, DRF connecté et DRF anonyme |
| Empoisonnement de `Host` dans les liens | `FRONTEND_URLS` absolues, `ALLOWED_HOSTS` strict | Avec un `Host` forgé, le lien reste sur le domaine officiel |
| Fuite des jetons (journaux, Referer, base) | Clé dans le fragment `#`, effacé de l'historique par Angular ; en-tête `X-Password-Reset-Key` ; jeton d'invitation haché ; corps sensibles purgés | Valeur brute en base ≠ jeton ; purge après envoi |
| Lien d'invitation transféré ou divulgué | RG-20 : le jeton seul ne suffit jamais. Il faut une adresse vérifiée correspondante, ou un lien de confirmation envoyé à l'adresse invitée, lié au compte demandeur et soumis à une réauthentification récente (option (a) de D6) | Jeton présenté par un compte sans l'adresse → 409, aucun rôle ; lien de liaison rejoué par un autre compte → 400 ; lien de liaison sans réauthentification récente → 403 |
| Rejeu ou vol du secret TOTP | Anti-rejeu via le cache partagé ; secret chiffré | Même code refusé deux fois ; colonne brute chiffrée |
| Contournement de la 2FA | `MfaVerified` à chaque requête `/manage/editions/{id}/…`, vérification de la session ; la liste des éditions, sans 2FA, ne renvoie aucun champ sensible | Rôle sensible sans session MFA → 403 ; liste des éditions → 200 sans champ sensible |
| Élévation entre éditions, IDOR | Édition prise uniquement dans le chemin et chargée avant les permissions, querysets filtrés, 404 pour un non-membre | `CHAIR` de A → 404 sur B ; ordre 401, 404, 403 fixé par un test |
| Escalade par attribution de rôles | Matrice d'attribution, pas d'action sur ses propres rôles, dernier `ADMIN` protégé, RG-20, e-mail au bénéficiaire | Tests de la matrice d'attribution |
| Abus d'envoi d'invitations (hameçonnage depuis le domaine) | Portée `invitation_create` sur la seule création, quota de 100 adresses par heure et par utilisateur (`QuotaExceeded`), plafond global d'envoi, audit | 21e création dans l'heure → 429 ; 101e adresse → 429 `throttled` avec `Retry-After` ; 25 consultations de la liste → 200 |
| Assignation de masse | Champs explicites, `role`, `status` et `edition` en lecture seule | PATCH avec champs interdits |
| Falsification des traces | Audit et consentements en ajout seul, commandes auditées avec motif | Tests d'immuabilité |
| Redirection ouverte | Validateur de `next`, identique côté serveur et côté Angular | Chaînes malveillantes paramétrées |

**Limites assumées en L1.**
- **Hameçonnage en temps réel (AiTM)** : le TOTP n'y résiste pas. Seul WebAuthn (P3) le ferait.
- **Opérateur malveillant** ayant accès à SSH ou à la base : l'immuabilité du journal est applicative, faute de droits SQL séparés en mutualisé (non vérifié). Un chaînage d'empreintes est possible plus tard.
- **XSS sur le portail** : comme le domaine et le cookie sont partagés, elle donnerait accès à l'API de gestion. D'où la CSP stricte sur les deux applications, l'absence de texte riche et l'absence de script tiers.
- **Écart de temps résiduel sur `password/request`.** Quand le compte existe, la requête rend l'e-mail et fait deux insertions en base, ce qui prend quelques millisecondes (non mesuré). Quand il n'existe pas, elle ne fait rien de tout cela. L'écart est sans commune mesure avec un aller-retour vers le fournisseur ou un hachage PBKDF2, et la limite `reset_password` (3 demandes par heure et par adresse) rend une mesure statistique très lente.
- **Mot de passe volé d'un compte sans 2FA** : la réauthentification ne protège plus rien, puisque l'attaquant la passe. La notification « adresse ajoutée » permet seulement à la victime de réagir. C'est la raison d'imposer la 2FA aux rôles de gestion et de trancher le cas de `SC_MEMBER` avant L4 (D3).
- **Saturation du cache en base** (R18). Au-delà de `MAX_ENTRIES` entrées non expirées, Django supprime un tiers des clés par ordre alphabétique, compteurs compris (vérifié). Un attaquant disposant de nombreuses IP pourrait ainsi remettre des compteurs à zéro. Mesures : plafond relevé, purge fréquente des entrées expirées, alerte (§3.5).

---

## 5. Rôles et permissions

### 5.1 Principe : quatre étages, refus par défaut

Le serveur calcule les droits à partir de **tous** les `UserRole` actifs de l'utilisateur dans l'édition visée. Il ne lit jamais de « rôle actif » envoyé par le client.

1. **Capacités d'édition.** Une table rôles → capacités, **codée et revue en PR**, non paramétrable en base. C'est pourquoi l'écran « Rôles et permissions » de §10.2 devient « Membres et rôles ».
2. **Filtrage du queryset** par édition, puis par rôle ou par propriété, pour la visibilité des objets.
3. **Règles fines dans les services** : qui attribue quoi, dernier `ADMIN`, invariants, quotas. C'est une défense en profondeur, également utilisée par les commandes et les tâches.
4. **Sérialiseur choisi selon les capacités**, pour la minimisation des champs. L'échec est fermé : sans correspondance, on refuse ou on renvoie le sérialiseur le plus restrictif.

`GET /v1/me` renvoie les capacités par édition. Angular masque les boutons d'après elles **sans recopier la matrice en TypeScript** : une seule source de vérité.

Les transitions d'état (édition, invitation, rôle, tâche) passent par un service par machine à états. Aucune vue ne modifie `status` directement : c'est le principe de la règle n° 4, étendu.

### 5.2 Capacités en L1 (proposition, extension de §3.3)

| Capacité | ADMIN | CHAIR | SC_CHAIR | OC_MEMBER | SC_MEMBER | AUTHOR, ATTENDEE, autres |
|---|---|---|---|---|---|---|
| `edition.read` (paramétrage) | ✓ | ✓ | Selon D8 (recommandé ✓) | ✓ | — | — |
| `edition.write` (infos, tracks, types, calendrier, confidentialité) | ✓ | ✓ | — | — (D8) | — | — |
| `edition.publish` | ✓ | ✓ | — | — | — | — |
| `edition.archive` | ✓ | — | — | — | — | — |
| `members.read` (membres et invitations) | ✓ | ✓ | Membres et invitations du CS seulement | — | — | — |
| `members.manage` (inviter, révoquer, selon §5.5) | ✓ | ✓ | `SC_MEMBER` seulement | — | — | — |
| `audit.read` (journal de l'édition, sans IP) | ✓ | ✓ | — | — | — | — |
| 2FA exigée (`MFA_REQUIRED_ROLES`) | ✓ | ✓ | ✓ | ✓ | Selon D3 | — |

**Remarques.**
- En L1, **aucun endpoint n'est ouvert à `SC_MEMBER`** ; l'emplacement de son espace relève de Q16. Il voit ses rôles et ses invitations dans `/compte`.
- `AUTHOR` et `ATTENDEE` n'ouvrent aucun accès à `/manage`.
- Un utilisateur anonyme reçoit 401. Un non-membre de l'édition reçoit 404. Un membre sans la capacité reçoit 403. Une écriture sur une édition archivée reçoit 409 `edition_archived`.

### 5.3 Mécanique DRF

Esquisse indicative, pour valider l'architecture :

```python
# apps/accounts/roles.py : source unique, revue en PR
class Role(models.TextChoices): ...                       # 11 rôles (§3.2)
class Capability(StrEnum): EDITION_READ = "edition.read"; ...
CAPABILITIES: Mapping[Role, frozenset[Capability]]
MFA_REQUIRED_ROLES: frozenset[Role]
GRANTORS: Mapping[Role, frozenset[Role]]                  # §5.5

# apps/accounts/services.py
@dataclass(frozen=True)
class EditionAccess:
    edition: Edition
    roles: frozenset[tuple[Role, str]]                    # (rôle, fonction CO)
    capabilities: frozenset[Capability]
def edition_access(user: User, edition_id: int) -> EditionAccess: ...   # 1 requête ; Http404 si aucun rôle actif
def grant_role(*, user: User, edition: Edition, role: Role, actor: Actor,
               source: RoleSource, oc_function: str = "", reason: str = "") -> UserRole: ...
def revoke_role(*, user_role: UserRole, actor: Actor, reason: str) -> UserRole: ...

# apps/accounts/permissions.py
class EditionScopedViewMixin:
    """Charge l'édition du chemin et l'EditionAccess AVANT les classes de permission.
    DRF appelle check_permissions() dans initial(), après l'authentification et avant
    le gestionnaire, donc avant get_queryset() : c'est là qu'on charge.
    Anonyme : rien n'est chargé, IsAuthenticated répond 401. Non-membre : Http404.
    Ensuite, filtre get_queryset() par édition et appelle scope_queryset(qs, access)."""
    def check_permissions(self, request):
        if request.user.is_authenticated:
            self.access = edition_access(request.user, self.kwargs["edition_id"])
        super().check_permissions(request)
class HasCapability(BasePermission):
    """Lit view.required_capabilities = {"GET": EDITION_READ, "PATCH": EDITION_WRITE}
    et view.access. Échec fermé : une méthode non déclarée est refusée."""
class MfaVerified(BasePermission): ...                    # §4.4
class RecentAuthRequired(BasePermission): ...             # §4.5
class CsrfEnforced(BasePermission): ...                   # §4.6, POST publics
class ManageViewSet(EditionScopedViewMixin, GenericViewSet):
    """Réservé aux routes v1/manage/editions/{edition_id}/… (test de plateforme, §5.9)."""
    permission_classes = (IsAuthenticated, HasCapability, MfaVerified)
class ManageEditionListView(ListAPIView):
    """GET v1/manage/editions : sélecteur d'édition, sans edition_id dans le chemin.
    Queryset limité aux éditions où l'on détient au moins une capacité ; champs non
    sensibles (id, code, titres, année, statut) ; pas de MfaVerified (D3)."""
    permission_classes = (IsAuthenticated,)
```

**Ordre des contrôles.** DRF exécute l'authentification, les permissions et les limites de débit dans `initial()`, avant le gestionnaire, donc avant `get_queryset()` et `get_object()` (vérifié). Si l'édition n'était chargée que dans `get_queryset()`, `HasCapability` et `MfaVerified` s'exécuteraient sans elle. Deux issues possibles, toutes deux mauvaises : un non-membre recevrait 403 au lieu de 404, ce qui révèle l'existence de l'édition ; ou la permission planterait. D'où la surcharge de `check_permissions`. Un test de la matrice fixe l'ordre attendu :
1. anonyme → 401 ;
2. non-membre → 404 ;
3. membre sans capacité → 403 ;
4. rôle sensible sans TOTP → 403 `mfa_enrollment_required` ;
5. rôle sensible sans session MFA → 403 `mfa_required`.

Les limites de débit s'appliquent après les permissions, dans l'ordre de DRF.

**La liste des éditions, une vue à part (corrigé en v3).** `GET /v1/manage/editions` n'a pas d'`edition_id` dans son chemin. Servie par `ManageViewSet`, elle ferait lever `KeyError` au mixin (`self.kwargs["edition_id"]`), donc une erreur 500, et `MfaVerified` n'aurait pas d'édition à examiner. Elle est donc déclarée à part, `ManageEditionListView`, seule exception à la règle de plateforme (§5.9). Elle n'exige pas la 2FA (D3) : elle ne sert qu'au sélecteur, ne renvoie aucun champ sensible, et chaque édition exige ensuite la 2FA. Ses cases de matrice :
- anonyme → 401 ;
- connecté sans rôle → 200, liste vide ;
- `CHAIR` sans session MFA → 200, sans champ sensible ;
- `CHAIR` de l'édition A → l'édition B est absente de la liste.

**Filtres et tri.** `FilterSet` et `ordering_fields` sont toujours **explicites**. Par défaut, `OrderingFilter` autorise le tri sur les champs du sérialiseur (vérifié), et `"__all__"` l'ouvrirait à tous les champs du modèle. Un tri sur un champ caché pourrait servir d'oracle contre le double aveugle en L4 : un méta-test interdit donc `"__all__"`.

**Permission globale.** `IsAuthenticated` reste la permission par défaut. Le test L0 `test_api_requires_authentication_by_default` vérifie aujourd'hui une égalité stricte : il passe à un test d'inclusion si nécessaire.

### 5.4 Filtrage des querysets et sérialiseurs par rôle (base de RG-04)

- **Filtrage par édition.** Le mixin filtre toujours par `edition=self.access.edition`. Un identifiant d'une autre édition donne 404.
- **Filtrage par rôle.** Le point d'extension `scope_queryset(qs, access)` est utilisé dès L1 pour deux listes :
  - **les membres** : le `SC_CHAIR` ne voit que le CS ;
  - **les invitations** : le `SC_CHAIR` ne voit que les invitations `SC_MEMBER`. Sinon, il verrait les adresses invitées aux rôles `ADMIN`, `CHAIR` et CO.

  En L4, il limitera un relecteur aux soumissions qui lui sont affectées.
- **Sérialiseur selon les capacités.** En L1, l'e-mail des membres n'est visible qu'avec `members.manage`, donc pour le `SC_CHAIR` sur le seul CS.
- **RG-04 n'est pas préparée spécifiquement en L1.** Le registre `IDENTITY_FIELDS`, la classe `AnonymizedSerializer` et son méta-test, ainsi que l'utilitaire `assert_no_identity_leak`, n'auraient aucun consommateur en L1. Aucun sérialiseur relecteur n'existe, et un méta-test sur une classe sans sous-classe ne teste rien. Ils sont reportés au **début de L4**, avant le premier endpoint relecteur (§1.3), conformément à la méthode par lots de `CLAUDE.md`. L1 livre en revanche les **mécanismes génériques** dont RG-04 aura besoin, chacun avec un consommateur en L1 :
  - le filtrage par rôle ;
  - le sérialiseur choisi selon les capacités ;
  - les tris et filtres explicites, avec le méta-test contre `"__all__"` ;
  - la matrice des droits.

  L'action d'audit `identity.revealed` reste réservée dans le catalogue (§7.3).
- **Donnée d'entrée pour L4, conservée de la v1** (supprimée par erreur en v2). Champs d'identité que le registre `IDENTITY_FIELDS` devra couvrir : `User.email`, `Profile.first_name`, `last_name`, `institution`, `department`, `orcid`, `bio`, ainsi que `EmailAddress.email`, pour les adresses secondaires (ajouté en v3). **À examiner en L4** pour le double aveugle : `Profile.title` et `country`. Ils ne nomment personne, mais réduisent l'anonymat : un titre de professeur, un pays peu représenté dans une thématique.
  - Conception du contrôle, conservée de la v1 : le méta-test d'`AnonymizedSerializer` vérifie qu'aucun sérialiseur relecteur ne déclare un champ du registre, **ni directement, ni par une relation imbriquée** ; `assert_no_identity_leak(payload, users)` parcourt **récursivement** une réponse et y cherche les **valeurs** d'identité (nom, adresses, ORCID), et non les noms de champs. Ce sont les deux pièges classiques du double aveugle.

### 5.5 Qui attribue quel rôle (D7)

| Rôle visé | Opérateur (commande) | ADMIN | CHAIR | SC_CHAIR |
|---|---|---|---|---|
| ADMIN, CHAIR | Oui | Oui, avec réauthentification | — | — |
| SC_CHAIR, OC_MEMBER (avec fonction) | Oui | Oui | Oui | — |
| SC_MEMBER | Oui | Oui | Oui | Oui |
| SPEAKER, SESSION_CHAIR, SPONSOR, VOLUNTEER | Oui | Activés dans leur lot (L5, L8) | Idem | — |
| AUTHOR, ATTENDEE | Système uniquement (§5.6) | Jamais à la main | — | — |

**Règles transverses.**
- On ne modifie jamais ses propres rôles.
- Le dernier `ADMIN` actif d'une édition ne peut être révoqué que par commande (code `last_admin`).
- Toute révocation exige un motif.
- Toute attribution ou révocation est auditée et notifiée par e-mail au bénéficiaire, ce qui permet de détecter une attribution malveillante.
- Les invitations sont soumises au quota du §4.7.

### 5.6 Attribution automatique d'`AUTHOR` et d'`ATTENDEE`

- **En L1 :** le service `grant_role(source=system)` est idempotent (aucune nouvelle ligne si le rôle est déjà actif) et audité. Il n'a **aucun déclencheur** en L1.
- **Jamais à l'inscription**, qui n'est rattachée à aucune édition.
- **Moments proposés** : voir D7. Ils seront figés dans L3 et L6.
- Ces rôles servent à la navigation et aux segments d'envoi. L'accès à ses propres objets se contrôle par **propriété** (filtrage par utilisateur).

### 5.7 Invitation des membres de comité

| Étape | Mécanique | Contrôles |
|---|---|---|
| **Créer** | `POST /v1/manage/editions/{id}/invitations {emails (50 au plus), role, oc_function, locale, message}` | Matrice §5.5. Portée `invitation_create`, appliquée à la seule création, et quota de 100 adresses par heure et par utilisateur, dont le dépassement lève `QuotaExceeded` → 429 (§4.7). Expiration à la volée des invitations échues de même clé (§3.3), puis une seule invitation en attente, garantie par la base (`pending_key`, empreinte SHA-256). Aucun rôle actif identique. Jeton de 256 bits haché. E-mail FR/EN mis en file (`is_sensitive`) ; la voie rapide n'en envoie que 3 pendant la requête, les autres partent au cron (§8.3). Audit `invitation.created`, sans l'adresse en clair |
| **Lien** | `https://<domaine>/compte/invitation#<jeton>` | Le fragment n'est jamais envoyé au serveur, donc jamais journalisé. Angular le lit puis l'efface de l'historique (`history.replaceState`) |
| **Consulter** | `POST /v1/invitations/lookup {token}` (public, `CsrfEnforced`, limité) | Renvoie l'édition, le rôle, le nom de l'invitant, l'adresse **masquée** (`j***@univ.ci`), l'état, et si la personne connectée contrôle déjà l'adresse |
| **Accepter** | `POST /v1/invitations/accept {token}` (connecté) | Jeton valide et non expiré, puis **RG-20** : **(a)** une adresse vérifiée du compte correspond → acceptation ; **(b)** l'adresse invitée est vérifiée sur un **autre** compte → 409 `invitation_email_mismatch` (« connectez-vous avec le compte qui porte cette adresse ») ; **(c)** sinon → 409 `invitation_email_unverified`, et l'écran propose de lier l'adresse (option (a) de D6 ; avec l'option (b), il propose de l'ajouter dans `/compte/securite`). Rôle créé ou réactivé dans la même transaction. Audit `role.granted` et `invitation.accepted`. Avec le corps `{token}`, aucune réauthentification n'est exigée, car aucune adresse n'est ajoutée au compte. **Refus (403 `invitation_self_accept`) si le compte qui accepte est celui de l'invitant** (`invited_by`) : on ne s'attribue jamais un rôle (§5.5). Cette règle, ajoutée en v3, ferme à elle seule le scénario « s'inviter à sa propre adresse, puis la lier à son compte » décrit plus bas |
| **Lier l'adresse** (cas c, option (a) de D6) | `POST /v1/invitations/link-email {token}` (connecté, **réauthentification récente** par `RecentAuthRequired`, limite `invitation_link`). Un e-mail part vers l'adresse invitée, avec le lien `/compte/invitation#lier=<jeton signé>`. Ce lien aboutit à `POST /v1/invitations/accept {link}`, depuis le même compte, **lui aussi soumis à `RecentAuthRequired`** : la vue ajoute cette permission quand le corps porte `link` (ajouté en v3) | Le jeton signé (`django.core.signing.dumps`, sel dédié, valable 1 h, vérifié dans le code) porte l'identifiant de l'invitation et celui du **compte demandeur**. Il n'est valable que pour ce compte. Comme il est envoyé à l'adresse invitée, il prouve qu'on la contrôle, exactement comme la vérification d'allauth. À l'acceptation, une seule transaction : `EmailAddress(verified=True, primary=False)` créée, ou l'adresse non vérifiée du compte marquée vérifiée ; acceptation ; **e-mail « une adresse a été ajoutée à votre compte » mis en file vers l'adresse principale** (gabarit `account/email/email_added`, en liste blanche, ajouté en v3) ; audit `account.email_linked` et `invitation.accepted`. Refus si l'adresse est entre-temps vérifiée sur un autre compte (409 `invitation_email_mismatch`), ou si le compte a déjà 3 adresses (409 `email_address_limit`, `can_add_email`). Lien expiré ou altéré → 400 `invitation_link_invalid`. Usage unique de fait : l'invitation n'est plus en attente après acceptation. **Pourquoi ce détour :** en mode lien, le formulaire d'ajout d'adresse d'allauth est bloqué pour les comptes 2FA (`add_email_blocked`, vérifié par essai) ; en créant la ligne `EmailAddress` dans notre service, on ne passe pas par lui. Le blocage serait aussi levé par le mode « code » : c'est l'option (b) de D6. **Ce détour doit appliquer les mêmes protections que l'ajout d'adresse par allauth, tel que ce plan le configure (§4.2)** : réauthentification récente, notification, limite de 3 adresses, refus d'une adresse vérifiée sur un autre compte. La v2 en oubliait deux, la réauthentification et la notification. Une session volée de `SC_CHAIR` ou de `CHAIR`, déjà validée par la 2FA, aurait alors suffi pour s'émettre une invitation à sa propre adresse, la lier au compte de la victime, puis réinitialiser le mot de passe par elle. La 2FA aurait ensuite bloqué la connexion de l'attaquant, mais la victime aurait perdu l'accès à son compte. **Effet de bord à connaître :** l'adresse liée permet aussi de se connecter, car allauth authentifie par toute adresse vérifiée (vérifié) |
| **Refuser** | `POST /v1/invitations/decline {token}` (public, `CsrfEnforced`) | Ne donne aucun droit, donc pas besoin de compte. Audit. Une nouvelle invitation reste possible |
| **Renvoyer, annuler** | `…/invitations/{id}/resend` et `/cancel` | Renvois limités (`send_count`). Audit |
| **Lister** | `GET …/invitations` | Filtrée par rôle : le `SC_CHAIR` ne voit que les invitations `SC_MEMBER` (§5.4) |
| **Expirer** | `cleanup` (quotidien) et service de création (à la volée) | Statut `expired`, `pending_key` remis à NULL |

**Alternative écartée.** La relecture proposait d'ajouter l'adresse au compte sur simple présentation du jeton d'invitation. Ce serait plus simple, mais le jeton deviendrait un titre au porteur pour le rôle : un lien transféré à un collègue, ou retrouvé dans un historique, suffirait pour obtenir un rôle `ADMIN`. C'est ce que RG-20 veut justement empêcher. Le lien de confirmation coûte environ 0,75 j-h, protections de la v3 comprises (§13).

**Si l'option (b) de D6 est retenue.** La ligne « Lier l'adresse » disparaît, avec `link-email`, le jeton signé, la limite `invitation_link` et le code `invitation_link_invalid`. Dans le cas (c), la personne ajoute l'adresse invitée dans `/compte/securite` : réauthentification récente, puis code reçu à cette adresse. Elle revient ensuite accepter l'invitation, qui relève alors du cas (a). RG-20 reste identique, et la notification « adresse ajoutée » est envoyée par le récepteur d'`email_added` (§4.2).

### 5.8 Sélecteurs d'édition et de rôle actifs

Ils sont **purement ergonomiques** (règle n° 2) :
- l'édition active figure dans l'URL de la gestion (`/gestion/editions/:editionId/…`) ;
- le « rôle actif » ne fait que filtrer les menus ;
- la préférence est mémorisée dans `localStorage`, avec un accès protégé par try/catch ;
- **le serveur ne lit aucun rôle actif.**

Les conflits, par exemple un `SC_MEMBER` également `AUTHOR` dans la même édition, sont traités en L4 par exclusion automatique. L1 ne les interdit pas.

### 5.9 Tests « un test par case sensible »

**Tableau déclaratif.** `MATRIX = [(nom_de_route, méthode, profil, statut_attendu), …]`, paramétré par pytest. Chaque case devient un test nommé, par exemple `test_matrix[manage-tracks-POST-OC_MEMBER-403]`. Les docstrings citent §3.3 et la RG concernée.

**Profils couverts :**
- anonyme ; connecté sans rôle ; `AUTHOR` ; `SC_MEMBER` ; `SC_CHAIR` ; `OC_MEMBER` ; `CHAIR` ; `ADMIN` ;
- `CHAIR` d'une **autre édition** ;
- rôle **révoqué** ;
- destinataire d'une **invitation non acceptée** ;
- `CHAIR` **sans TOTP** ; `CHAIR` avec TOTP mais **session sans MFA** ;
- `CHAIR` dont la **réauthentification a expiré** ;
- **édition archivée**.

**Cases ajoutées en v2 :**
- liste des invitations par `SC_CHAIR` : seulement `SC_MEMBER` ;
- ordre des réponses 401 → 404 → 403 → `mfa_*` (§5.3).

**Cases ajoutées en v3 :**
- liste des éditions (`ManageEditionListView`) : anonyme → 401 ; connecté sans rôle → 200, liste vide ; `CHAIR` sans session MFA → 200, sans champ sensible ; `CHAIR` de A → B absente (§5.3) ;
- liaison d'adresse (`link-email`, `accept {link}`) sans réauthentification récente → 403 `reauthentication_required` ;
- 25 consultations de la liste des invitations en une heure → 200 : le budget de création n'est pas consommé (§4.7).

**Test de complétude.** Il parcourt le résolveur d'URL et échoue si une route sous `/v1/manage/` est absente de `MATRIX`. Un endpoint ajouté en L3 à L8 ne peut pas échapper à la matrice.

**Volume.** Environ 90 à 130 cas en L1, générés et peu coûteux.

**Autres garde-fous de plateforme** (`tests/test_platform_rules.py`) :
- toute vue sous `v1/manage/editions/{edition_id}/` hérite de `ManageViewSet`, et toute route servie par `ManageViewSet` contient `{edition_id}`. Seule autre vue sous `v1/manage/` : `ManageEditionListView`, en liste blanche (§5.3 ; corrigé en v3) ;
- `AllowAny` est limité à une liste blanche : `health`, `public/*`, `invitations/lookup`, `invitations/decline` ;
- toute vue publique qui accepte POST porte `CsrfEnforced` ;
- pas de `has_perm` ni de `DjangoModelPermissions` ;
- pas de `"__all__"` dans les filtres ou le tri ;
- pas de `UniqueConstraint(condition=…)` ;
- chaque énumération du schéma porte un nom déclaré dans `ENUM_NAME_OVERRIDES` (§9.5) ;
- `HEADLESS_CLIENTS == ("browser",)` et `ACCOUNT_REAUTHENTICATION_REQUIRED is True` ;
- pas de `django.contrib.admin` (test L0 existant).

---

## 6. Paramétrage de l'édition (M3)

### 6.1 Ce qui est en L1

| Élément de M3 | Contenu L1 | Droits | Règles |
|---|---|---|---|
| Conférence et création d'une édition | Nom, slug, description FR/EN ; édition courante | Opérateur (commande, D1) | Écran éventuel en L8 |
| Informations générales | Titres et thèmes FR/EN, dates, lieu, ville, pays, fuseau, `code` | Écriture : ADMIN et CHAIR. Lecture : OC (et SC_CHAIR selon D8) | Fuseau validé par `zoneinfo` |
| Statut | `draft` → `published` → `archived` | §6.3 | Service unique, réauthentification, audit |
| Thématiques (tracks) | Code, noms et descriptions FR/EN, ordre, activation | ADMIN, CHAIR | Désactivation plutôt que suppression dès qu'une référence existe |
| Types de communication | Code, libellés FR/EN, durée par défaut, nombre maximal de mots du résumé, ordre, activation | ADMIN, CHAIR | Formats et taille viendront en L3 (Q5) |
| Calendrier | Codes réservés et libres, saisie à l'heure de l'édition (D13), visibilité publique ou interne, ordre contrôlé ; services `key_date()` et `is_call_open()` | ADMIN, CHAIR | Les déclencheurs automatiques viendront en L3 et L4 |
| Confidentialité | `double_blind`, `reviewers_per_submission` | ADMIN, CHAIR, avec réauthentification | Changement audité, classé critique. Gel après l'ouverture de l'appel : L3 (RG-19 proposée) |

Toute modification est **auditée avec l'état avant et après**, limité aux champs de configuration (B14).

### 6.2 Échéances et fuseau

- **Saisie et stockage :** `at_local` est converti en UTC côté serveur (D13). L'heure proposée par défaut est 23 h 59, heure de l'édition, affichée avec le nom du fuseau.
- **Changement de fuseau après la saisie des dates :** les instants UTC ne bougent pas, mais les heures locales affichées se décalent. Un avertissement s'affiche, et le changement est audité.

### 6.3 Statut de l'édition

Transition par un service unique, `set_edition_status(edition, to_status, actor, reason="")`.

| Transition | Qui | Préconditions | Effet |
|---|---|---|---|
| `draft` → `published` | ADMIN, CHAIR (réauthentification) | Titres FR et EN (D14), dates, au moins un track et un type actifs, `call_open` et `call_close` renseignés | Visible par `GET /v1/public/editions/current`, et par le portail en L2 |
| `published` → `archived` | ADMIN (réauthentification) | Date du jour postérieure à `end_date` | Lecture seule partout (409). Point de départ de la conservation RG-18 |
| Retour en arrière | Commande seulement | Motif | Audit |

### 6.4 Ce qui attend

| Élément | Lot |
|---|---|
| Langues des soumissions (Q6, C13), formats et tailles des fichiers, article complet (Q5) | L3 |
| Gel de la confidentialité et du code après l'ouverture (RG-19 proposée) ; états automatiques déclenchés par les dates ; prolongation globale ou dérogation (RG-02) | L3, L4 |
| Grilles d'évaluation (RG-05), minimum de relecteurs (RG-07), seuil de divergence, charge maximale, validation par le Chair, président de track | L4 |
| Modèles d'e-mails par édition, expéditeur | L3 |
| RG-11 désactivable, tampons RG-13 | L5 |
| Tarifs, catégories, devises | L6 |
| Modèles de documents (attestations, factures) | L6, L7 |
| Contenus du portail | L2 |
| Durée de conservation par édition (RG-18) | L3 (champ), L8 (purge) |
| Écritures partielles du CO | Après Q12 |

---

## 7. Journal d'audit (RG-17)

### 7.1 Modèle

Voir §3.5. La table est en **ajout seul** :
- le modèle refuse `save()` sur une ligne existante, ainsi que `delete()` ;
- le queryset refuse `update()` et `delete()`.

Trois exceptions, nommées et elles-mêmes auditées. La v1 n'en citait que deux, en oubliant la purge du contexte réseau à 6 mois de D15.
- `purge_network_before(date)` : efface l'IP et le user-agent des lignes plus anciennes que la date (6 mois, D15) ;
- `purge_before(date)` : supprime les lignes plus anciennes que la durée de conservation (3 ans, D15) ;
- `redact_network_for_user(user)` : efface l'IP et le user-agent des actions d'un compte, à son anonymisation.

**`Consent` suit le même mécanisme** : refus de `save()` en mise à jour, de `delete()`, de `update()` et de `delete()` sur le queryset. Deux exceptions nommées et auditées : `purge_network_before(date)` (6 mois) et `redact_network_for_user(user)`. Sans elles, la purge de l'IP prévue par D15 échouerait, ou l'immuabilité ne serait pas appliquée.

### 7.2 Service

```python
# apps/core/audit.py
def record(action: str, *, actor: Actor, edition: Edition | None = None, obj: Model | None = None,
           before: Mapping[str, Any] | None = None, after: Mapping[str, Any] | None = None,
           reason: str = "") -> AuditLog: ...
def snapshot(instance: Model) -> dict[str, Any]: ...      # uniquement les AUDIT_FIELDS du modèle
```

- `record` est appelé **dans la transaction du service métier** : si l'action est annulée, aucune trace ne subsiste, et inversement.
- **`AUDIT_FIELDS` ne contient jamais d'adresse e-mail en clair.** Pour `RoleInvitation`, on journalise un champ calculé `email_masked` (`j***@univ.ci`) à la place de `email`. Un test le vérifie.
- `Actor` est construit une seule fois : `Actor.from_request(request)`, `Actor.command(nom)` ou `Actor.system(job)`. Il porte l'IP (via `client_ip()`), le user-agent et le `request_id`, généré par un petit middleware. Les services ne reçoivent jamais l'objet `request`.
- Pour l'authentification, `record` est appelé par des récepteurs de signaux branchés dans `AccountsConfig.ready()`. Leurs noms ont été relevés dans le code :
  - Django : `user_logged_in` (qui pose aussi `gc_login_at`, D12), `user_login_failed` ;
  - allauth : `user_logged_in`, `password_changed`, `password_reset`, `email_confirmed`, `email_added` (ce dernier ajouté en v3, pour la notification du §4.2) ;
  - MFA : `authenticator_added`, `authenticator_removed`, `authenticator_reset`, `authentication_failed`.

  Les signatures exactes sont **à vérifier**, sauf celle d'`email_added`, vérifiée : `request`, `user`, `email_address`.
- Pour un e-mail inconnu, la tentative de connexion est enregistrée sans compte, avec seulement l'IP.

### 7.3 Actions journalisées dès L1

| Domaine | Actions | Édition |
|---|---|---|
| Authentification | `auth.login`, `auth.login_failed`, `auth.logout`, `auth.session_expired`, `auth.password_changed`, `auth.password_reset`, `account.signed_up`, `account.email_confirmed`, `account.email_added`, `account.email_linked` | Non (opérateur) |
| 2FA | `mfa.enabled`, `mfa.disabled`, `mfa.recovery_codes_regenerated`, `mfa.failed`, `mfa.reset` (commande) | Non |
| Rôles (RG-17 : « changement de rôle ») | `role.granted`, `role.revoked`, `role.reactivated` ; `invitation.created`, `.resent`, `.cancelled`, `.accepted`, `.declined`, `.expired`, `.link_requested` | Oui |
| Paramétrage | `edition.updated`, `edition.status_changed`, `edition.confidentiality_changed` (critique), `track.*`, `submission_type.*`, `key_date.*` | Oui |
| Données personnelles (RG-17 : « export ») | `consent.granted`, `consent.withdrawn`, `account.exported`, `account.anonymized`, `account.deactivated` | Non |
| Opérateur et conservation | `command.<nom>`, avec motif ; `retention.applied` ; `audit.purged`, `audit.network_purged`, `consent.network_purged` | Selon le cas |
| Réservées (L3, L4) | `identity.revealed` (RG-04, levée d'anonymat), `submission.deadline_override` (RG-02), `decision.*`, `export.bulk` | Oui |

Aucune donnée de profil n'apparaît dans `before` et `after` : pour un profil, seule la **liste des champs modifiés** est journalisée.

### 7.4 Consultation

- **Endpoint :** `GET /v1/manage/editions/{id}/audit`, capacité `audit.read`, 2FA.
  - Filtres : action, acteur, type d'objet, période. Tri par `at` décroissant, pagination uniforme.
  - **Ni IP ni user-agent** dans l'API (minimisation).
  - Aucune écriture possible (405), même pour l'`ADMIN`.
- **Écran « Journal »** dans la gestion.
- **Entrées sans édition** (connexions, comptes) et contexte réseau : uniquement par la commande `audit_query`. Un administrateur d'édition ne voit donc pas l'activité des comptes dans les autres éditions.
- **Pas d'export CSV en L1.** Quand il viendra, il sera lui-même journalisé (`export.bulk`).
- **Fil d'activité du CO (M11)** : distinct du journal d'audit, reporté (B7).

### 7.5 Tests

- `test_rg17_role_grant_and_revoke_logged_with_before_after`.
- `test_rg17_invitation_lifecycle_logged`.
- `test_rg17_invitation_snapshot_has_no_clear_email`.
- `test_rg17_confidentiality_change_logged`.
- `test_rg17_data_export_logged`.
- `test_rg17_command_requires_reason`.
- `test_rg17_audit_rolled_back_with_business_transaction`.
- Immuabilité de `AuditLog` **et de `Consent`** : `save` en mise à jour, `delete`, ainsi que `update()` et `delete()` sur le queryset lèvent une exception ; seules les méthodes nommées modifient, et elles sont auditées.
- Aucune adresse e-mail en clair dans `before` et `after` : le test parcourt récursivement les **valeurs** produites par toutes les fabriques d'actions (dont `account.email_added` et `account.email_linked`) et échoue sur toute chaîne de la forme `[^*\s]+@` qui n'est pas au format masqué `x***@domaine`. Les noms de clés `password`, `secret`, `token` restent interdits (égalité stricte) ; `email` est retiré de cette liste, puisque `email_masked` est légitime.
- Lecture limitée à son édition. Les entrées sans édition sont invisibles par l'API.
- La purge du contexte réseau laisse le journal intact.

---

## 8. Tâches asynchrones et e-mails

### 8.1 Choix : une seule file (`Job`), et `OutboxEmail` comme registre

**Tout ce qui est asynchrone est un `Job`** : c'est la règle n° 9 appliquée littéralement. Le moteur de file n'est écrit qu'une fois.

`OutboxEmail` n'est pas une seconde file. C'est le **registre** des e-mails, qui sert :
- au journal d'envoi ;
- aux statistiques d'échec (M12) ;
- à l'anonymisation ;
- à l'écran « File d'envoi » en L3.

Chaque e-mail fait l'objet d'un job `communications.send_email` qui reçoit `{"outbox_id": …}`.

**Mise en file dans la transaction métier.** Une action annulée n'envoie aucun e-mail : c'est le schéma *transactional outbox*.

### 8.2 `run_jobs` : verrou, réservation, reprise

Le schéma est compatible avec MariaDB avant 10.6 : il n'utilise pas `SKIP LOCKED`, que Django ne permet qu'à partir de 10.6 (vérifié), alors que la version d'o2switch est inconnue.

**Classe de base `core.management.LockedCommand`.** `CLAUDE.md` (règle n° 9) et l'étude (§11.5) exigent des commandes cron idempotentes et verrouillées. Le verrou est donc factorisé une fois, et utilisé par `run_jobs`, `cleanup` et `check_integrity` (plus tard `send_reminders`, `sync_payments`, `backup_db`) :
- `fcntl.flock` non bloquant sur `BASE_DIR/tmp/<commande>.lock`, dossier exclu du rsync. Si le verrou est déjà pris, la commande sort sans erreur (code 0) ;
- le comportement de `flock` sur le système de fichiers d'o2switch est **à vérifier** en L1.0 ;
- repli : `GET_LOCK('gestconf.<commande>', 0)`, vérifié sur MariaDB 10.11 en local ; le droit de l'utiliser en mutualisé est **à vérifier** ;
- battement de cœur (`CronHeartbeat`) au début et à la fin ;
- un test par commande vérifie la sortie propre quand le verrou est pris.

**Déroulement de `run_jobs`.**
1. **Verrou de commande** (`LockedCommand`).
2. **Battement de cœur** au démarrage.
3. **Récupération des tâches bloquées.** Un job `running` dont le bail de 15 minutes est dépassé repasse en `pending`, ou en `failed` si `attempts ≥ max_attempts`.
4. **Purge des entrées expirées du cache** (§3.5) : une requête `DELETE` sur `gestconf_cache` où `expires` est dépassé. Django n'offre pas d'API publique pour cela : `_cull` est privée (vérifié).
5. **Boucle dans un budget de temps** (`--max-seconds`, inférieur à l'intervalle du cron) :
   1. sélection d'au plus 20 identifiants éligibles, triés par `priority`, `run_at`, `id` ;
   2. **réservation par une mise à jour conditionnelle** : `filter(pk=…, status=PENDING).update(status=RUNNING, locked_by=…, locked_at=…, attempts=F("attempts")+1)`. Une ligne modifiée signifie que le job est à nous. Deux exécutions simultanées ne traitent donc **jamais** le même job, même si le verrou fait défaut ;
   3. exécution du gestionnaire ;
   4. en cas de succès : `succeeded` et `finished_at`. En cas d'échec : retour en `pending`, avec `run_at` repoussé de 1 min, 5 min, 30 min, puis 2 h ; au-delà de `max_attempts`, statut `failed` et alerte à l'opérateur.
6. **Battement de cœur** de fin : durée, nombre de tâches traitées, dernière erreur.

**Idempotence.** C'est le contrat de chaque gestionnaire, la livraison étant garantie « au moins une fois ». Elle est testée par double exécution. `dedup_key` empêche de programmer deux fois la même tâche.

### 8.3 E-mails

**Chaîne d'envoi.**
1. Pendant la requête, `queue_email(...)` rend le message dans la langue du destinataire. C'est `User.locale` (initialisée à l'inscription) quand l'adresse appartient à un compte, `RoleInvitation.locale` pour une invitation, et sinon la langue de la requête.
2. Une ligne `OutboxEmail` est créée.
3. Un `Job("communications.send_email", dedup_key="email:<id>")` est créé.

**Gestionnaire d'envoi.**
- Il ignore un e-mail déjà `sent`.
- Il passe l'e-mail en `sending` et **valide la transaction avant** d'appeler le fournisseur.
- Il envoie par `EMAIL_BACKEND`. La classe anymail exacte de Brevo ou Mailjet est **à vérifier**.
- Il passe ensuite l'e-mail en `sent` et purge le corps si `is_sensitive`.

**Doublons.** Une panne entre l'acceptation par le fournisseur et la validation peut produire un doublon. C'est rare, assumé et documenté pour des e-mails transactionnels. Le `Message-ID`, dérivé de l'identifiant, permet de les repérer.

**Voie rapide.** Sans elle, une vérification d'adresse attendrait le prochain cron, dont la fréquence est inconnue.
- `queue_email` enregistre, par `transaction.on_commit`, une tentative d'envoi immédiat **pour les seuls gabarits de la liste blanche** ci-dessous. La tentative réserve le job avec la **même réservation conditionnelle**, donc sans doublon possible avec le cron. Hors transaction, `on_commit` s'exécute immédiatement (vérifié) : l'envoi a donc lieu **pendant** la requête HTTP.
- **Sélection par gabarit, pas par priorité (corrigé en v3).** La v2 parlait des « jobs de priorité 0 » tout en listant des gabarits : les deux critères ne coïncidaient pas, et les invitations, de priorité 100, n'auraient jamais pris la voie rapide. Désormais, seul le gabarit compte. Les gabarits de la liste blanche reçoivent aussi la priorité 0, qui ne sert plus qu'à ordonner le cron.
- **Plafond par requête : `FAST_PATH_MAX_PER_REQUEST = 3` (ajouté en v3).** Un compteur propre à la requête, remis à zéro par le middleware d'identifiant de requête, limite les envois immédiats ; les suivants partent au cron. Sans plafond, une création de 50 invitations ferait jusqu'à 50 allers-retours HTTPS vers le fournisseur pendant la requête, soit plusieurs secondes, voire dizaines de secondes, sous Passenger. Test : `test_fast_path_capped_per_request`.
- **Elle est réservée, par une liste blanche de gabarits (`FAST_PATH_TEMPLATES`), aux e-mails envoyés quelle que soit l'existence d'un compte** :
  - à l'inscription, l'e-mail de vérification et l'e-mail « compte existant », dont l'un ou l'autre part dans tous les cas (vérifié) ;
  - les invitations, envoyées dans tous les cas par un membre authentifié, dans la limite du plafond ci-dessus ;
  - les notifications de sécurité d'un utilisateur connecté, dont « adresse ajoutée » ;
  - l'e-mail de liaison d'adresse (RG-20, option (a) de D6, gabarit `role/invitation_link`). Le demandeur est connecté et réauthentifié, et l'e-mail part dans tous les cas où la réponse est 200 : aucun risque d'énumération. S'il attendait le cron (5 min ou plus, R5), la réauthentification de moins de 5 min exigée au clic aurait presque toujours expiré.
- **Elle est exclue pour la réinitialisation du mot de passe.** Avec `EMAIL_UNKNOWN_ACCOUNTS=False`, rien n'est envoyé pour une adresse inconnue (vérifié). Un envoi synchrone pour une adresse connue ajouterait un aller-retour HTTPS vers le fournisseur, soit des centaines de millisecondes : un oracle temporel qui annulerait l'anti-énumération. Ces e-mails attendent le cron (5 min au plus si o2switch le permet, R5), et l'écran le dit.
- **Alternative écartée pour L1 :** lancer la voie rapide après l'envoi de la réponse, par le signal `request_finished`. Son moment exact sous Passenger n'est pas vérifié, et Django ferme les connexions à la base sur ce même signal.
- En cas d'échec, le cron prend le relais.
- Le délai d'attente réseau d'anymail est **à vérifier**, pour ne pas bloquer la réponse HTTP. Le plafond borne le pire cas à trois fois ce délai.

**Gabarits FR/EN.**
- Nom du site fixe.
- Texte et HTML simple, sans image distante.
- Échappement automatique.
- **Contexte en liste blanche.** allauth passe aux gabarits des objets de l'ORM et la requête : `user`, `request`, `current_site`, ainsi que `uid` et `key` pour la réinitialisation (vérifié). `AccountAdapter.send_mail` construit donc, avant le rendu, un contexte réduit à des chaînes :
  - `activate_url`, `password_reset_url`, `signup_url` ;
  - `site_name`, `display_name` ;
  - `timestamp`, formaté dans la langue du destinataire ;
  - pour les alertes de sécurité, `ip` et `user_agent`.

  Les gabarits du projet (`account/email/*`, `mfa/email/*`, `role/*`) ne reçoivent que ce contexte. Sinon, un futur éditeur de modèles (L3) pourrait afficher `{{ user.password }}`. Un test le vérifie sur les gabarits du projet et sur ce contexte filtré.
- **Aucune donnée de personne dans les objets (ajouté en v3).** Les gabarits d'objet (`*_subject.txt`) n'utilisent ni `display_name`, ni adresse, ni nom de l'invitant. L'objet est en effet conservé 12 mois avec les métadonnées d'envoi (D15), alors que les corps sont purgés. Un test rend chaque gabarit d'objet avec des valeurs sentinelles et vérifie qu'aucune n'y apparaît (`test_subject_templates_have_no_personal_data`).

**Plafond global d'envoi par heure** : au-delà, les e-mails sont reportés en file.

**Backends par environnement :**
- `console` en développement ;
- `locmem` en test ;
- anymail en production (D10).

**Suivi par commande :** `manage.py outbox --status failed` et `--retry <id>`. Les webhooks de rebond arrivent en L3.

### 8.4 Cron, `cleanup`, `check_integrity` et supervision

```text
*/5 * * * *  <app>/deploy/cron.sh run_jobs --max-seconds 240   # chaque minute si o2switch le permet (L1.0)
17 3 * * *   <app>/deploy/cron.sh cleanup
47 3 * * *   <app>/deploy/cron.sh check_integrity
```

**`deploy/cron.sh`** charge le **même venv et le même `.env`** que Passenger et journalise dans un fichier. Le chemin du venv cPanel est **à vérifier** ; il sera documenté dans `deploy/README.md`. Les minutes sont décalées pour éviter les heures pleines.

**`cleanup`** (quotidienne) est une `LockedCommand`, idempotente. Elle :
- lance `clearsessions` ;
- fait passer les invitations échues en `expired` ;
- efface l'adresse et le message des invitations expirées, refusées ou annulées depuis plus de 12 mois (en simulation tant que D15 n'est pas validée) ;
- purge les corps d'e-mails (§3.6), les jobs terminés depuis plus de 30 jours, et le contexte réseau de l'audit et des consentements, par leurs méthodes nommées (§7.1) ;
- applique les durées de D15 **en simulation tant qu'elles ne sont pas validées**.

Un résumé est journalisé (audit `retention.applied`).

**`check_integrity`** (**quotidienne**, comme le prévoit l'étude §11.5 ; la v1 la disait hebdomadaire) est une `LockedCommand`. Elle est en lecture seule, donc idempotente, et alerte l'opérateur par e-mail si un contrôle échoue. Contrôles en L1 :
- doublons d'adresses vérifiées et de TOTP, que MariaDB n'empêche pas (W036) ;
- cohérence entre rôles et invitations ;
- taille de la table de cache (alerte au-delà de 20 000 entrées, §3.5) ;
- jobs en `failed`.

Chaque lot y ajoute ses contrôles : scores et grilles (L4), conflits de planning (L5).

**`/v1/health`**, ajouts compatibles avec l'existant :
- `jobs` : `ok`, `late` ou `unknown`. `late` signifie que le dernier succès date de plus de trois intervalles ;
- `cache` : `ok` ou `error`, ce qui détecte un `createcachetable` oublié. Le nombre d'entrées n'est pas exposé publiquement. `cache` a les mêmes valeurs que `database` : les deux champs partagent donc la surcharge de nom `ServiceStatus`, faute de quoi la génération du schéma échouerait (§3.1, §9.5).

Il faut ensuite régénérer le schéma et le client, et adapter `smoke-test.sh`. On propose aussi de retirer de la réponse publique l'empreinte de commit, une fuite d'information mineure relevée en L0. **À valider.**

---

## 9. API

### 9.1 Conventions fixées dans `core` en L1

- **Montage.** Les URL Django sont déclarées sans `/api`, qu'ajoute `config/mount.py`. Pas de barre oblique finale.
- **Pagination.** `StandardPagination` par numéro de page : 25 éléments par défaut, 100 au plus.
- **Filtres et tri.** Toujours explicites, avec un tri déterministe (départage par `id`).
- **Erreurs.**
  - Format `{code, message, fields}`.
  - Les services lèvent des `DomainError`, indépendantes de HTTP : `RuleViolation` → 409, `NotAllowed` → 403, `Invalid` → 400, `QuotaExceeded` → 429 `throttled` (ajoutée en v3). Le gestionnaire d'exceptions existant les traduit. `QuotaExceeded(retry_after=…)` devient un `Throttled(wait=…)` de DRF, qui pose l'en-tête `Retry-After` et garde le code `throttled` (vérifié). Sans elle, le quota d'adresses du §4.7 n'avait aucun chemin vers le 429 annoncé.
  - 401 pour une session absente (D4).
  - `CsrfFailed` (403 `csrf_failed`) levée par notre `SessionAuthentication` et par `CsrfEnforced` (§4.6).
- **Catalogue de codes (`core.errors.ErrorCode`)**, stable et traduit côté Angular :
  - codes existants : `validation_error`, `not_authenticated`, `permission_denied`, `not_found`, `bad_request`, `server_error`, `throttled` ;
  - codes ajoutés : `csrf_failed`, `mfa_required`, `mfa_enrollment_required`, `reauthentication_required`, `last_admin`, `invitation_expired`, `invitation_email_mismatch`, `invitation_email_unverified`, `invitation_link_invalid`, `invitation_self_accept`, `email_address_limit`, `account_has_active_duties`, `edition_archived`, `in_use`.

### 9.2 Authentification (allauth *headless*, client « browser ») : `/api/_allauth/browser/v1/…`

| Méthode | Chemin | Accès | Remarque |
|---|---|---|---|
| GET | `config` | Public | — |
| GET / DELETE | `auth/session` | Public / connecté | GET pose le cookie CSRF (401 si anonyme) ; DELETE = déconnexion |
| POST | `auth/login`, `auth/signup` | Public | Limites (§4.7). Une nouvelle connexion renvoie le lien de vérification d'une adresse non vérifiée (180 s au plus) |
| POST | `auth/reauthenticate` | Connecté | — |
| GET, POST | `auth/email/verify` | Public | Clé dans le corps |
| POST | `auth/email/verify/resend` | — | **Non utilisé** : mode « code » seulement, 409 en mode lien (vérifié par essai) |
| POST / GET, POST | `auth/password/request` / `auth/password/reset` | Public | En-tête `X-Password-Reset-Key`. Pas de voie rapide (§8.3) |
| POST | `account/password/change` | Connecté | Ancien mot de passe exigé (`current_password`), pas de réauthentification (vérifié) |
| GET, POST, PUT, PATCH, DELETE | `account/email` | Connecté ; réauthentification récente pour POST, PATCH et DELETE (`ACCOUNT_REAUTHENTICATION_REQUIRED`, 401 `reauthenticate` sinon) | 3 adresses au plus. Ajout notifié à l'adresse principale (récepteur `email_added`). En mode lien, ajout refusé aux comptes protégés par la 2FA (`add_email_blocked`, vérifié par essai) ; RG-20 passe par §5.7 |
| POST | `auth/2fa/authenticate`, `auth/2fa/reauthenticate` | Flux en cours / connecté | L1.6 |
| GET | `account/authenticators` | Connecté | L1.6 |
| GET, POST, DELETE | `account/authenticators/totp` | Connecté, réauthentification | L1.6. 409 `unverified_email` si une adresse non vérifiée existe |
| GET, POST | `account/authenticators/recovery-codes` | Connecté | L1.6 |
| — | `auth/phone/*`, `account/phone`, `auth/code/confirm`, `auth/2fa/trust`, WebAuthn | — | Fonctions non configurées. Un test vérifie que ces routes ne permettent rien ; le moyen de les neutraliser explicitement est **à vérifier** |

Ces vues sont des vues Django ordinaires : elles n'apparaissent pas dans le schéma drf-spectacular (vérifié). Elles sont couvertes par la façade `AuthApi` et par des **tests de contrat** pytest, qui portent sur les champs réellement consommés : `status`, `data.user`, `data.flows[].id`, `meta.is_authenticated`, `errors[].code` et `param`.

### 9.3 API métier DRF : `/api/v1/…`

| Méthode | Chemin | Accès |
|---|---|---|
| GET | `/v1/health` | Public (ajout de `jobs` et `cache`) |
| GET | `/v1/public/editions/current` | Public, éditions `published` seulement. Inclut les tracks et types actifs et les dates `is_public`. En-tête `Cache-Control`. Sert au test de fumée de §11.4 |
| GET | `/v1/me` | Connecté. Identité, langue, `profile_complete`, état 2FA (`enabled`, `required`, `session_verified`), éditions avec rôles **et capacités**, invitations en attente adressées à ses adresses vérifiées, `privacy_notice_pending` |
| PATCH | `/v1/me/preferences` | Connecté (`locale`) |
| GET / PATCH | `/v1/me/profile` | Connecté |
| GET / POST | `/v1/me/consents` | Connecté (le POST ajoute une ligne) |
| GET | `/v1/me/totp-qr` | Connecté. QR code SVG (`data:image/svg+xml`) du secret TOTP **en attente dans la session**, 404 s'il n'y en a pas. `Cache-Control: no-store` (§10.2) |
| GET | `/v1/me/data-export` | Connecté, réauthentification, limite `data_export` |
| POST | `/v1/me/anonymization` | Connecté, réauthentification, limite `account_deletion` |
| POST | `/v1/invitations/lookup`, `/v1/invitations/decline` | Public avec jeton, `CsrfEnforced`, limite `invitation` |
| POST | `/v1/invitations/accept` | Connecté, limite `invitation`. Corps `{token}`, ou `{link}` avec **réauthentification récente**. RG-20 (§5.7) |
| POST | `/v1/invitations/link-email` | Connecté, **réauthentification récente**, limite `invitation_link`. Envoie le lien de liaison à l'adresse invitée (§5.7 ; option (a) de D6) |
| GET | `/v1/manage/editions` | Connecté, **sans 2FA** (D3). Vue à part, `ManageEditionListView` (§5.3). Éditions où l'on a au moins une capacité de gestion ; champs non sensibles (id, code, titres, année, statut) ; alimente le sélecteur |
| GET / PATCH | `/v1/manage/editions/{edition_id}` | `edition.read` / `edition.write`, 2FA |
| POST | `/v1/manage/editions/{edition_id}/status` | `edition.publish` / `edition.archive`, 2FA, réauthentification |
| GET / PATCH | `/v1/manage/editions/{edition_id}/confidentiality` | Lecture / écriture, 2FA, réauthentification pour l'écriture |
| GET, POST ; GET, PATCH, DELETE | `/v1/manage/editions/{edition_id}/tracks` ; `…/tracks/{track_id}` | `edition.read` / `edition.write`, 2FA |
| Idem | `…/submission-types` ; `…/submission-types/{type_id}` | Idem |
| Idem | `…/key-dates` ; `…/key-dates/{key_date_id}` | Idem (`at_local`) |
| GET | `…/roles` | `members.read`, 2FA. Queryset filtré selon le rôle ; sérialiseur avec ou sans e-mail |
| POST | `…/roles/{role_id}/revoke` | `members.manage` (§5.5), 2FA, réauthentification, motif |
| GET / POST | `…/invitations` | `members.read` / `members.manage`, 2FA. Liste filtrée selon le rôle (`SC_CHAIR` : invitations `SC_MEMBER`). Création : limite `invitation_create`, sur la seule création, et quota d'adresses (429 `throttled`, §4.7) |
| POST | `…/invitations/{invitation_id}/resend`, `…/cancel` | `members.manage`, 2FA |
| GET | `…/audit` | `audit.read`, 2FA |

### 9.4 Commandes `manage.py`

Toutes sont auditées (`actor_kind=command`), avec un motif obligatoire quand l'action est sensible.

| Famille | Commandes |
|---|---|
| Amorçage | `create_conference`, `create_edition --admin-email`, `set_current_edition` |
| Rôles | `grant_role`, `revoke_role` |
| Comptes | `sync_email_addresses`, `reset_mfa`, `deactivate_user`, `reactivate_user`, `anonymize_user`, `export_user_data` |
| Audit | `audit_query` |
| E-mails | `outbox`, `send_test_email` |
| Clés | `rotate_mfa_keys` |
| Exploitation (cron, `LockedCommand`) | `run_jobs`, `cleanup`, `check_integrity` |

Un compte créé par commande reçoit une `EmailAddress(verified=True, primary=True)`.

### 9.5 Schéma OpenAPI et client TypeScript

- Après chaque endpoint : `python manage.py spectacular --file schema.yml --validate --fail-on-warn`, puis `npm run api:generate`. La CI compare les deux (existant).
- `ENUM_NAME_OVERRIDES` est posé **dès L1.1**, puis complété à chaque nouveau jeu de choix. Liste prévue pour L1 (complétée en v3 ; la v2 n'en citait que six) :
  - santé : `HealthStatus` (`status`), `ServiceStatus` (commun à `database` et `cache`, qui ont les mêmes valeurs, car une surcharge s'applique à un jeu de choix), `JobsStatus` ;
  - rôles et invitations : `Role`, `InvitableRole` (si le sérialiseur d'invitation restreint `role` aux 5 rôles invitables, ce qui provoquerait sinon une « collision »), `UserRoleStatus`, `RoleSource`, `OcFunction`, `InvitationStatus` ;
  - édition : `EditionStatus` ;
  - compte : `ConsentKind`, `ConsentSource`, `ProfileTitle`, `Locale` (`User.locale` et `RoleInvitation.locale`) ;
  - audit : `ActorKind`, si l'API du journal l'expose ;
  - erreurs : `ErrorCode` (`ApiError.code`).

  C'est indispensable : sans surcharge, un renommage peut passer la CI sans avertissement, ou au contraire la faire échouer (§3.1). Le champ `country` est contrôlé par un validateur, sans `choices`, pour ne pas produire une énumération de 249 valeurs. Renommer `StatusEnum` en `HealthStatus` et `DatabaseEnum` en `ServiceStatus` ne touche que le client généré, qu'on régénère (vérifié).
- **Méta-test `test_every_schema_enum_has_explicit_name`** (ajouté en v3). Il génère le schéma et échoue si un composant d'énumération ne porte pas un nom déclaré dans `ENUM_NAME_OVERRIDES`, à l'exception de `BlankEnum` et `NullEnum`, que drf-spectacular ajoute pour les choix vides ou nuls (vérifié). Un oubli est ainsi détecté même quand drf-spectacular ne dit rien.
- Le composant `ApiError` est déclaré avec `code` en énumération : le client obtient un type union, et un test front vérifie que chaque code a une traduction. Le mécanisme global (`POSTPROCESSING_HOOKS`, qui existe, ou `extend_schema` sur une classe de base) est **à vérifier**. À défaut, il est déclaré vue par vue.
- `SPECTACULAR_SETTINGS["VERSION"]` est aligné sur la version du projet.

---

## 10. Frontend

### 10.1 Bibliothèque `shared`

```text
shared/src/lib/
  api/          (généré, jamais édité à la main)
  http/         provideGestconfApi() + intercepteurs :
                  acceptLanguage  (Accept-Language = langue courante ; sert aussi à l'inscription)
                  apiError        (DRF {code,message,fields} et allauth {status,errors[]} → ApiError,
                                   traduit par shared.errors.<code>, message serveur en repli)
                  session         (401 sous /api/v1/ SEULEMENT → état anonyme + connexion avec next ;
                                   401 sous /api/_allauth/ : laissé à AuthApi, qui lit data.flows et
                                   meta.is_authenticated (verify_email, mfa_authenticate, reauthenticate,
                                   amorçage, déconnexion) ;
                                   csrf_failed → GET auth/session puis une seule nouvelle tentative ;
                                   mfa_required → vérification 2FA ;
                                   mfa_enrollment_required → /compte/securite ;
                                   reauthentication_required → dialogue puis une seule nouvelle tentative)
  auth/         auth-api.ts (façade allauth typée à la main), session.store.ts et me.store.ts (signaux),
                authGuard et capabilityGuard (CanMatchFn), safe-next.ts (même règle que le serveur),
                active-context.ts (édition et rôle actifs, ergonomiques)
  ui-kit/       jetons --gc-* (déplacés depuis les deux styles.scss), thème Material (§10.5),
                gc-page-header, gc-confirm-dialog, gc-bilingual-fields, applyServerErrors(form, ApiError),
                formatage de date dans le fuseau de l'édition (Intl.DateTimeFormat)
  i18n/         (existant) + clés shared.auth.*, shared.errors.*
testing         provideAuthTesting({ me }) en plus de provideI18nTesting (existant)
```

**Pourquoi l'intercepteur distingue les deux préfixes.** Pour allauth, un 401 fait partie du protocole : il signale par exemple l'étape 2FA de la connexion. Un intercepteur qui redirigerait sur tout 401 casserait cette étape, ou bouclerait. Depuis la v3, la gestion des adresses renvoie aussi un 401 portant le flux `reauthenticate` ou `mfa_reauthenticate` (§4.3) : la façade ouvre alors la fenêtre de réauthentification, puis rejoue la requête une seule fois, comme pour le 403 `reauthentication_required` de DRF.

**Conventions.**
- Les composants n'appellent jamais `HttpClient` directement. Chaque fonctionnalité a un petit service de données qui utilise le client généré (`inject(Api).invoke(fn)`).
- Formulaires réactifs typés.
- État local en signaux, sans bibliothèque de gestion d'état. L'usage de `httpResource` d'Angular est **à vérifier**.

**Gardes de route : de l'ergonomie, jamais de la sécurité** (règle n° 2). Elles s'appuient sur les capacités renvoyées par `/me`.

### 10.2 Portail : espace compte

Routes `/compte/*` en `RenderMode.Client`, marquées `noindex` et chargées à la demande. Les composants Material ne sont chargés que par ces routes (code découpé à la demande). Le **thème** Material est traité au §10.5 : il n'est pas non plus dans les styles initiaux du portail.

| Route | Écran |
|---|---|
| `/compte/connexion` | Connexion, avec l'étape 2FA |
| `/compte/inscription` | Inscription, avec la notice d'information |
| `/compte/verifier-email` | Lecture de la clé dans le fragment, puis vérification ; écran « consultez vos e-mails », dont le bouton « renvoyer » est un formulaire de reconnexion (§4.3) |
| `/compte/mot-de-passe-oublie`, `/compte/reinitialiser` | Réinitialisation (l'e-mail part au passage suivant du cron) |
| `/compte/double-authentification` | Saisie d'un code TOTP ou d'un code de secours (connexion et *step-up*) |
| `/compte` | Accueil : éditions et rôles, invitations en attente, état de la 2FA, accès à la gestion ; première connexion (notice, profil minimal) |
| `/compte/profil` | Profil et langue (enregistrée par `PATCH /me/preferences`) |
| `/compte/securite` | Mot de passe (ancien mot de passe exigé), adresses e-mail (réauthentification récente), enrôlement TOTP (avec gestion de `unverified_email`), codes de secours |
| `/compte/confidentialite` | Notice, consentements (historique, retrait) |
| `/compte/mes-donnees` | Export, anonymisation |
| `/compte/invitation` | Consultation, acceptation ou refus d'une invitation ; liaison de l'adresse invitée (RG-20, avec réauthentification récente). L'écran prévient qu'une nouvelle réauthentification sera demandée si le lien est ouvert plus de 5 min après la demande |

S'y ajoutent `public/robots.txt` et un indicateur « connecté » dans l'en-tête.

**QR code de l'enrôlement.**
- `GET …/authenticators/totp` renvoie `totp_url` sans image (vérifié).
- **Choix arrêté en v2 : génération côté serveur, sans dépendance nouvelle.** `GET /v1/me/totp-qr` lit le secret en attente dans la session. allauth l'y range sous la clé interne `mfa.totp.secret`, figée par un test de contrat comme `at` (§4.5). L'endpoint appelle ensuite les méthodes publiques `MFAAdapter.build_totp_url` et `build_totp_svg` (vérifié). Cette dernière utilise `qrcode`, déjà installé par l'extra `mfa` (licence BSD, pur Python, vérifié).
- Aucun script tiers, donc aucune question de licence JavaScript ni de compatibilité CSP. Le secret ne transite jamais dans une URL. `segno` reste réservé aux badges (L7).
- L'image est renvoyée en `data:image/svg+xml`, ce que permet la CSP (`img-src 'self' data:`).
- La clé en texte, avec un bouton de copie, reste disponible pour l'accessibilité.

### 10.3 Gestion

**Coque commune** : sélecteur d'édition, sélecteur de rôle actif, langue, menu utilisateur, déconnexion, navigation filtrée par les capacités.

| Route | Écran | Capacité (garde) |
|---|---|---|
| `/gestion/` | Redirige vers la dernière édition utilisée, ou vers le sélecteur | Connecté avec au moins une capacité |
| `/gestion/editions/:editionId` | Redirige vers le tableau de bord avec `edition.read`, sinon vers « Membres » avec `members.read`. C'est le cas du `SC_CHAIR` si D8 n'est pas acceptée | Au moins une capacité dans l'édition |
| `…/tableau-de-bord` | Accueil récapitulatif (squelette US-12) : dates clés, paramétrage à compléter, invitations en attente, état de la 2FA. **Pas d'indicateurs** (L4) | `edition.read` |
| `…/parametrage/{general,thematiques,types,calendrier,confidentialite}` | Paramétrage (§6) : champs bilingues, saisie à l'heure de l'édition avec double affichage | `edition.read` / `edition.write` |
| `…/comites/membres`, `…/comites/invitations` | Membres et rôles, invitations (relancer, annuler), révocation | `members.read` / `members.manage` |
| `…/audit` | Journal filtrable et paginé, détail avant/après | `audit.read` |
| Pages d'erreur | Accès refusé ; « 2FA requise », qui renvoie vers `/compte/securite` | — |

**Pas d'écran de connexion dans la gestion** : redirection complète vers `/compte/connexion?next=…` (D11).

### 10.4 Session côté Angular

- **Aucun jeton stocké.** `localStorage` ne sert qu'aux préférences (langue, édition active), avec gestion des erreurs.
- **Démarrage de la gestion :** `provideAppInitializer` appelle `GET auth/session`, puis `GET /v1/me` si l'utilisateur est connecté.
- **Portail :** l'état de session est lu uniquement dans `afterNextRender`, jamais pendant le pré-rendu.
- **Après la connexion,** `LanguageService` adopte `me.locale`. Un changement de langue envoie ensuite `PATCH /v1/me/preferences`.
- **Réponse 401 inattendue sous `/api/v1/`** (session expirée, y compris par la limite de 12 h) : message « session expirée », vidage des stores, retour à la connexion avec `next`.
- **Déconnexion :** rechargement complet de la page.

### 10.5 i18n, accessibilité, kit UI

**i18n.**
- Aucune chaîne en dur.
- Clés `shared.*`, `portail.*`, `gestion.*`.
- **Test de parité des clés FR/EN** dans `npm test`.
- Test « chaque `ApiError.code` a une traduction ».
- Côté serveur : `LocaleMiddleware`, messages et e-mails en `.po`, `.mo` versionnés (gettext est probablement absent d'o2switch, **à vérifier**).

**Accessibilité (WCAG 2.1 AA).**
- Composants Material ; lien d'évitement et `main#contenu` conservés.
- Focus sur le premier champ en erreur, résumé des erreurs, zone `aria-live` pour les messages asynchrones.
- Navigation au clavier dans les dialogues de réauthentification et de 2FA.
- Contrastes vérifiés sur les jetons du thème.
- Règles ESLint de gabarits (existantes) et liste de contrôle manuelle à chaque démo. Audit axe automatisé en L3.

**Kit UI et thème : choix explicite.** La v1 affirmait à la fois que Material n'était chargé que par `/compte` et que son thème était global. Les deux sont incompatibles : un thème injecté dans les `styles` du portail alourdit le CSS initial de **toutes** les pages pré-rendues.
- **Gestion :** thème Material dans les styles globaux. C'est nécessaire, à cause du budget de 4 kB de styles par composant.
- **Portail :** le thème **n'est pas** dans les styles initiaux. Il est compilé dans une feuille séparée, déclarée dans `styles` avec `inject: false` (option vérifiée dans `@angular/build` 22.2.1). La coque de `/compte` charge cette feuille au premier affichage par un `<link rel="stylesheet">`, ce que permet `style-src 'self'`. Les pages publiques pré-rendues ne paient donc rien. Deux points sont **à vérifier** en L1.4 : le nom du fichier produit, haché ou non, et l'absence de clignotement à l'affichage.
- Les jetons `--gc-*`, légers, restent dans `shared/ui-kit` et dans les styles initiaux des deux applications.
- **Budget `initial` propre au portail**, resserré à la taille mesurée en L1.1 plus 10 %. Les budgets actuels (500 kB / 1 MB) sont communs aux deux applications.
- La version 22 de l'API de thème Sass est **à confirmer**.
- Polices système en attendant l'identité visuelle ; icônes SVG hébergées localement (`font-src 'self'`). Paquet d'icônes et licence **à vérifier**.

---

## 11. CI/CD et exploitation

| Ajout | Détail |
|---|---|
| **Correctif L0 (bug vérifié)** | `deploy.sh` lance `npx ng build portail && npx ng build gestion` sans `inject-csp.mjs` : **la CSP à empreintes n'est pas posée en production.** Remplacer par `npm run build`. Corriger le commentaire obsolète `autoCsp` dans le `.htaccess` |
| `deploy.sh` | Sauvegarde avant `migrate` (dès qu'il existe des données réelles) ; `createcachetable` après `migrate` ; envoi des `.mo` ; `deploy/cron.sh` |
| Tests de fumée | CSP en `<meta>` sur `/` et `/gestion/` ; `GET /api/_allauth/browser/v1/auth/session` → 401 JSON et cookie `csrftoken` posé ; `/api/v1/public/editions/current` → 200 (ou 404 attendu sans édition publiée) ; `/health` avec `jobs` et `cache` ; `X-Robots-Tag` sur `/api/`. **Pas** de connexion réelle, qui exigerait un compte de production (C6) |
| Dépendances Python | `django-allauth[mfa]` (version figée ; apporte `qrcode`), `django-anymail[<fournisseur>]`, `tzdata`. Verrouillage **avec empreintes** via pip-tools (`.in` → `.txt --generate-hashes`), parce que des dépendances binaires transitives arrivent (`cryptography`, `cffi`). pip-tools n'a pas été installé lors des essais : **à vérifier**. `pip-audit` sur le fichier verrouillé (existant) |
| Contrôles backend | ruff (existant) ; `makemigrations --check` (existant) ; migrations dans les deux sens ; pytest sur SQLite et **MariaDB**, avec des tests marqués `mariadb` pour le cache, les verrous, les CHECK, l'unicité et la longueur des clés ; `check --deploy --fail-level WARNING` (existant, non concerné par W036) ; schéma DRF validé et comparé (existant) |
| Couverture | `pytest-cov` (**à vérifier**, non installé lors des essais), seuil ≥ 80 % sur `accounts/services`, `accounts/permissions`, `core/audit`, `core/jobs`, `conferences/services`, `communications/services` |
| i18n | gettext installé dans la CI : `compilemessages`, puis vérification que les `.mo` versionnés sont à jour |
| Contrat allauth | Tests pytest sur les réponses consommées par la façade, sur la structure des enregistrements d'authentification (`at`), sur la clé `mfa.totp.secret`, sur la réauthentification exigée par `account/email` et sur l'émission d'`email_added` ; version d'allauth figée ; liste de contrôle pour chaque montée de version |
| Frontend | Tests, lint, prettier, build, budgets (dont le budget `initial` propre au portail), comparaison `api:generate` (existants) ; parité i18n ; traduction de chaque code `ApiError` |
| Secrets | Aucun secret dans le dépôt (existant). Nouvelles variables dans `.env.example` sans valeur. Rotation documentée. Outil de détection de secrets en CI : **à vérifier** (option) |
| Déploiement depuis la CI | **Hors de L1 : écart de périmètre à valider** (D18 ; l'étude §14.1 place CI/CD en L1). En L1, `deploy.sh` manuel ; la CI publie le `dist` comme artefact. CD prévu dans une étape dédiée avant l'ouverture de l'appel (L3) |
| Documentation | `deploy/README.md` (trois lignes de cron, variables, rotation, procédure `reset_mfa`, sauvegarde) ; `docs/L1-socle.md` (décisions, écarts) ; brouillon du registre des traitements |
| Branches | **`git fetch` d'abord**, car l'`origin/main` local est périmé. Branche L1 depuis `main` à jour, **une PR par étape**, CI au vert, messages de commit en français |
| Node | La version locale (22.22.0) ne respecte pas `engines` (`^22.22.3`) : mettre à jour le poste de développement |

---

## 12. Tests

**Règle.** Toute RG implémentée est citée dans le nom ou la docstring de son test. RG concernées en L1 :
- **RG-17**, implémentée ;
- **RG-18**, en partie : l'anonymisation sur demande (M2 et M17) est implémentée, la purge par durée de conservation ne l'est pas ;
- **RG-20**, proposée et implémentée sous réserve de validation (D6) ;
- **RG-04 n'est pas implémentée en L1.** L1 en fournit les mécanismes génériques (filtrage par rôle, sérialiseurs selon les capacités, tri explicite, matrice), testés pour leurs usages L1. Les tests dédiés à RG-04 arrivent au début de L4 (§5.4).

### 12.1 Unitaires et services (pytest-django)

- **Rôles :**
  - `grant_role` idempotent : une seule ligne et une seule entrée d'audit ;
  - réactivation ;
  - `test_last_admin_cannot_be_revoked` ;
  - refus de modifier ses propres rôles ;
  - `test_grantors_table[<rôle>]` (paramétré) ;
  - `test_capabilities_table_covers_every_role` ;
  - `edition_access` en une requête SQL (test du nombre de requêtes).
- **Contraintes, sur MariaDB :**
  - `test_userrole_oc_function_check_constraint` ;
  - `test_userrole_unique_with_oc_function` ;
  - `test_invitation_single_pending_via_nullable_unique_key` ;
  - `test_invitation_pending_key_fixed_length_with_254_char_email`.
- **Invitations :**
  - jeton jamais stocké en clair ;
  - expiration ; `test_invitation_expired_on_the_fly_unblocks_new_invitation` ;
  - `test_rg20_accept_requires_verified_matching_email` ;
  - `test_rg20_bare_token_does_not_grant_role` : un compte sans l'adresse reçoit 409 `invitation_email_unverified`, et aucun rôle n'est créé ;
  - `test_rg20_mfa_user_links_second_address_via_signed_link` : un `CHAIR` avec TOTP, invité à une seconde adresse, obtient le rôle par le lien de liaison, et l'adresse est ajoutée comme vérifiée. Le test vérifie aussi que l'ajout par allauth aurait renvoyé `add_email_blocked` ;
  - `test_rg20_link_token_bound_to_requesting_account` (lien rejoué par un autre compte → 400) et lien expiré → 400 `invitation_link_invalid` ;
  - `test_rg20_link_requires_recent_reauth_and_notifies_primary` (ajouté en v3) : `link-email` et `accept {link}` sans réauthentification récente → 403 `reauthentication_required` ; après réauthentification, l'acceptation met en file l'e-mail « adresse ajoutée » vers l'adresse principale, dans la même transaction que l'audit `account.email_linked`, et rien n'est envoyé si la transaction est annulée ;
  - `test_rg20_address_verified_on_other_account_refused` ;
  - limite de 3 adresses → 409 `email_address_limit` ;
  - double acceptation refusée ;
  - `test_inviter_cannot_accept_own_invitation` (ajouté en v3) : 403 `invitation_self_accept`, aucune adresse liée, aucun rôle ;
  - refus sans compte ;
  - nouvelle invitation possible après un refus ;
  - `test_invitation_quota_and_throttle_scope` (ajouté en v3) : 25 consultations de la liste en une heure → 200 ; 21e création → 429 ; 101e adresse dans l'heure → 429 `throttled` avec `Retry-After`.
- **Permissions et sessions :**
  - `MfaVerified` dans ses trois cas ;
  - `RecentAuthRequired` (horodatage `at`, structure figée) ;
  - `CsrfEnforced` : POST anonyme sans en-tête → 403 `csrf_failed` ;
  - `test_add_email_requires_recent_reauth` (ajouté en v3) : `POST account/email` sans réauthentification récente → 401 avec le flux `reauthenticate`, aucune adresse ajoutée ;
  - `test_absolute_session_timeout` : une session modifiée à 11 h 59 est refusée à 12 h 01 ; une session authentifiée sans `gc_login_at` est fermée ;
  - validateur de `next` avec des chaînes malveillantes paramétrées.
- **Paramétrage :**
  - ordre des dates clés ;
  - fuseau invalide ;
  - `test_key_date_local_time_conversion` sur `Africa/Abidjan` et `Europe/Paris` (heure inexistante ou ambiguë) ;
  - format de `Edition.code` ;
  - EN exigé à la publication ;
  - transitions et préconditions du statut ;
  - `is_call_open`.
- **Profil :** `test_orcid_checksum[...]`, `test_country_iso3166`.
- **Audit :** `test_rg17_*` (§7.5), immuabilité de `AuditLog` et de `Consent`, listes blanche et noire de clés.
- **Tâches :**
  - réservation exclusive entre deux exécutions ;
  - délais croissants ;
  - `failed` après `max_attempts` ;
  - récupération après expiration du bail ;
  - `dedup_key` ;
  - gestionnaire exécuté deux fois sans effet ;
  - `LockedCommand` : verrou déjà pris → sortie propre, pour `run_jobs`, `cleanup` et `check_integrity` ;
  - budget de temps ;
  - battement de cœur ;
  - purge des entrées expirées du cache.
- **E-mails :**
  - mise en file par `send_mail` ;
  - rendu dans la langue du destinataire ;
  - `test_signup_with_accept_language_en_sends_english_verification` ;
  - corps sensible purgé après l'envoi ;
  - aucun envoi si la transaction est annulée ;
  - contexte en liste blanche : les gabarits du projet ne reçoivent que des chaînes ;
  - voie rapide limitée à `FAST_PATH_TEMPLATES`, sélection par gabarit et non par priorité ; la réinitialisation du mot de passe n'y figure pas, l'e-mail de liaison d'adresse (RG-20) y figure ;
  - `test_fast_path_capped_per_request` (ajouté en v3) : création de 50 invitations → au plus 3 appels au backend d'e-mail pendant la requête, les autres jobs restent `pending` ;
  - `test_email_added_notifies_primary` et `test_password_reset_not_sent_to_unverified_secondary_address` (ajoutés en v3) ;
  - `test_subject_templates_have_no_personal_data` (ajouté en v3) ;
  - repli sur la file si l'envoi immédiat échoue ;
  - plafond horaire.
- **Données personnelles :**
  - `test_rg18_anonymize_user_removes_personal_data` ;
  - `test_rg18_anonymization_leaves_no_original_identity` : balayage de toutes les colonnes texte, y compris `OutboxEmail.to_email` et `subject`, les invitations traitées et leur `message` (reçues comme envoyées), les clichés d'audit et `django_session` décodée. Les fabriques injectent volontairement le nom et l'adresse dans ces champs de texte libre ;
  - `test_rg18_anonymization_is_idempotent` ;
  - refus `account_has_active_duties` ;
  - `test_personal_data_registry_covers_all_user_fks` (introspection) ;
  - l'export contient chaque section et aucun secret ;
  - `cleanup` idempotente et sans effet en mode simulation.
- **Chiffrement :**
  - aller-retour de l'adaptateur MFA ;
  - la colonne brute de `mfa_authenticator` ne contient pas le secret.

### 12.2 API et droits

- **Matrice §5.9** (environ 90 à 130 cas nommés, dont ceux de la liste des éditions), `test_every_manage_route_is_in_matrix`, et `test_manage_response_order_401_404_403_mfa`.
- **Schéma :** `test_every_schema_enum_has_explicit_name` (§9.5).
- **Garde-fous de plateforme** (§5.9).
- **Assignation de masse :** les champs interdits sont ignorés ou refusés.
- **Édition :** écriture sur une édition archivée → 409 ; édition en brouillon et date interne invisibles par `/public`.
- **Invitations :** un `SC_CHAIR` ne voit que les invitations `SC_MEMBER`.
- **`/me` :**
  - non connecté → **401** ;
  - ne renvoie que ses propres rôles actifs et les capacités correspondantes ;
  - `PATCH` de la langue.
- **Format :**
  - toute réponse 4xx sous `/v1` respecte `{code, message, fields}` ;
  - échec CSRF → `csrf_failed` en JSON, **testé séparément** pour allauth (vue d'échec), pour DRF connecté (`SessionAuthentication`) et pour DRF anonyme (`CsrfEnforced`), avec `enforce_csrf_checks=True` ;
  - `ScopedRateThrottle` et `QuotaExceeded` → 429 `throttled`, avec `Retry-After`.
- **Parcours allauth par le client de test :**
  - inscription → e-mail **en file** → clé lue dans la file → vérification → connexion → session → déconnexion → ancien cookie refusé (401) ;
  - renvoi du lien de vérification par reconnexion ; `auth/email/verify/resend` répond 409 en mode lien ;
  - réinitialisation ;
  - gestion des adresses : ajout sans réauthentification récente → 401 `reauthenticate` ; après réauthentification → 200 et notification de l'adresse principale ;
  - anti-énumération : réponses identiques ;
  - `test_no_timing_oracle_on_signup_and_password_request` : adresse connue ou inconnue, même nombre d'appels au backend d'e-mail pendant la requête (zéro pour `password/request`) et même nombre de hachages de mot de passe ;
  - `too_many_login_attempts` ;
  - clé de session renouvelée à la connexion ;
  - sessions invalidées au changement de mot de passe ;
  - liens des e-mails sur `GESTCONF_PUBLIC_URL` malgré un `Host` forgé ;
  - clé dans le fragment ;
  - routes du client `app` absentes ;
  - routes `phone`, `code` et `trust` inertes.
- **2FA (L1.6) :**
  - `mfa_enrollment_required`, puis `mfa_required`, puis 200 après la réauthentification 2FA ;
  - activation refusée (`unverified_email`) tant qu'une adresse non vérifiée existe ;
  - `/v1/me/totp-qr` : 404 sans secret en attente, SVG sinon, `Cache-Control: no-store` ;
  - auteur non concerné ;
  - suppression du TOTP → `/manage` exige un réenrôlement ;
  - rejeu d'un même code refusé.
- **Tests L0 adaptés :**
  - `test_unauthenticated_access` passe à 401 ;
  - `test_api_requires_authentication_by_default` passe en test d'inclusion si nécessaire.

### 12.3 Intégration (MariaDB en CI)

- Cache partagé entre deux connexions : limites de débit et anti-rejeu TOTP.
- `GET_LOCK` ; présence des contraintes CHECK et d'unicité par introspection.
- Clé `pending_key` avec une adresse de 254 caractères : insertion sans erreur ni troncature.
- Doublons d'adresses vérifiées non empêchés par la base (W036) : vérification que le service ou allauth les refuse (comportement d'allauth **à vérifier**, sinon contrôle dans nos services) ; `check_integrity` les détecte.
- `run_jobs` de bout en bout avec le backend `locmem`, deux exécutions de suite sans double effet.
- Commandes `create_conference`, `create_edition`, `grant_role`, `reset_mfa`, `anonymize_user`, `export_user_data`, `check_integrity` : effet et audit.
- Migration depuis l'état L0 avec un compte existant, puis `sync_email_addresses`.
- Tests de fumée sur l'environnement déployé.

### 12.4 Frontend (Vitest)

- **Intercepteurs :**
  - normalisation des deux formats d'erreur ;
  - redirections selon le code ;
  - une seule nouvelle tentative (CSRF, réauthentification) ;
  - **401 avec le flux `mfa_authenticate` sous `/_allauth/` : pas de redirection** ;
  - 401 sous `/api/v1/` → connexion avec `next`.
- **Façade et état :** `AuthApi` testée avec `HttpTestingController` ; stores.
- **Navigation :** gardes ; `safe-next` (cas de redirection ouverte) ; `ActiveContextService` avec stockage indisponible ; redirection d'un détenteur de `members.*` sans `edition.read` vers « Membres ».
- **Formulaires et i18n :** `applyServerErrors` ; parité des clés i18n.
- **Composants :** formulaires de compte (validation, attributs d'accessibilité), enrôlement 2FA, invitations (dont la liaison d'adresse).
- **Thème :** la feuille du thème est absente du HTML des pages publiques pré-rendues et chargée par `/compte`.

**E2E Playwright :** reporté en L3, avec le parcours auteur (§1.3).

---

## 13. Découpage en étapes livrables

Chaque étape donne **une PR** :
- CI au vert : ruff, pytest sur SQLite et MariaDB, schéma validé, client régénéré ;
- déployable sur la recette ;
- un critère de fin vérifiable.

| Étape | Contenu | Critère de fin vérifiable | j-h |
|---|---|---|---|
| **L1.0 Préalables et vérifications o2switch** | `git fetch`, branche depuis `main` à jour. Script en lecture seule sur le serveur : `SELECT VERSION()` (MariaDB ≥ 10.5 exigé par Django 5.2) ; **`SELECT @@sql_mode` et `check --database default`** (avertissement `mysql.W002`) ; `ldd --version` (glibc ≥ 2.17) ; `pip install --only-binary=:all: cryptography fido2` dans un venv jetable ; journalisation temporaire de `REMOTE_ADDR` et `X-Forwarded-For` ; `flock` dans `tmp/` ; `GET_LOCK` ; fréquence minimale du cron ; chemin du venv cPanel ; HTTPS sortant vers le fournisseur d'e-mails ; limite d'upload ; présence de gettext et de `mysqldump`. Décisions consignées | Fiche `docs/L1-verifications-o2switch.md` remplie ; décisions bloquantes validées | 0,75 – 1 |
| **L1.1 Socle transverse et dettes L0** | `DatabaseCache` (`MAX_ENTRIES=50000`) + `createcachetable` ; 401 ; **CSRF en JSON sur les trois chemins** (`CSRF_FAILURE_VIEW` pour allauth, `SessionAuthentication` avec `CsrfFailed`, permission `CsrfEnforced`) ; `LocaleMiddleware` et `.po` ; `ENUM_NAME_OVERRIDES` (liste complète et méta-test) et `ApiError` ; `DomainError` (dont `QuotaExceeded`), `Actor`, `StandardPagination` ; `ScopedRateThrottle` et `GESTCONF_TRUSTED_PROXY_COUNT` ; `conftest.py` et fabriques ; méta-tests ; correctif CSP de `deploy.sh` et tests de fumée ; `robots.txt` et `X-Robots-Tag` ; verrouillage des dépendances ; `pytest-cov` ; mesure du CSS initial du portail et budget dédié | Sur la recette, le test de fumée détecte la CSP en `<meta>` ; une requête anonyme reçoit 401 en JSON ; un POST DRF connecté sans jeton reçoit 403 `csrf_failed` ; 429 obtenu sur MariaDB | 1,5 – 2 |
| **L1.2 Audit, file, e-mails, cron** | `core/0001`, `communications/0001` ; `AuditLog` + `record` ; `Job`, registre, **`LockedCommand`**, `run_jobs` (dont la purge des entrées expirées du cache), battement de cœur ; `OutboxEmail` + `send_email` + voie rapide **en liste blanche, plafonnée à 3 envois par requête** ; anymail ; `cron.sh` ; squelette de `cleanup` ; `/health` ; alerte minimale aux opérateurs (D17) ; `send_test_email` | **J-tech :** sur o2switch, `send_test_email` met un e-mail en file, le **cron** l'envoie par le fournisseur, il arrive dans la boîte de réception (SPF/DKIM valides) ; `/health` → `jobs: ok` ; tests d'exclusivité et de verrou au vert | 2,25 – 2,75 |
| **L1.3 Comptes (backend)** | Réglages allauth et sessions (§4.2), dont **`ACCOUNT_REAUTHENTICATION_REQUIRED`**, **middleware d'expiration absolue** et `gc_login_at` ; adaptateur : `send_mail` (contexte en liste blanche, gabarits FR/EN, pas de réinitialisation vers une adresse secondaire non vérifiée), `save_user` (langue), **hachage égalisé** du chemin « compte existant » ; **notification « adresse ajoutée »** (récepteur `email_added`) ; signaux d'audit ; `Profile`, `Consent` (immuable) ; `/v1/me…` ; `sync_email_addresses`, `deactivate_user`, `audit_query` ; tests de contrat | Parcours inscription → vérification → connexion → profil → déconnexion vert en pytest ; e-mails uniquement via la file, dans la langue de la requête ; anti-énumération (réponses, envois synchrones, hachages) et CSRF testés ; expiration absolue testée ; ajout d'adresse refusé sans réauthentification récente (401) et notifié à l'adresse principale | 3,25 – 3,75 |
| **L1.4 Socle front et pages de compte** | Material et thème (feuille non injectée dans le portail), `ui-kit`, intercepteurs (401 limité à `/api/v1/`), `ApiError`, façade `AuthApi`, stores, gardes, `safe-next`, outils de test ; pages `/compte/*` (sauf 2FA et invitation) : connexion, inscription, vérification et renvoi, mot de passe oublié et réinitialisation, accueil et première connexion, profil ; `noindex` | **Démo A sur o2switch :** une personne crée un compte depuis le portail **avec un navigateur en anglais**, reçoit l'e-mail de vérification en anglais, vérifie, se connecte, prend connaissance de la notice, complète son profil, change de langue (mémorisée), réinitialise son mot de passe (e-mail reçu au passage suivant du cron) ; `audit_query` montre ces actions ; budgets respectés et thème absent des pages publiques | 4 – 5 |
| **L1.5 Éditions, rôles, permissions (backend)** | App `conferences` et migrations de FK d'édition (§3.8) ; `create_conference`, `create_edition`, `grant_role`, `revoke_role` ; `Role`, `Capability`, `UserRole`, `RoleInvitation` (`pending_key` en empreinte, expiration à la volée) ; services (attribution, invitations avec quota et `QuotaExceeded`, **RG-20 avec lien de liaison**, réauthentification et notification comprises, statut de l'édition) ; `HasCapability`, `EditionScopedViewMixin` (édition chargée dans `check_permissions`), `MfaVerified` (inactive tant que `allauth.mfa` n'est pas installé), **`RecentAuthRequired`** (avancée de L1.6 en v3 : elle ne dépend que d'`allauth.account`, installé en L1.3, et la révocation, la publication et la liaison RG-20 en ont besoin dès L1.5) ; endpoints `/v1/manage/editions/{id}/**` (membres et invitations filtrés par rôle, limite de création par action), `ManageEditionListView`, `/v1/invitations/**`, `/v1/public/editions/current` ; harnais de matrice et test de complétude | Matrice entièrement au vert, y compris l'ordre 401/404/403 ; test de complétude au vert ; `test_rg17_*` des rôles et du paramétrage au vert ; `test_rg20_*` au vert ; client régénéré ; le test de fumée `public/editions/current` passe | 3,75 – 4,25 |
| **L1.6 2FA et réauthentification** | `allauth.mfa`, chiffrement du secret, `MfaVerified` activée, réauthentification par TOTP (`RecentAuthRequired` est livrée en L1.5), notifications, `reset_mfa`, `rotate_mfa_keys` ; `GET /v1/me/totp-qr` ; écrans `/compte/securite` (dont `unverified_email`) et `/compte/double-authentification` ; fenêtre de réauthentification | Un `CHAIR` sans 2FA reçoit `mfa_enrollment_required`, puis `mfa_required`, puis 200 après la vérification ; un auteur n'est pas concerné ; secret chiffré en base ; rejeu refusé ; QR code affiché sans dépendance ajoutée | 1,5 – 2 |
| **L1.7 Écrans de gestion et invitations** | Coque, sélecteurs, redirection vers la connexion, redirection d'édition selon les capacités, tableau de bord squelette, 5 écrans de paramétrage, membres et invitations, journal ; `/compte/invitation` dans le portail (consultation, acceptation, refus, liaison d'adresse) | **Démo B sur o2switch :** l'administrateur d'édition (`ADMIN`, invité par commande) active la 2FA, paramètre l'édition en FR/EN et la publie (`/api/v1/public/editions/current` la renvoie) ; il invite un président du CS sans compte, qui s'inscrit, accepte, active la 2FA, arrive sur « Membres » (ou sur le tableau de bord si D8 est acceptée) et invite un relecteur ; le relecteur accepte et reçoit un refus (403) sur le paramétrage ; le journal montre l'état avant/après | 4 – 5 |
| **L1.8 Données personnelles et clôture** | Registre et test d'introspection, export, **anonymisation étendue** (registre d'envoi et objets des e-mails, invitations traitées et leurs messages, sessions) et **test de balayage**, en libre-service et par commande ; `cleanup` complet (en simulation selon D15) ; `check_integrity` **quotidienne** ; écrans `/compte/mes-donnees` et `/compte/confidentialite` ; trois lignes de cron ; `deploy/README.md`, `docs/L1-socle.md` ; PR de mise à jour de l'étude et de `CLAUDE.md` (§15) ; déploiement final | `test_rg18_*`, test d'introspection et test de balayage au vert ; couverture ≥ 80 % sur les modules critiques ; tests de fumée au vert en production ; cron actifs depuis 48 h sans battement de cœur en retard | 1,75 – 2,25 |
| **Total** | | | **22,75 – 28** |

**Ordre et chemin critique.** Les jalons correspondent au milieu des fourchettes cumulées.
- L1.0 → L1.1 → L1.2 (**J-tech**, cumul 4,5 à 5,75 j-h, ≈ j5) → L1.3 → L1.4 (**Démo A**, cumul 11,75 à 14,5 j-h, ≈ j13) → L1.5 → L1.6 → L1.7 (**Démo B**, cumul 21 à 25,75 j-h, ≈ j23) → L1.8 (cumul 22,75 à 28 j-h, ≈ j25).
- La 2FA (L1.6) arrive **avant** les écrans de gestion : la démo B se fait donc dans les conditions réelles.
- La partie front de L1.4 peut commencer en parallèle de la fin de L1.3.
- **Dépendances des lots suivants :** L2 dépend de L1.5 (données et endpoint public). L3 dépend de L1.2, L1.3 et L1.5. L4 dépend de L1.6 et L1.7.
- **Pourquoi J-tech si tôt :** dès la première semaine, il lève les inconnues qui pourraient remettre en cause l'hébergement : cron, délivrabilité, `cryptography`, IP derrière le proxy, `sql_mode`.

**D'où vient la hausse par rapport à la v1 (19 à 23 j-h, somme exacte 18,75 à 23).**

| Étape | v1 | v2 | Raison |
|---|---|---|---|
| L1.2 | 2 – 2,5 | 2,25 – 2,75 | `LockedCommand`, purge du cache, voie rapide en liste blanche |
| L1.3 | 2,5 – 3 | 3 – 3,5 | Expiration absolue, langue à l'inscription, contexte filtré, égalisation du hachage et tests |
| L1.4 | 3 – 3,5 | 4 – 5 | Réestimation : thème, kit UI, trois intercepteurs, façade, stores, gardes, outils de test et environ huit pages, à environ 0,3 j-h par page tests et i18n compris ; feuille de thème séparée |
| L1.5 | 3 – 3,5 | 3,5 – 4 | Lien de liaison RG-20 (+0,5), quota et filtrage des invitations, ordre des contrôles ; préparation de RG-04 retirée (−0,25) |
| L1.7 | 3 – 3,5 | 4 – 5 | Réestimation : une douzaine d'écrans, dont cinq de paramétrage bilingues avec saisie en heure locale ; liaison d'adresse dans `/compte/invitation` |
| L1.8 | 1,5 – 2 | 1,75 – 2,25 | Anonymisation étendue et balayage, immuabilité de `Consent` |
| L1.0, L1.1, L1.6 | inchangées | inchangées | Contenu modifié, sans effet notable sur la charge |

**Hausse de la v3 (+0,5 j-h).**

| Étape | v2 | v3 | Raison |
|---|---|---|---|
| L1.3 | 3 – 3,5 | 3,25 – 3,75 | `ACCOUNT_REAUTHENTICATION_REQUIRED` et son test, récepteur `email_added` et gabarit FR/EN, réinitialisation refusée vers une adresse secondaire non vérifiée |
| L1.5 | 3,5 – 4 | 3,75 – 4,25 | +0,25 j-h répartis entre cinq travaux : réauthentification et notification de la liaison RG-20 (0,1 à 0,15), refus d'accepter sa propre invitation, `QuotaExceeded` et limite par action, `ManageEditionListView` et ses cases de matrice |
| L1.1, L1.2, L1.8 | inchangées | inchangées | Méta-test des énumérations, plafond de la voie rapide, anonymisation des objets et des messages : absorbés dans les fourchettes |

**Écart avec l'étude (15 à 20 j-h, §14.3).** Il vient surtout :
- des vérifications o2switch restées ouvertes depuis L0 ;
- de l'adaptation d'allauth *headless* (contrat, file d'e-mails, imposition de la 2FA, expiration absolue, anti-énumération par le temps) ;
- de la correction de la CSP ;
- des écrans (B21). L1.4 et L1.7 représentent 8 à 10 j-h, soit environ 35 % de la charge. C'est cohérent avec la part de 30 à 35 % que l'étude attribue aux écrans qui remplacent l'admin Django (§14.3).

Environ 7 à 9 j-h ont été **reportés** vers L2, L3 et L4 (§1.3) pour tenir cette charge. Le déploiement continu sort aussi de L1 (D18). Le diagramme de Gantt de l'étude prévoit 28 jours calendaires pour L1.

**Variante courte (≈ 20,5 à 25,75 j-h) : scénario de repli décidé d'avance.** Chaque réduction est réversible.

| Réduction | Étape | Gain |
|---|---|---|
| Journal d'audit consultable par commande seulement (pas d'écran) | L1.7 | −1 |
| Export et anonymisation par commande seulement (pas d'écran « Mes données ») | L1.8 | −0,75 |
| Tableau de bord réduit à la liste des éditions ; sélecteur de rôle actif supprimé | L1.7 | −0,5 |
| **Déconseillé :** 2FA reportée au début de L4 | L1.6 | −1,5 à −2 |

**Règle de déclenchement (à valider dans D18).** Si J-tech n'est pas atteint à **j7** (prévu ≈ j5), ou la démo A à **j15** (prévu ≈ j13), les trois premières réductions s'appliquent sans nouvelle décision. Elles sont signalées dans la PR de l'étape suivante et dans `docs/L1-socle.md`.

**Je déconseille de reporter** la 2FA, les tests de la matrice ou le verrouillage des dépendances : ils ne font jamais partie du repli.

---

## 14. Risques et hypothèses non vérifiées

### 14.1 Risques

| # | Risque | Probabilité / impact | Parade |
|---|---|---|---|
| R1 | `cryptography` / `fido2` (paquets manylinux2014, glibc ≥ 2.17) ne s'installent pas sur o2switch | Faible / **élevé** (2FA) | Essai en L1.0. Repli : `django-otp` et une étape maison (+3 à 4 j-h) |
| R2 | MariaDB d'o2switch en version inférieure à 10.5 (incompatible Django 5.2), ou à 10.6 | Faible / **bloquant** ou nul | L1.0 ; la file n'utilise pas `SKIP LOCKED` |
| R3 | IP client masquée par un proxy : compteur de débit commun à tous, IP fausses dans l'audit | Moyenne / élevé | Mesure en L1.0, `GESTCONF_TRUSTED_PROXY_COUNT` ; **production bloquée sans cette mesure** |
| R4 | Délivrabilité ; domaine encore inconnu (Q15) | Moyenne / élevé | D10 tôt, SPF/DKIM/DMARC, jalon J-tech |
| R5 | Cron limité à une exécution toutes les 5 min ou plus | Moyenne / faible | Voie rapide `on_commit` pour les e-mails envoyés dans tous les cas, 3 par requête au plus ; la réinitialisation du mot de passe attend le cron, et l'écran le dit |
| R6 | `flock` non fiable, ou `GET_LOCK` interdit | Faible / faible | La réservation conditionnelle par ligne empêche déjà tout double traitement ; `cleanup` et `check_integrity` sont idempotentes |
| R7 | Contraintes conditionnelles non créées par MariaDB (allauth ×3) | Certaine / moyen | Tests sur MariaDB, `check_integrity` quotidienne, contrôle dans les services si allauth ne refuse pas |
| R8 | Une montée de version d'allauth change le contrat *headless* | Moyenne / moyen | Version figée, tests de contrat (dont `at`, `mfa.totp.secret`, la réauthentification de `account/email` et le signal `email_added`), PR dédiée à chaque montée |
| R9 | Perte de la clé de chiffrement MFA | Faible / élevé | Sauvegarde séparée hors hébergement, codes de secours, `reset_mfa` |
| R10 | Faible adoption de la 2FA, perte de téléphone avant une échéance | Moyenne / moyen | `SC_MEMBER` non contraints en L1, codes de secours, guide, `reset_mfa` audité, pas de verrouillage permanent |
| R11 | Cadre légal (ARTCI, RGPD) et lieu d'hébergement (Q14) | Faible / **très élevé** | Question à poser maintenant ; durées paramétrables, purges en simulation ; L1 ne traite que des données de démonstration |
| R12 | Charge encore sous-estimée (écrans qui remplacent l'admin, B21) | Moyenne (après réestimation de L1.4 et L1.7) / moyen | Réestimation v2, variante courte décidée d'avance avec seuils de déclenchement (j7, j15), PR par étape, démos |
| R13 | Données réelles avant une sauvegarde testée | Moyenne / élevé | D18 : comptes de démonstration, ou sauvegarde avancée en L1 |
| R14 | Coût CPU de PBKDF2 (1 000 000 itérations, vérifié) au pic de connexions en mutualisé. L'égalisation du temps de l'inscription ajoute un hachage par inscription avec une adresse existante | Faible / moyen | Test de charge en L9 ; la limite `signup` borne le surcoût. Argon2 exigerait un module binaire |
| R15 | Poids du thème Material dans le portail | Faible / faible | Thème hors des styles initiaux du portail (feuille non injectée), budget `initial` propre au portail en CI |
| R16 | XSS sur le portail donnant accès à l'API de gestion (domaine et cookie partagés) | Faible / élevé | CSP à empreintes sur les deux applications (corrigée en L1.1), pas de texte riche, pas de script tiers |
| R17 | Dépendance à une seule personne | Moyenne / moyen | Documentation, tests, une PR par étape |
| R18 | Saturation du cache en base : un tiers des clés (compteurs de débit, anti-rejeu TOTP) supprimé par ordre alphabétique au-delà de `MAX_ENTRIES` | Faible / moyen | `MAX_ENTRIES=50000`, purge des entrées expirées à chaque `run_jobs`, alerte de `check_integrity` au-delà de 20 000 entrées (§3.5) |
| R19 | `sql_mode` non strict sur o2switch : troncature silencieuse au lieu d'une erreur | Inconnue / moyen | Vérification en L1.0 (`mysql.W002`) ; clés de longueur fixe (empreintes) ; longueurs validées dans les sérialiseurs. Si besoin, mode strict demandé à la connexion par `OPTIONS["init_command"]`, réglage documenté par Django mais dont l'acceptation par o2switch est **à vérifier** |
| R20 | Oracle temporel d'énumération (inscription : hachage seulement pour un nouveau compte ; envoi synchrone d'e-mail) | Certaine sans parade / moyen | Hachage factice dans le chemin « compte existant », voie rapide en liste blanche, tests de comptage ; écart résiduel de quelques millisecondes sur `password/request` (§4.11) |

### 14.2 Hypothèses non vérifiées, et quand on les vérifie

| Hypothèse | Vérification |
|---|---|
| glibc ≥ 2.17, `pip` et paquets binaires disponibles ; HTTPS sortant vers le fournisseur | L1.0 |
| Version de MariaDB ; **`sql_mode`** ; droit d'utiliser `GET_LOCK` ; tables de fuseaux (`CONVERT_TZ`, C9, non utilisé ici) | L1.0 |
| `flock` fiable ; fréquence minimale du cron ; chemin du venv cPanel pour le cron | L1.0 |
| Nombre de processus Passenger ; en-têtes ajoutés par le proxy | L1.0 |
| Limite d'upload ; gettext et `mysqldump` disponibles ; sauvegardes cPanel | L1.0 (et D18) |
| SSH depuis les runners GitHub ; restriction de commande dans `authorized_keys` | Avant l'étape qui accueillera le CD (D18) |
| Connexion après vérification si une connexion est en attente dans la même session | L1.3 (test) |
| Chaîne d'appel complète du chemin « compte existant » de l'inscription, donc point exact de l'égalisation du hachage | L1.3 (test de comptage) |
| Prise en compte effective de `PASSWORD_RESET_TIMEOUT` par allauth ; usage unique de la clé | L1.3 (test) |
| Refus par allauth d'une seconde adresse vérifiée identique (W036) | L1.3 (test sur MariaDB) |
| Signatures des signaux allauth et MFA | L1.3, L1.6 |
| Moyen de neutraliser explicitement `auth/phone/*` et `auth/code/*` | L1.3 |
| `MultiFernet.rotate` pour la rotation ; délai réseau d'anymail ; nom de la classe du backend Brevo ou Mailjet | L1.2, L1.6 |
| Déclaration globale d'`ApiError` (`POSTPROCESSING_HOOKS` ou `extend_schema`) | L1.1 |
| pip-tools, `pytest-cov` | L1.1 |
| API de thème Sass Material 22 ; feuille non injectée (nom de fichier, affichage) ; paquet et licence des icônes ; licence de `tzdata` ; `httpResource` d'Angular | L1.4 |
| Pérennité de la structure des enregistrements d'authentification (`at`) et de la clé de session `mfa.totp.secret` | Figées par des tests de contrat |
| Seulement si l'option (b) de D6 est retenue : délai du code adapté à la fréquence réelle du cron, comportement avec `SESSION_EXPIRE_AT_BROWSER_CLOSE`, parade à l'oracle temporel du renvoi | Avant L1.3 |

**Tranchés en v2, retirés de cette liste :**
- `csrf_protect` sur une `APIView` : sans effet (§4.6) ;
- bibliothèque de QR code : `qrcode`, déjà installé (§10.2) ;
- réponse identique de l'inscription avec une adresse existante : confirmée par essai, mais avec un écart de temps, qui est traité (§4.3).

**Tranchés en v3, retirés de cette liste ou corrigés :**
- réauthentification exigée par allauth pour les adresses : non, sauf avec `ACCOUNT_REAUTHENTICATION_REQUIRED=True` (vérifié par essai ; §4.2) ;
- conditions du blocage `add_email_blocked` : levé aussi par le mode « code » (vérifié par essai ; D6) ;
- avertissements de nommage des énumérations de drf-spectacular : deux cas distincts, l'un constaté par essai (§3.1) ;
- `sql_mode` de MariaDB : la v2 le disait par erreur « vérifié en L1.0 » au §3.1 ; il reste **à vérifier** en L1.0.

---

## 15. Mises à jour proposées de l'étude (et de `CLAUDE.md`)

Ces mises à jour seront livrées par une PR de documentation en L1.8, **après votre validation**. Rien ne sera modifié de façon silencieuse.

1. **§1.2 n° 3, §7.2, A4, `CLAUDE.md` (tableau de la stack)**
   - 2FA par `allauth.mfa` (TOTP et codes de secours) au lieu de `django-otp`, si D2 est validée.
   - Dépendance binaire `cryptography` ; secret TOTP chiffré ; `qrcode` pour l'enrôlement.
   - `django.contrib.messages` et `contrib.sites` sont inutiles.
   - Même correction dans `docs/L0-prototype-deploiement.md`.
2. **M2**
   - 2FA en P1 (L1) pour `ADMIN`, `CHAIR`, `SC_CHAIR` et `OC_MEMBER` ; `SC_MEMBER` selon D3. Cela supprime la contradiction avec §14.1.
   - Profil : photo et réseaux en L2, spécialités en L4 (en relationnel), « titre » à la place de « civilité ».
3. **§3.1, §3.2, §7.3, A5**
   - L'« administrateur technique » agit par commandes auditées.
   - `create_platform_admin` est remplacée par `create_conference`, `create_edition` et `grant_role`.
   - `ADMIN` est un rôle d'édition.
   - Les invitations génériques vivent dans `accounts`, et `committees` (L4) ne porte que les données propres aux comités.
4. **§3.3**
   - Table des capacités (§5.2) et matrice d'attribution (§5.5).
   - Colonnes `SPEAKER` à `VOLUNTEER`.
   - Lignes « son compte », « membres », « invitations », « exports ».
   - Rôles soumis à la 2FA.
   - Lecture du paramétrage par le `SC_CHAIR` (D8, B20).
   - « Partiel » du CO renvoyé à Q12.
   - La matrice est codée, non paramétrable.
   - Question d'un rôle `TRACK_CHAIR` (B5).
5. **§6**
   - **RG-19 proposée** : `double_blind` et `code` gelés après `call_open`, modification par un `ADMIN` avec motif et audit (implémentée en L3).
   - **RG-20 proposée** : une invitation ne s'accepte que depuis un compte qui contrôle l'adresse invitée, soit par une adresse vérifiée correspondante, soit par un lien de confirmation envoyé à cette adresse, lié au compte et soumis à une réauthentification récente (option (a) de D6), soit par l'ajout préalable de l'adresse, vérifiée par code (option (b)). Le jeton d'invitation seul ne suffit pas.
   - **RG-17** : catalogue d'actions (§7.3), aucune donnée personnelle ni adresse en clair dans avant/après, IP purgeable par méthodes nommées.
   - **RG-18** : distinguer le compte, transverse aux éditions, des données d'une édition ; l'anonymisation couvre aussi les registres d'envoi, les invitations et les sessions ; conflits avec les conservations légales (factures RG-14, actes) à trancher.
6. **§8.2 et §8.3**
   - Tous les écarts du §3.7.
   - Limites de MariaDB : pas d'unicité conditionnelle (convention de la « clé d'unicité nullable », en empreinte de longueur fixe), NULL distincts, pas d'index sur expression, `sql_mode` à vérifier.
   - Exception INT et CASCADE pour les tables tierces.
   - Pas de table générique de paramètres.
   - Compteurs reportés en L3 ; `Consent.edition` en L3.
7. **§9.1**
   - 401 pour une session absente.
   - Catalogue des codes d'erreur, dont `csrf_failed` sur allauth et DRF.
   - Coexistence avec l'enveloppe d'erreur d'allauth, normalisée côté client ; un 401 d'allauth est un état du protocole.
8. **§9.2**
   - Authentification sous `/_allauth/browser/v1/…`, déconnexion par `DELETE auth/session`, renvoi de vérification par reconnexion en mode lien.
   - `/manage/editions/{id}/…`, avec le Chair ajouté aux rôles d'accès à `/manage`.
   - Endpoints `/me/*` (dont `totp-qr`), `/invitations/*` (dont `link-email`), audit par édition.
   - `/public/key-dates` intégré à `/public/editions/current`.
9. **§9.3**
   - « Verrouillage progressif » remplacé par une limitation temporaire par compte et par IP, plus une alerte, sans verrouillage permanent.
   - Cache partagé obligatoire (et son risque de purge), mesure de l'IP derrière le proxy.
   - Expiration absolue des sessions à 12 h, imposée côté serveur.
   - Réauthentification récente pour la gestion des adresses e-mail (`ACCOUNT_REAUTHENTICATION_REQUIRED`) et notification de tout ajout d'adresse.
   - Anti-énumération y compris par le temps de réponse.
   - CSRF des POST anonymes par une permission dédiée (`csrf_protect` est inopérant sous DRF).
   - Quota d'invitations.
   - Chiffrement applicatif et rotation des clés.
   - Anti-robots selon D16.
10. **§10.1 et §10.2**
    - Ajout de « Mes données », « Invitation » et du sélecteur d'édition.
    - « Rôles et permissions » devient « Membres et rôles ».
    - Pas d'écran « Utilisateurs » global.
    - « Exports RGPD » : libre-service plus commande opérateur.
    - Écrans de compte dans le portail (D11).
11. **M3 et §5.1**
    - Les états automatiques déclenchés par les dates arrivent en L3 et L4.
    - Règle des échéances : 23 h 59 heure de l'édition, saisie convertie côté serveur (D13), avec la nuance correspondante dans `CLAUDE.md`.
    - Contenus paramétrés en `_fr` / `_en` (D14).
12. **M11** : le fil d'activité du CO est distinct du journal d'audit (B7).
13. **§11.2, §11.4, §11.5, §11.7**
    - Points à vérifier sur o2switch : MariaDB ≥ 10.5, `sql_mode`, glibc et paquets binaires, IP derrière le proxy, `flock` et `GET_LOCK`, SSH depuis la CI.
    - `npm run build` (CSP), `createcachetable`, sauvegarde avant `migrate`, `.mo` versionnés.
    - `cron.sh` ; `run_jobs` avec voie rapide en liste blanche ; `cleanup` détaillée (dont `clearsessions`) ; `check_integrity` **quotidienne** ; commandes cron verrouillées par une classe commune (`LockedCommand`).
    - Battement de cœur dans `/health`.
    - Tests de fumée sans compte de production (C6).
14. **§12 et A6** : Vitest au lieu de Jest ou Karma (C5) ; E2E à partir de L3.
15. **§14.1 et §14.3**
    - Choix du fournisseur d'e-mails déplacé de L0 vers L1 (D10).
    - Liste des reports de L1 vers L2, L3 et L4 (§1.3), dont la préparation spécifique de RG-04 (début de L4).
    - **CI/CD : le déploiement continu sort de L1 (écart de périmètre, D18).** L1 garde l'intégration continue. Lot de destination : une étape dédiée avant l'ouverture de l'appel (L3), idéalement en tête de L2, après vérification du SSH depuis les runners.
    - Charge de L1 réestimée à 22,75–28 j-h, dont 8 à 10 j-h d'écrans ; variante courte (20,5–25,75 j-h) comme repli décidé d'avance, avec ses seuils de déclenchement.
16. **A3** : histoires utilisateur L1 à ajouter (inscription, invitation d'un relecteur, paramétrage, consultation de l'audit, anonymisation).
17. **§15.1 (nouvelles questions)**
    - Fournisseur d'e-mails et domaine.
    - Kit UI.
    - Bibliothèque et périmètre de la 2FA.
    - Mode de vérification des adresses (lien ou code) et rattachement d'une adresse invitée à un compte 2FA (D6).
    - Autorité de plateforme.
    - Durées de conservation par catégorie.
    - Fournisseur anti-robots.
    - Environnement de recette.
    - Version et `sql_mode` de MariaDB, fréquence du cron.
    - Outil de supervision des erreurs (tiers).
    - Procédure de vérification d'identité avant `reset_mfa`.
    - Sauvegardes avant les données réelles.
    - Règle de déclenchement de la variante courte.
    - Lot d'accueil du déploiement continu.

---

## 16. Écarts constatés pendant l'implémentation (L1.0 à L1.2)

Consignés ici pour ne pas dériver en silence (CLAUDE.md). Les écarts marqués **à valider** attendent
l'accord du commanditaire ; les autres sont des précisions sans effet sur les décisions D1 à D18.
Ils seront repris dans la PR de documentation de L1.8 (§15).

1. **§9.1, catalogue `ErrorCode`.** Quatre codes s'ajoutent à la liste : `parse_error`,
   `method_not_allowed`, `not_acceptable` et `unsupported_media_type`. Ce sont les codes par défaut
   des exceptions de DRF que l'API produit déjà (corps JSON illisible, méthode refusée, en-tête
   `Accept` ou type de contenu refusé) ; sans eux, `ApiError.code` aurait reçu des valeurs hors de
   l'énumération. Les codes des étapes suivantes (`mfa_required`, `invitation_*`…) n'entrent dans le
   catalogue qu'avec le code qui les émet.
2. **§7.2, `Actor`.** Le constructeur s'appelle bien `Actor.command(nom)`, comme prévu (un premier
   jet l'avait nommé `for_command`, corrigé).
3. **§13, critère de fin de L1.1 (à valider).** « Une requête anonyme reçoit 401 en JSON ; un POST
   DRF connecté sans jeton reçoit 403 `csrf_failed` ; 429 obtenu sur MariaDB » n'est pas vérifiable
   **sur la recette** : aucun endpoint protégé ni limité en débit n'y est déployé avant L1.3 et L1.5.
   Reformulation proposée : « vérifié par pytest sur MariaDB en CI ; sur la recette, le test de fumée
   détecte la CSP en `<meta>`, le cache OK, `X-Robots-Tag`, `robots.txt` et le diagnostic désactivé ».
   Le test de fumée `GET /api/_allauth/browser/v1/auth/session` → 401 (§11) arrive avec L1.3.
4. **§3.5 et R18, cache partagé : deux tables au lieu d'une (à valider).** Les compteurs des limites
   DRF ont leur propre table, `gestconf_throttle_cache` (alias `throttle`,
   `apps.core.throttling.ScopedRateThrottle`), créée elle aussi par `createcachetable`. La purge de
   Django supprime les clés **par ordre alphabétique** : dans une table commune, une inondation de
   compteurs anonymes `throttle_invitation_<ip>` effaçait d'abord les clés `allauth…` (limites de
   débit, anti-rejeu TOTP) et les compteurs `throttle_account_deletion_…`. Elle ne peut plus purger
   que des compteurs DRF. Conséquences pour L1.2 : la purge des entrées expirées de `run_jobs` et
   l'alerte de `check_integrity` (au-delà de 20 000 entrées) couvrent **les deux tables**.
5. **§4.7 et §4.11, sonde `/health`.** `/health` est public et sans limite de débit ; la sonde du
   cache (écriture, lecture, suppression dans les deux tables, chaque écriture précédée d'un
   `SELECT COUNT(*)`) est donc **mémorisée 10 s par processus**. Les écritures dues à la sonde sont
   bornées quel que soit le trafic ; une panne du cache apparaît avec au plus 10 s de retard.
6. **§9.5.** `SPECTACULAR_SETTINGS["VERSION"]` est lu dans `backend/pyproject.toml` (source unique) :
   le schéma passe de `1.0.0` à `0.1.0`.
7. **§11, déploiement.** Les contrôles passent **avant** `migrate` (un avertissement n'arrête plus
   le déploiement entre deux migrations, le DDL n'étant pas transactionnel sous MariaDB), en deux
   commandes : `check --deploy --fail-level WARNING`, toujours **sans** `--database` comme le prévoit
   le §3.7 (sinon `models.W036` des contraintes conditionnelles d'allauth bloquerait les déploiements
   dès L1.3), puis `check --database default --tag database --fail-level WARNING`, qui ne lance que
   les contrôles de la base (connexion, `mysql.W002`). Le code Django envoyé est celui du
   commit (`git archive`), jamais un fichier ignoré du poste. Le garde-fou CSP couvre toutes les pages
   HTML du build. Le test de fumée vérifie que le diagnostic de L1.0 est désactivé (404).
8. **§11, CI.** pytest tourne sur MariaDB (la suite refuse de démarrer hors MariaDB grâce à
   `GESTCONF_REQUIRE_MARIADB=1`) **et** sur SQLite ; `prod.txt` est téléchargé en roues
   `manylinux2014` pour chaque version de Python, comme l'installe `deploy.sh` ; le `dist` Angular est
   publié comme artefact (D18).
9. **Fiche L1.0.** Les décisions d'hébergement s'appellent H-1 à H-11 (et non D-1 à D-11, qui se
   confondaient avec D1 à D18). Contrôle ajouté : V27, format de ligne InnoDB (`DYNAMIC` et pages
   ≥ 8 Kio, sans quoi `migrate` échoue sur les index utf8mb4 longs).
10. **`CLAUDE.md`, section « Commandes » (proposition, à valider ; fichier non modifié).** Ajouter
    `python manage.py createcachetable` après `migrate`, `requirements/compile.sh` (verrouillage
    avec empreintes), `locale/check.sh` (traductions de l'API) et `deploy/check-o2switch.sh`
    (vérifications de l'hébergement, lecture seule).

### Étape L1.2 (audit, file, e-mails, cron)

11. **§3.5, `CronHeartbeat`.** Deux colonnes s'ajoutent : `last_success_at` (date du dernier
    passage **réussi**, sur laquelle `/health` calcule `jobs: late`, alors que `last_finished_at`
    couvre aussi les échecs) et `last_error` (nature de l'erreur seulement).
12. **§7.2, `record`.** Le paramètre `edition` et l'index (`edition`, `at`) arrivent en L1.5 avec
    la FK (§3.8). Les garde-fous sur `before`/`after` sont appliqués **à chaque écriture**, et non
    seulement par un test : clé interdite (`password`, `secret`, `token`, `key`, `otp`,
    `totp_secret`, à toute profondeur) ou adresse e-mail en clair dans une valeur →
    `AuditDataError`. Seule la forme masquée `x***@domaine` (`mask_email`) passe. Un modèle
    photographié par `snapshot` doit déclarer `AUDIT_FIELDS`, sinon `TypeError`.
13. **§8.3, gabarits.** Registre `register_email_template(code, sensitive=…, fast_path=…)` :
    `is_sensitive`, la priorité du job (0 si sensible ou voie rapide) et la liste blanche
    `FAST_PATH_TEMPLATES` (calculée, `fast_path_templates()`) **découlent du gabarit**, jamais de
    l'appelant. Un gabarit non déclaré est refusé. Le code d'un gabarit est le préfixe de ses
    fichiers (`account/email/email_confirmation`), à la manière d'allauth, et non une forme pointée
    (`account.email_confirmation`). Le test `test_subject_templates_have_no_personal_data` parcourt
    **tous** les gabarits déclarés, y compris ceux des lots suivants.
14. **§8.3, plafond de la voie rapide.** Le budget de 3 envois par requête est porté par un
    middleware dédié, `EmailFastPathMiddleware` (variable de contexte), et non par
    `RequestIdMiddleware` : hors requête (commandes, cron), aucun budget, donc aucune voie rapide.
15. **§8.2 et §3.6, `last_error`.** Seule la **nature** de l'erreur est conservée (classe de
    l'exception), jamais son message, qui peut contenir l'adresse du destinataire (refus du
    fournisseur). Le détail va dans le journal du serveur.
16. **§8.4, `/health` (à valider).** `jobs: late` ne fait pas passer `status` à `degraded` ni la
    réponse à 503 : un cron arrêté n'empêche pas l'API de répondre. Le test de fumée exige en
    revanche `jobs: ok` ; il échoue donc au tout premier déploiement, tant que la crontab n'a pas
    tourné une fois (documenté dans `deploy/README.md`). Le retrait de l'empreinte de commit de
    `/health`, proposé au §8.4, n'est pas fait (toujours à valider).
17. **§8.4, `cleanup`.** Les purges sont déclarées par chaque application
    (`register_retention_task`, `apps/core/retention.py`) : `core` ne dépend d'aucune application
    métier. Une purge **imposée par la sécurité** (corps d'e-mails à jeton non envoyés après 24 h,
    §3.6) s'applique toujours ; les durées de D15 restent en simulation tant que
    `GESTCONF_RETENTION_ENFORCED` est faux. `cleanup`, lancée par le cron, est journalisée sous
    l'acteur `Actor.system("cron:cleanup")` : préfixe `cron:`, à côté de `cli:` et `job:`.
    `check_integrity` reste en L1.8 (§13) : `deploy/cron.sh` n'accepte pour l'instant que
    `run_jobs` et `cleanup`, la troisième ligne de cron arrive avec elle.
18. **§8.4, `deploy/cron.sh`.** Liste fermée de commandes ; sorties dans
    `logs/cron-<commande>.log` (rotation à 5 Mio), rien sur la sortie standard. Le chemin du venv
    cPanel (V22) n'est pas codé en dur : `deploy.sh` l'écrit dans `VENV_ACTIVATE`, à côté de
    `RELEASE`, et le script est extrait du commit déployé (`git show`), comme le code Django.
19. **D17, mécanisme précisé.** `apps.core.alerts.OperatorAlertHandler`, branché sur
    `django.request` (erreurs 5xx), n'envoie que le type d'exception, le **motif de route
    résolu** (jamais le chemin brut, qui pourrait porter un jeton), la méthode, le statut et
    l'identifiant de requête. Envoi direct (`mail_admins`), hors file, pour qu'une alerte parte
    même base ou file en panne ; plafond de 10 par heure (`GESTCONF_OPERATOR_ALERTS_PER_HOUR`).
    Les opérateurs sont lus dans `GESTCONF_OPERATORS` (liste d'adresses), qui alimente `ADMINS`.
    Les mêmes alertes signalent une tâche en échec définitif et une commande cron en erreur.
20. **D10, dépendances.** `django-anymail==15.2` (sans extra : ceux de Brevo et Mailjet
    n'ajoutent rien) apporte `requests`, `urllib3`, `certifi`, `idna` et `charset-normalizer`,
    tous en roues pures. Vérifié dans le code installé : classes
    `anymail.backends.brevo.EmailBackend` et `anymail.backends.mailjet.EmailBackend` ; délai
    réseau par `ANYMAIL["REQUESTS_TIMEOUT"]` (30 s par défaut), réglé à (3,05 s ; 10 s). En
    production, `GESTCONF_EMAIL_BACKEND` et `DEFAULT_FROM_EMAIL` sont obligatoires.
21. **`outbox --retry`.** Le job existant (`dedup_key` unique) est remis en attente, tentatives
    à zéro, plutôt que d'en créer un second. Un e-mail dont le corps à jeton a été purgé ne peut
    pas être renvoyé : le destinataire doit le redemander.
22. **Critère de fin de L1.2 (J-tech).** Vérifié en local : `send_test_email` met en file,
    `deploy/cron.sh run_jobs` (réglages de production, venv lu dans `VENV_ACTIVATE`) envoie, le
    battement de cœur donne `jobs: ok`, les verrous et l'exclusivité sont testés (y compris
    `GET_LOCK` sur MariaDB 10.11). **Reste à faire sur o2switch**, avec un accès au compte : la
    crontab, le fournisseur (D10, clé et domaine SPF/DKIM) et la réception réelle de l'e-mail.
