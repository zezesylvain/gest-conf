# Lot L7 — Jour J et attestations : bilan et exploitation

Ce document résume ce que livre le lot L7 de GEST-CONF et comment l'exploiter. Le détail des
choix, des vérifications et des défauts trouvés est dans
[`L7-jour-j-plan.md`](L7-jour-j-plan.md) : décisions K1 à K17 au §2, K18 et K19 au §2.1,
bilans des étapes aux §11 à §19. L'étude est mise à jour en conséquence (§23 « Mises à jour
issues du lot L7 »).

## 1. Ce qui est livré

| Étape | Contenu | Commit |
|---|---|---|
| L7.0 | Vérifications : lecture du QR (`jsQR`, `BarcodeDetector`), caméra simulée, service worker sous `/gestion/`, `Permissions-Policy` par chemin, badges `fpdf2`, PAdES par `pyHanko` | `d40eba8` |
| L7.1 | Rôles bénévole (invitable) et signataire (K18), capacités du jour J, attributions par fonction au CO, signature du signataire, matrice, registre | `331ff10` |
| L7.2 | Pointage à l'accueil (badge ou référence), liste hors ligne, synchronisation, annulation, export ; badges retirés ; badges PDF (A6, planches A4) ; badge perdu | `3d2f6f2` |
| L7.3 | Émargement des sessions publiées, président de séance, communication « présentée » (`SCHEDULED → PRESENTED`) et sa correction | `d21f23e` |
| L7.4 | Attestations (RG-16) : modèle officiel, signataire désigné, PAdES, émission en file, révocation, vérification publique, e-mail | `d0ae750` |
| L7.5 | Lettres d'invitation (demande, instruction, effacement du passeport) ; inscription au comptoir d'une personne sans compte | `3f84c20` |
| L7.6 | Gestion : « Jour J » (accueil installable et hors ligne, sessions du jour, présences, badges, comptoir), « Attestations et lettres », « Ma signature », tableau de bord, aide | `7dfef23` |
| L7.7 | Portail : « Mes documents », vérification publique `/verification/<code>` | `a3d7ab0` |
| L7.8 | Parcours de bout en bout, recette, bilan, étude (§23), `CLAUDE.md` | dernier commit du lot |

Intégration continue : à faire passer par une PR (sur demande).

## 2. Parcours couverts (démo H)

- **Bénévole** (rôle invité, 2FA), dans la gestion, sur son téléphone :
  - « Accueil » s'installe comme une application (manifeste et service worker ajoutés par
    cet écran seul) ;
  - avant l'ouverture : « Télécharger la liste hors ligne » (empreintes des badges, noms,
    catégories ; valable 48 heures) ;
  - la caméra lit le QR du badge ; le serveur répond « pointé », « déjà pointé » ou un refus
    motivé (annulée, expirée, en attente de paiement, badge remplacé, autre édition) ;
  - **sans réseau**, l'appareil décide sur la liste et garde les pointages en file ; au
    retour du réseau, la file part seule et le serveur signale ce qu'il refuse ;
  - mode « session » : entrée d'une session du programme publié ;
  - nom du poste repris dans chaque pointage.
- **Président de séance** : ses sessions du jour ; présents à l'entrée ; communications
  marquées « présentée ».
- **CO « programme »** (et administrateur) : « présentée » sur toute session, et sa
  correction motivée.
- **CO « secrétariat »** (et administrateur) :
  - « Présences » : recherche, annulation motivée d'un pointage, export ;
  - « Comptoir » : inscription d'une personne sans compte, paiement reçu, badge aussitôt ;
  - « Badges » : planches A4 par catégorie, par fichiers de 200 ; badge perdu remplacé
    depuis la fiche de l'inscription ;
  - « Modèle des attestations » : mode de signature, en-tête officiel, certificat PAdES,
    signataire désigné et textes FR et EN par nature, aperçu ;
  - « Attestations » : émission par nature après la conférence, émission complémentaire,
    révocation motivée ;
  - « Lettres d'invitation » : instruction des demandes (émission ou refus motivé),
    révocation.
- **Chair** : attestations (modèle, émission, révocation) et badges.
- **Signataire** (rôle invité, 2FA) : « Ma signature » (nom, fonction FR et EN, image) ;
  personne d'autre ne peut la déposer.
