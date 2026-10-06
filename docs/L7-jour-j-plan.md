# Lot L7 — Jour J et attestations : plan d'implémentation

> **Statut : proposition, en attente de validation** (décisions K1 à K17, §2). Questions au
> commanditaire au §10, dont **Q11** (signataire des lettres d'invitation) et **Q14**
> (exigences institutionnelles pour les attestations). L6 est clos (bilan :
> `docs/L6-inscriptions.md`).
>
> Sources :
> - étude §4 M14 (jour J) et M10 (lettres d'invitation), §6 (RG-16, RG-17, RG-18), §8.2
>   (`checkin`, `certificate`), §9.2 (« Jour J »), §10.2, §10.5 (PWA), §13.1 (QR), §14
>   (L7 : 8 à 12 j-h), annexe A2 (« Attestation disponible »), US-10 et US-11 ;
> - mises à jour §17 à §22 (jeton QR d'inscription de L6, J11 ; rôles `SESSION_CHAIR` et
>   `SPEAKER` de L5 ; transition `SCHEDULED → PRESENTED` déclarée pour L7 ; inscription au
>   comptoir sans compte reportée de L6) ;
> - CLAUDE.md, règles n° 2 (droits côté serveur), n° 8 (fichiers privés), n° 9 (pas de
>   WebSocket ; tâches par `run_jobs`), n° 10 (`fpdf2`, `segno`).

## En bref

| | |
|---|---|
| **Objectif** | Le jour de la conférence, l'accueil scanne le QR du badge (téléphone, même sans réseau) et le participant est pointé ; chaque session émarge ses présents et marque les communications présentées. Après la conférence, chacun télécharge ses **attestations** (participation, communication, évaluation), vérifiables publiquement par un QR. Avant, les participants qui en ont besoin obtiennent une **lettre d'invitation** (visa). Badges imprimables en planche. |
| **Point dur** | **Hors ligne et caméra** sur un hébergement mutualisé, sans WebSocket : PWA limitée à l'accueil, liste de pointage minimale en cache, file de pointages synchronisée et idempotente ; lecture de QR dans le navigateur (iOS compris) ; en-têtes de sécurité à ouvrir pour la caméra sur `/gestion/` seulement. **RG-16** : une attestation n'existe que sur présence enregistrée. |
| **Hors périmètre** | Questionnaire de satisfaction et annonces de dernière minute (proposés en L8), signature électronique qualifiée (P3), « Mon programme » du participant (J15, reportée), impression sur imprimante thermique, contrôle d'accès aux sessions payantes. |
| **Charge** | **20,5 à 26 j-h** (étude : 8 à 12). Détail au §8. |
| **Démo H** | Une bénévole invitée installe l'accueil sur son téléphone, télécharge la liste, coupe le réseau, scanne trois badges (dont un déjà pointé et un annulé), retrouve le réseau : les pointages se synchronisent. Un participant sans compte est inscrit au comptoir et paie sur place ; son badge s'imprime. Le président de séance émarge sa session et marque les communications présentées. Le lendemain, le CO émet les attestations ; une participante télécharge la sienne et un tiers la vérifie par le QR. Un participant obtient sa lettre d'invitation validée. |

## 1. Périmètre

| Fonction (étude M14, M10) | Priorité | Dans L7 |
|---|---|---|
| Badges imprimables (A6, planche A4) avec QR | P2 | Oui (K3) |
| Check-in par scan QR (PWA), liste hors ligne synchronisable | P2 | Oui (K4 à K6) |
| Émargement par session | P2 | Oui (K7) |
| Communications marquées présentées (`PRESENTED`) | P2 | Oui (K8) |
| Attestations de participation, de communication, d'évaluation, vérification publique (RG-16) | P2 | Oui (K9 à K11) |
| Lettres d'invitation (visa) | P2 | Oui (K12), sous réserve de Q11 |
| Inscription au comptoir d'une personne sans compte | P2 | Oui (K13), reportée de L6 |
| Questionnaire de satisfaction, annonces de dernière minute | P2 | **Non** : L8 (K16) |
| Signature électronique qualifiée (PAdES, eIDAS) | P3 | **Non** (§13.2 de l'étude) |

**Écarts avec l'étude, à valider** :

- le rôle `VOLUNTEER` (bénévole) devient invitable en L7 et non en L8, puisque l'accueil en
  dépend (K1) ;
- 2FA imposée aux bénévoles, qui lisent la liste des participants (K1) ;
- attestation d'évaluation fondée sur les évaluations envoyées, sans présence physique ;
  l'étude (RG-16) ne parle que de présence et de communication présentée (K9).

## 2. Décisions (proposées)

| # | Sujet | Proposition |
|---|---|---|
| K1 | Droits | Capacités nouvelles. **`checkin.scan`** (pointer à l'accueil et en session) : `ADMIN`, `VOLUNTEER`, CO de toutes fonctions. **`checkin.manage`** (annuler un pointage, pointer à la main, liste et export des présences) : `ADMIN`, CO « secrétariat », « logistique » et « bénévoles ». **`certificates.manage`** (paramétrer et émettre les attestations, révoquer) : `ADMIN`, `CHAIR`, CO « secrétariat ». **`letters.manage`** (instruire les demandes de lettre d'invitation) : `ADMIN`, CO « secrétariat » et « relations extérieures ». Badges : `registrations.read` (L6). `VOLUNTEER` **invitable** par `ADMIN`, `CHAIR` et CO « bénévoles » (écart : L8 dans l'étude) ; **2FA imposée** (il lit noms et catégories des participants). `SESSION_CHAIR` : émargement et « présentée » pour **ses** sessions seulement (K7, K8) |
| K2 | Jeton du QR | Le QR du badge porte le **jeton d'inscription de L6** (192 bits, unique, retiré à l'annulation). Le serveur ne garde que lui ; la liste hors ligne n'en contient que l'**empreinte SHA-256** (K5). Un badge perdu : le CO **régénère** le jeton (l'ancien badge devient invalide, journal) |
| K3 | Badges | PDF par `fpdf2` : **A6** (un badge) ou **planche A4** de 4 badges, recto seul. Contenu : nom (taille adaptée), institution, pays, catégorie (bandeau de couleur par catégorie, paramétrable), titre de l'édition, QR (`segno`). Pas d'adresse ni de numéro. Téléchargement : le participant (le sien, dès la confirmation) ; le CO (lot filtré par catégorie ou statut, `registrations.read`, journalisé). Badges **générés à la demande**, non stockés (le jeton les rend sensibles : `Cache-Control: no-store`) |
| K4 | Pointage à l'accueil | Table `checkin` : inscription, session (vide = accueil), instant du pointage (heure de l'appareil, bornée), instant de réception, auteur, moyen (`scan`, `manual`), appareil, **clé d'idempotence** (unique). Un pointage d'accueil vaut **présence à la conférence** (RG-16). Refus explicites et distincts : jeton inconnu, inscription annulée ou expirée, en attente de paiement (proposition : refus, avec « régler au comptoir »), autre édition. Déjà pointé : avertissement, pas d'erreur. Annulation d'un pointage : `checkin.manage`, motif, journal |
| K5 | Hors ligne (PWA) | **PWA limitée à l'écran d'accueil** de la gestion (`/gestion/editions/{id}/accueil`), service worker Angular (`@angular/service-worker`) : coquille et écran en cache. **Liste de pointage** téléchargée (`GET …/checkin/bundle`) : empreinte du jeton, nom, catégorie, statut, déjà pointé ; ni adresse ni institution. Elle est gardée dans IndexedDB, effacée à la déconnexion et après 48 h ; un chiffrement au repos (Web Crypto, clé non exportable) sera évalué en L7.0, sans en attendre plus qu'une protection contre la copie des fichiers du navigateur. **File de pointages** en IndexedDB, envoyée par lots à la reconnexion (`POST …/checkin/sync`), idempotente ; le serveur renvoie l'état réel (un pointage hors ligne d'une inscription annulée entre-temps est rejeté et signalé). Pas de notification poussée ni de synchronisation en arrière-plan obligatoire (repli : bouton « Synchroniser ») |
| K6 | Lecture du QR | Caméra par `getUserMedia` ; décodage par l'API **`BarcodeDetector`** quand elle existe (Chrome Android), sinon par une bibliothèque JavaScript pur (**`jsQR`**, Apache-2.0, ou `zxing-js`), choisie en L7.0 sur la taille et la fiabilité. Saisie manuelle de la référence en secours. **En-têtes** : `Permissions-Policy` autorise `camera=(self)` **sous `/gestion/` seulement** ; CSP `worker-src 'self'` déjà en place, `media-src` à vérifier. HTTPS obligatoire (o2switch l'a) |
| K7 | Émargement par session | Même écran, mode « session » : choix de la session (programme **publié**), scan des badges à l'entrée. Pointage de session sans pointage d'accueil : accepté (il vaut aussi présence). Liste des présents par session, export CSV. Le **président de séance** (`SESSION_CHAIR`) émarge ses sessions sans autre droit |
| K8 | Communication présentée | Transition **`SCHEDULED → PRESENTED`** (déclarée pour L7) par le président de séance de la session, le CO « programme » ou l'administrateur, depuis la session publiée. Défaut proposé : le président de séance coche « présentée » pour chaque communication. Retour arrière (`PRESENTED → SCHEDULED`) : non prévu ; correction par l'administrateur, motif et journal. Les communications non marquées restent `SCHEDULED` |
| K9 | Attestations (RG-16) | Trois natures. **Participation** : inscription confirmée **et** présence enregistrée (accueil ou session). **Communication** : présentateur d'une soumission `PRESENTED` (un par présentateur, titre de la communication). **Évaluation** : relecteur ayant envoyé au moins une évaluation (nombre seulement, **jamais les titres** : RG-04) ; écart : pas de présence exigée. Contenu : nom, institution, nature, édition (titre, dates, lieu), date d'émission, **signataire** paramétré (nom, fonction, image de signature : fichier privé), **QR de vérification**. PDF `fpdf2`, figé, empreinte SHA-256, en ajout seul ; **révocable** (motif, journal), jamais supprimé |
| K10 | Vérification publique | Code de vérification aléatoire (≥ 100 bits, base32 lisible), dans le QR : `https://<domaine>/verification/<code>`. Page du portail **rendue dans le navigateur** (pas de pré-rendu), qui lit `GET /v1/public/certificates/{code}` : nature, nom, édition, date, statut (valide ou révoquée). Ni institution, ni adresse, ni empreinte. Limité en débit (CLAUDE.md), réponse identique pour code inconnu et mal formé (pas d'énumération), `noindex` |
| K11 | Émission et notification | Émission **par le CO** après la conférence (`certificates.manage`, réauthentification) : tâche `certificates.issue` en file (`run_jobs`, règle n° 9), par lots, idempotente (une attestation par personne, nature et objet). E-mail « Attestation disponible » (annexe A2), lien vers « Mes documents ». Émission complémentaire possible (pointage tardif). Le participant ne déclenche rien |
| K12 | Lettres d'invitation (M10, Q11) | Demande par le participant depuis « Mon inscription » (inscription **en attente ou confirmée**) : nom tel que sur le passeport, nationalité, numéro de passeport, dates de séjour, ambassade ou consulat. **Instruite** par le CO (`letters.manage`) : acceptée (lettre PDF émise, vérifiable comme une attestation) ou refusée (motif). Signataire paramétré (Q11). Mention : la lettre n'engage pas la prise en charge des frais. Numéro de passeport **effacé** à la fin de l'édition (K14) |
| K13 | Comptoir (reporté de L6) | Le CO « secrétariat » inscrit **une personne sans compte** : création d'un compte **sans mot de passe** (adresse non vérifiée, profil minimal : nom, institution, pays), inscription au tarif « sur place » (J2), paiement reçu (J7), badge imprimé. Un e-mail invite la personne à définir son mot de passe (lien de réinitialisation d'allauth). Adresse déjà connue : on rattache au compte existant. Journal `registrations.counter_created` |
| K14 | Données personnelles | Pointages, présences, attestations et demandes de lettre au registre (export). **Anonymisation** : pointages et présences anonymisés ; attestations et lettres **conservées** (preuve délivrée à la personne) avec leur nom figé, la page de vérification n'affichant alors que « attestation valide » sans nom ; numéro de passeport effacé à la clôture de l'édition (tâche de `cleanup`). Liste hors ligne : minimale et éphémère (K5) |
| K15 | Écrans | **Gestion** : « Jour J » (accueil et scan PWA, émargement de session, présences, badges, comptoir), « Attestations » (paramétrage : signataire, modèles FR et EN, couleurs de catégories ; émission, liste, révocation), « Lettres d'invitation » (demandes, instruction) ; carte « Jour J » du tableau de bord ; fiches d'aide. **Portail** : « Mes documents » dans le compte (badge, attestations, lettre : demande et suivi) ; page publique `/verification/<code>` |
| K16 | Reporté | Questionnaire de satisfaction et annonces de dernière minute : **L8** (avec le reporting). « Mon programme » (J15) : non demandé. Signature qualifiée : P3 |
| K17 | Ordre | L7.0 vérifications ; L7.1 modèle, droits, bénévoles ; L7.2 pointage (API, hors ligne côté serveur), badges ; L7.3 `PRESENTED`, émargement ; L7.4 attestations et vérification ; L7.5 lettres, comptoir ; L7.6 écrans de la gestion et PWA ; L7.7 portail ; L7.8 E2E, recette, documentation |

## 3. Modèle de données (nouvelle application `events`, additif)

- `checkin` : édition, inscription, session (nullable), `scanned_at` (appareil, borné à
  ±24 h de la réception), `received_at`, `recorded_by`, `method`, `device`, clé
  d'idempotence (unique), annulé (date, auteur, motif) ; pas de suppression.
- `certificate_settings` (une ligne par édition) : signataire (nom, fonction, image privée),
  textes FR et EN par nature (gabarits à variables fermées), couleurs des catégories de
  badges.
- `certificate` : édition, compte, nature (`participation`, `presentation`, `review`), objet
  (soumission pour une communication), nom et institution **figés**, code de vérification
  (unique), PDF privé et empreinte, émise le, révoquée (date, auteur, motif) ; unique par
  (édition, compte, nature, objet) hors révoquées.
- `invitation_letter` : édition, inscription, données du passeport (numéro effaçable),
  séjour, statut (`requested`, `issued`, `refused`), instruction (auteur, date, motif),
  code de vérification, PDF privé et empreinte.
- Soumissions : transition `SCHEDULED → PRESENTED` ouverte (K8) ; registre et workflow
  inchangés par ailleurs.
- **Contrôles d'intégrité** : attestation ⇔ condition RG-16 à l'émission ; PDF présents et
  intacts ; pointages d'inscriptions annulées signalés.

## 4. API

**Public** : `GET /v1/public/certificates/{code}` (attestations et lettres, limité en débit).

**Participant** : `GET /v1/registrations/{id}/badge` (PDF) ; `GET /v1/me/certificates`,
`…/{id}/pdf` ; `POST/GET /v1/registrations/{id}/invitation-letter`, `…/pdf`.

**Gestion** (`…/manage/editions/{id}/…`, 2FA) : `checkin/bundle`, `checkin/sync`,
`checkin/scan`, `checkin` (liste, annulation, saisie manuelle), `checkin/export` ;
`program/sessions/{id}/attendance`, `program/slots/{id}/presented` ;
`registrations/badges` (lot) ; `registrations/{id}/regenerate-token` ;
`registrations/counter` (comptoir) ; `certificates/settings`, `certificates`
(liste, émission, révocation) ; `invitation-letters` (liste, instruction).

## 5. Frontend

- **Gestion** : rubrique « Jour J » (accueil et scan, mode session, présences, badges,
  comptoir), « Attestations », « Lettres d'invitation » ; carte du tableau de bord ; fiches
  d'aide ; **manifeste et service worker** limités à l'accueil (installable sur
  téléphone).
- **Portail** : « Mes documents » (badge, attestations, lettre) et lien depuis « Mon
  inscription » ; page `/verification/<code>` (rendue dans le navigateur, `noindex`).

## 6. Sécurité

- **Le jeton du QR est un titre d'accès** : jamais dans une URL, ni dans un journal, ni
  dans la liste hors ligne (empreinte seulement) ; badges non stockés, servis sans cache.
- **Liste hors ligne** : minimale (ni adresse ni institution), effacée à la déconnexion et
  après 48 h ; téléchargement journalisé (qui, quand, combien).
- **Synchronisation** : idempotente, bornée (taille des lots, dates), chaque pointage
  revérifié par le serveur (règle n° 2).
- **Caméra** : `Permissions-Policy` ouverte à `/gestion/` seulement ; aucun flux envoyé au
  serveur (décodage local).
- **Vérification publique** : code non devinable, limitée en débit, sans énumération, sans
  donnée au-delà du nécessaire.
- **Attestations et lettres** : en ajout seul, empreinte vérifiée, révocation journalisée
  (RG-17) ; RG-16 vérifiée au serveur à l'émission.
- **Comptoir** : compte créé sans mot de passe, adresse non vérifiée jusqu'à la
  réinitialisation ; aucune connexion possible avant.

## 7. Tests

- **Unitaires** : RG-16 (conditions des trois natures), idempotence de la synchronisation,
  bornes des horodatages, refus explicites du pointage, régénération du jeton.
- **API** : matrice des droits (bénévole, président de séance limité à ses sessions) ;
  vérification publique (inconnu, révoqué, débit) ; liste hors ligne sans donnée sensible
  (traceurs).
- **PDF** : badges (planche, noms longs, alphabets étendus), attestations et lettres
  (contenu, empreinte, sortie identique).
- **Front** : file hors ligne (IndexedDB simulé), décodage QR sur images de test, écrans.
- **E2E** (L7.8) : badge du participant de L6 → scan à l'accueil (dont hors ligne simulé)
  → émargement de session et « présentée » → émission des attestations → téléchargement
  et vérification publique ; lettre d'invitation demandée et émise ; comptoir.

## 8. Étapes

| Étape | Contenu | Critère de fin | Charge |
|---|---|---|---|
| L7.0 | Vérifications : décodage QR (`BarcodeDetector`, `jsQR`, `zxing-js`), caméra sur iOS Safari et Android, service worker Angular servi par o2switch (`.htaccess`, `ngsw.json`), `Permissions-Policy` par chemin, chiffrement IndexedDB (Web Crypto), images dans `fpdf2` | Choix consignés | 1,5 – 2 |
| L7.1 | Application `events`, capacités, rôle `VOLUNTEER` invitable et 2FA, matrice, registre | Matrice au vert | 2 – 2,5 |
| L7.2 | Pointage : scan, liste hors ligne, synchronisation, annulation, export ; badges PDF ; régénération du jeton | Tests au vert | 3 – 4 |
| L7.3 | `PRESENTED`, émargement de session, président de séance | Tests au vert | 1,5 – 2 |
| L7.4 | Attestations : paramétrage, émission en tâche, PDF, vérification publique, e-mail, révocation | Tests RG-16 au vert | 3 – 4 |
| L7.5 | Lettres d'invitation ; comptoir sans compte | Tests au vert | 2 – 2,5 |
| L7.6 | Gestion : Jour J (PWA, scan, hors ligne), attestations, lettres, tableau de bord, aide | Démo H côté gestion | 4 – 5 |
| L7.7 | Portail : « Mes documents », vérification publique | Démo H côté portail | 1,5 – 2 |
| L7.8 | E2E, recette (téléphone réel si possible), documentation, étude (§23) | Démo H sur o2switch | 1,5 – 2 |
| **Total L7** | | | **20,5 – 26** |

## 9. Risques et hypothèses non vérifiées

- **iOS Safari** : caméra dans une PWA installée et `BarcodeDetector` absent ; repli
  `jsQR` à confirmer en L7.0 sur un appareil réel (impossible ici : le vérifier à la
  recette).
- **Service worker sur o2switch** : en-têtes de cache de `ngsw-worker.js` et `ngsw.json`,
  `.htaccess` de la gestion (`/gestion/`) ; à vérifier au premier déploiement.
- **Réseau du lieu** : inconnu ; l'accueil doit fonctionner sans réseau toute une matinée
  (taille de la liste pour 1 000 participants à mesurer en L7.0).
- **Horloge des téléphones** : les pointages hors ligne portent l'heure de l'appareil ; le
  serveur la borne et garde l'heure de réception.
- **Valeur des attestations** (Q14) : une université peut exiger une signature qualifiée ;
  hors L7.
- **Lettres d'invitation** (Q11) : signataire, en-tête et mentions inconnus ; gabarit
  paramétrable en attendant.

## 10. Questions au commanditaire

1. **Q11** : qui signe les lettres d'invitation et les attestations (nom, fonction, image de
   signature) ? En-tête institutionnel ?
2. **Q14** : les attestations doivent-elles respecter un modèle officiel (université,
   ministère) ? Une signature qualifiée est-elle exigée ?
3. **Bénévoles** : 2FA imposée (proposition) ou simple mot de passe ? Les bénévoles ont-ils
   tous un téléphone récent ?
4. **Pointage d'une inscription en attente de paiement** : refus avec renvoi au comptoir
   (proposition) ou pointage accepté et signalé ?
5. **Attestation d'évaluation** : souhaitée ? Pour les relecteurs seulement, ou aussi pour
   les présidents de séance et les membres des comités ?
6. **Badges** : format A6 en planche A4 (proposition) ou autre (badge plastifié, cordon,
   imprimante thermique) ? Couleurs par catégorie ?
7. **Questionnaire de satisfaction** : à reprendre en L8 (proposition) ?