- **Participant** (portail) :
  - « Mes documents » (`/compte/mes-documents`) : badge, attestations, lettre d'invitation
    (demande et suivi) ;
  - vérification publique d'une attestation ou d'une lettre par son QR
    (`/verification/<code>`).

## 3. Sécurité et données personnelles, en bref

- **Le QR du badge est un titre d'accès** :
  - jeton de 192 bits ;
  - la liste hors ligne n'en contient que l'empreinte, et le serveur n'accepte jamais une
    empreinte comme preuve ;
  - badges générés à la demande, jamais stockés, servis sans cache ;
  - badge perdu : nouveau jeton, l'ancien est refusé.
- **Hors ligne** :
  - liste minimale (ni adresse ni institution), effacée à 48 heures et à la déconnexion ;
  - la file garde les jetons lus jusqu'à l'envoi : la déconnexion l'efface, après
    avertissement ;
  - chaque pointage est revérifié par le serveur.
- **Caméra** : permise sous `/gestion/` seulement (`Permissions-Policy`), image décodée sur
  l'appareil, jamais envoyée.
- **RG-16** : vérifiée par le serveur à l'émission :
  - participation sur présence enregistrée ;
  - communication sur statut « présentée » ;
  - évaluation sur évaluations envoyées, avec leur nombre seulement (RG-04).
- **Attestations et lettres** :
  - en ajout seul, PDF figés et empreinte vérifiée ;
  - révocation motivée et journalisée (RG-17) ;
  - vérification publique limitée en débit, sans énumération, sans institution ni
    empreinte.
- **Signature** :
  - le signataire seul la dépose ;
  - une pièce émise fige nom, fonction et empreinte de l'image ;
  - le certificat PAdES est rechiffré par une clé dédiée et jamais servi ; son mot de passe
    n'est pas gardé.
- **Droits** :
  - `checkin.scan` (administrateur, bénévoles, CO) ;
  - `checkin.manage` (administrateur, CO « secrétariat », « logistique », « bénévoles ») ;
  - `certificates.manage` (administrateur, Chair, CO « secrétariat ») ;
  - `letters.manage` (administrateur, CO « secrétariat », « relations extérieures ») ;
  - `signature.manage` (signataire seul) ;
  - `sessions.chair` (président de séance, vérifié session par session) ;
  - réauthentification récente pour les écritures sensibles (attestations, lettres, exports,
    signature).
- **Données personnelles** :
  - pointages, signature, attestations et lettres figurent à l'export ;
  - anonymisation : pointages rattachés à l'inscription anonymisée ; attestations et lettres
    conservées, la vérification publique ne montrant plus de nom ;
  - **numéro de passeport effacé** 30 jours après la fin de l'édition ou à son archivage
    (tâche de conservation).

## 4. Exploitation

- **Variable d'environnement** (`backend/.env.example`), facultative :
  `GESTCONF_SIGNING_ENCRYPTION_KEYS`, clés `MultiFernet` du certificat PAdES. Sans elle, la
  signature PAdES est refusée ; l'image de signature suffit.
- **Cron** : aucune ligne nouvelle.
  - L'émission des attestations passe par `run_jobs` (toutes les 5 minutes).
  - L'effacement des numéros de passeport et la purge des fichiers orphelins passent par
    `cleanup` (quotidien).
- **Hébergement** (`.htaccess`, `deploy/smoke-test.sh`) :
  - caméra permise sous `/gestion/` ;
  - manifeste servi en `application/manifest+json` ;
  - `ngsw.json` et le service worker sans cache long ;
  - `/verification/<code>` servie par la coquille rendue dans le navigateur ;
  - `Disallow: /verification` dans `robots.txt`.
- **Build** : `npm run build` régénère `ngsw.json` **après** l'injection de la CSP, puis en
  contrôle les empreintes (`web/scripts/check-ngsw.mjs`). Sans cela, le service worker
  refuserait la version et l'accueil ne marcherait plus sans réseau.
- **Avant le jour J** :
  - inviter les bénévoles (CO « bénévoles », administrateur ou Chair) : 2FA à activer ;
  - imprimer les badges ;
  - sur chaque téléphone :
    - ouvrir « Accueil » une fois en ligne et l'installer ;
    - télécharger la liste la veille, puis le matin.
- **Après la conférence** :
  - inviter le signataire, qui dépose sa signature ;
  - désigner le signataire de chaque nature dans « Modèle des attestations » ;
  - émettre les attestations : les e-mails partent avec la file.
- **Contrôles d'intégrité** (`check_integrity`) :
  - `events.checkins` : pointage d'une inscription qui n'est plus confirmée ;
  - `events.certificate_files` et `events.letter_files` : PDF présents et intacts.
- **À vérifier sur o2switch et sur appareils réels** :
  - caméra de l'accueil installé sur iOS Safari et sur Android ;
  - service worker servi sous `/gestion/` ;
  - en-têtes par chemin (`Permissions-Policy`) ;
  - délai de génération des planches de 200 badges.

## 5. Tests

- **Backend** : **4 972 tests** sous SQLite (10 ignorés), sous-ensembles du lot sous MariaDB.
  Matrice des droits : **3 746 cas** (2 273 à la fin de L6). Ils couvrent notamment :
  - pointage :
    - refus distincts ;
    - idempotence et rejeu de la synchronisation ;
    - bornes de l'heure de l'appareil ;
    - deux appareils sur le même badge (MariaDB) ;
  - liste hors ligne sans donnée sensible (traceurs) ;
  - badges : planche, noms longs, alphabets étendus ;
  - émargement et président de séance limité à ses sessions ;
  - RG-16 pour les trois natures ;
  - PAdES validé par `pyHanko` ;
  - vérification publique : inconnu, révoqué, anonymisé, débit ;
  - lettres et effacement du passeport ;
  - comptoir ;
  - registre des données personnelles.
- **Front (Vitest)** : **469 tests** (shared 79, portail 158, gestion 219, scripts 13). Ils
  couvrent :
  - le poste d'accueil :
    - en ligne, hors ligne, 504 du service worker ;
    - refus ;
    - lots de synchronisation ;
  - liste et file :
    - empreinte identique à celle du serveur ;
    - expiration ;
    - effacement ;
  - la lecture du QR ;
  - le démarrage hors ligne ;
  - les écrans de la gestion et du portail ;
  - les empreintes de `ngsw.json`.
- **Bout en bout (Playwright)** : le parcours en série se prolonge (plan, §19) :
  1. le signataire dépose sa signature, et le secrétariat le désigne ;
  2. l'auteure demande sa lettre d'invitation, émise par le secrétariat ;
  3. un bénévole, avec une caméra simulée filmant le badge de l'auteure :
     - télécharge la liste ;
     - pointe **sans réseau** ;
     - voit la file partir au retour du réseau, puis « déjà pointé » ;
     - pointe à l'entrée de la session ;
  4. le CO « programme » marque la communication « présentée » ;
  5. le secrétariat inscrit une personne au comptoir ;
  6. les attestations sont émises par la file, l'auteure seule en reçoit (RG-16), les
     télécharge, et la vérification publique les confirme.
- **Vérifié au navigateur** sur les builds de production :
  - l'accueil se recharge sans réseau depuis le service worker ;
  - la page de vérification fonctionne.

## 6. Ce qui reste à faire ou à décider

**Avant le jour J réel** :

- démo H sur o2switch, sur téléphones réels (iOS et Android), réseau coupé ;
- vérification des en-têtes par chemin sur l'hébergement.

**Décisions du commanditaire** :

- **Q17** : prestataire de signature qualifiée (eIDAS) : choix, contrat, coût. L'interface
  est prévue ; aucun n'est branché.
- **Q11** : tranchée par le rôle signataire (K18).
- **Q14** : tranchée sur le modèle (officiel et signature électronique, K19) ; la question
  des noms des auteurs au programme public reste ouverte.
- Pays imprimé en code ISO sur les badges : nom complet à ajouter si souhaité.

**Reporté** :

- questionnaire de satisfaction et annonces de dernière minute (L8, K16) ;
- « Mon programme » du participant (J15) ;
- signature qualifiée (P3) ;
- impression thermique, contrôle d'accès aux sessions payantes.

**Ouverts depuis L5 et L6** :

- transition `ACCEPTED_MINOR → WITHDRAWN` ;
- seuil d'avertissement du bundle initial du portail : 368,9 ko pour 365 ko ;
- Q7 et Q8.
