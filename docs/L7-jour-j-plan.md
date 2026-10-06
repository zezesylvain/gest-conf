# Lot L7 — Jour J et attestations : plan d'implémentation

> **Statut : validé le 6 octobre 2026, en cours** (décisions K1 à K17 telles que proposées,
> précisées par les réponses du commanditaire, qui ajoutent K18 et K19 : §2.1). L6 est clos
> (bilan : `docs/L6-inscriptions.md`).
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

### 2.1 Réponses du commanditaire (6 octobre 2026) et décisions ajoutées

| Question (§10) | Réponse | Effet sur le plan |
|---|---|---|
| Q11 : signataire | « Un utilisateur avec un rôle spécial, à créer » | **K18** (rôle signataire) |
| Q14 : modèle officiel ou signature qualifiée | « Les deux possibles » | **K19** (modèle officiel et signature électronique) |
| Bénévoles et 2FA | Oui | K1 tel quel |
| Inscription non payée à l'accueil | Refusée | K4 : refus « en attente de paiement », renvoi au comptoir |
| Attestation d'évaluation | Possible | K9 : nature **activable par édition**, désactivée par défaut |
| Badges | A6 en planche A4, couleur par catégorie | K3 tel quel |
| Questionnaire de satisfaction | Sans réponse | Hypothèse K16 maintenue : L8 |

| # | Sujet | Décision |
|---|---|---|
| K18 | Rôle signataire (Q11) | Nouveau rôle d'édition **`SIGNATORY`** (« signataire »), le 12ᵉ : attribué ou invité par `ADMIN` et `CHAIR`, **2FA imposée**, sans autre droit de gestion. Capacité **`signature.manage`** : le signataire **seul** renseigne sa signature, pour son propre compte : nom affiché, fonction FR et EN, image de signature (PNG ou JPEG, type vérifié par contenu, fichier privé, règle n° 8). Le CO ne peut ni déposer ni remplacer l'image d'un autre : il ne peut pas signer à sa place. Le paramétrage des attestations et des lettres **désigne** le signataire de chaque nature parmi les comptes qui ont le rôle et une signature complète ; sans signataire désigné, rien ne s'émet. Une pièce émise fige le nom, la fonction et l'empreinte de l'image. Retrait du rôle : les pièces émises restent valides ; les suivantes exigent un autre signataire |
| K19 | Modèle officiel et signature électronique (Q14) | **Modèle officiel** : gabarit paramétrable par édition et par nature : en-tête (logo ou bandeau, fichier privé), titre, textes FR et EN à variables fermées, pied de page, position de la signature et du QR. Le gabarit par défaut reste celui de K9. **Signature électronique** : interface de signataire électronique, sur le modèle des fournisseurs de paiement de L6 :<br>— **PAdES** (signature PDF) par une bibliothèque Python pure (`pyHanko`, à vérifier en L7.0), avec le **certificat de l'institution** (PKCS#12), déposé chiffré, son mot de passe dans l'environnement (règle n° 11) ;<br>— **qualifiée** : un certificat dans un fichier n'est pas un dispositif qualifié (QSCD). Une signature *qualifiée* au sens eIDAS exige un **prestataire de confiance qualifié** (signature à distance par API), à choisir (**nouvelle question Q17** : prestataire, contrat, coût). L'interface le prévoit ; aucun prestataire n'est branché en L7.<br>Activation par édition : image seule (défaut), PAdES, ou prestataire (quand il existera). La vérification publique (K10) reste disponible dans tous les cas |

**Charge** : K18 et K19 ajoutent **3 à 4 j-h** (rôle et droits, dépôt de la signature,
gabarits, PAdES et ses tests) : **23,5 à 30 j-h** au total.

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
| L7.0 | Vérifications : décodage QR (`BarcodeDetector`, `jsQR`, `zxing-js`), caméra sur iOS Safari et Android, service worker Angular servi par o2switch (`.htaccess`, `ngsw.json`), `Permissions-Policy` par chemin, chiffrement IndexedDB (Web Crypto), images dans `fpdf2`, **PAdES par `pyHanko`** (licence, dépendances, signature et vérification) | Choix consignés | 2 – 2,5 |
| L7.1 | Application `events`, capacités, rôles `VOLUNTEER` (invitable) et `SIGNATORY` (K18), 2FA, signature du signataire, matrice, registre | Matrice au vert | 3 – 3,5 |
| L7.2 | Pointage : scan, liste hors ligne, synchronisation, annulation, export ; badges PDF ; régénération du jeton | Tests au vert | 3 – 4 |
| L7.3 | `PRESENTED`, émargement de session, président de séance | Tests au vert | 1,5 – 2 |
| L7.4 | Attestations : paramétrage (signataire, gabarit officiel), émission en tâche, PDF, signature PAdES (K19), vérification publique, e-mail, révocation | Tests RG-16 au vert | 4,5 – 5,5 |
| L7.5 | Lettres d'invitation ; comptoir sans compte | Tests au vert | 2 – 2,5 |
| L7.6 | Gestion : Jour J (PWA, scan, hors ligne), attestations, lettres, signature du signataire, tableau de bord, aide | Démo H côté gestion | 4,5 – 5,5 |
| L7.7 | Portail : « Mes documents », vérification publique | Démo H côté portail | 1,5 – 2 |
| L7.8 | E2E, recette (téléphone réel si possible), documentation, étude (§23) | Démo H sur o2switch | 1,5 – 2 |
| **Total L7** | | | **23,5 – 30** |

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

## 11. Bilan de L7.0 (6 octobre 2026)

Essais menés dans des environnements jetables (dossier de travail de la session), sans
modifier le dépôt.

**Lecture du QR (K6)** : **`jsQR` 1.4.0 retenu** (Apache-2.0, JavaScript pur, environ 58 ko
compressés), chargé par le seul écran d'accueil.

- **`@zxing/library`** écartée : environ 11,8 Mo non empaquetés, pour un seul format utile.
- **`BarcodeDetector`** : absente de Chromium sous Linux (essai). Elle existe sur Chrome
  Android ; on l'emploiera là où elle existe, `jsQR` sinon.
- **Essai dans Chromium**, sur un QR de jeton d'inscription (192 bits) dégradé : rotation de
  14°, flou, bruit, contraste réduit, réduction à 113 px, perspective. Quatre images sur
  quatre décodées, en 7 à 80 ms.
- **Chaîne complète par une caméra simulée** (`--use-file-for-fake-video-capture`, vidéo
  Y4M fabriquée à partir du QR dégradé) : `getUserMedia`, vidéo, canevas, `jsQR`. Jeton lu
  dès la première trame. Ce montage servira à l'E2E de L7.8.
- **Non vérifiable ici** : caméra d'une PWA installée sur iOS Safari. À la recette, sur un
  appareil réel ; la saisie manuelle de la référence reste le recours.

**PWA (K5)** : **`@angular/service-worker` 22.2.1** (version d'Angular du dépôt).

- **Manifeste `ngsw.json`** généré par l'outil du paquet sur le build de la gestion : les
  77 fichiers sont préfixés par `/gestion/`.
- **Essai dans Chromium**, la gestion servie sous `/gestion/` avec repli SPA :
  - service worker actif, portée `/gestion/` ;
  - 80 entrées en cache ;
  - réseau coupé, `/gestion/editions/1/accueil` répond 200 avec l'application.
- **Précision de K5 : enregistrement à la demande.** Le service worker est enregistré
  **depuis l'écran d'accueil seulement**, pas au démarrage de la gestion. Les autres
  utilisateurs de la gestion n'en reçoivent donc jamais. Une fois installé, il met en
  cache toute la coquille de la gestion (plus simple que de la découper) ; seul l'accueil
  fonctionne sans réseau, les autres écrans affichant leur erreur habituelle.
- **Liste hors ligne** : 163 ko pour 1 000 participants (empreinte, nom, catégorie, statut),
  42 ko compressés.
- **Chiffrement au repos de la liste** dans IndexedDB : **non retenu**. La protection serait
  marginale (la clé vit dans le même navigateur) pour une liste déjà minimale ; restent la
  minimisation, l'effacement à la déconnexion et la durée de vie de 48 h.

**En-têtes (K6)** : vérifiés avec un **Apache 2.4 réel** (installé pour l'essai) et les
`.htaccess` du dépôt.

- Un `Header always set Permissions-Policy "camera=(self), …"` dans le `.htaccess` de la
  gestion **remplace** celui de la racine : `/fr/` garde `camera=()`, alors que `/gestion/`
  et ses sous-adresses reçoivent `camera=(self)`.
- `ngsw-worker.js` et `ngsw.json` ne prennent pas le cache long réservé aux fichiers à
  empreinte.
- Ce changement entre dans `deploy/apache/gestion.htaccess` en L7.6, avec un contrôle dans
  `deploy/smoke-test.sh`.

**Badges (K3)** : `fpdf2` 2.8.9 et `segno` 1.6.6, déjà installés en L6.

- **Planche A4** de quatre A6 : bandeau de l'édition, nom (alphabets étendus : Ŋ, ɔ́, Ḱ, Œ,
  Ł), institution et pays, QR, bandeau de catégorie en couleur. Rendu contrôlé.
- **QR en SVG** (vectoriel, plus net à l'impression) avec `viewBox`, sinon en PNG.
- **Durée** : 100 badges en 0,8 s, soit environ 8 s pour 1 000. **Précision de K3** : le
  lot du CO est découpé en fichiers de 200 badges au plus, pour tenir dans le temps d'une
  requête Passenger.

**Signature PAdES (K19)** : **`pyHanko` 0.37.0 retenu** (MIT).

- **Essai** : certificat RSA 3072 auto-signé, en PKCS#12 ; signature d'une attestation
  `fpdf2`, au format `ETSI.CAdES.detached` (PAdES-B-B). La validation donne : intègre,
  valide et de confiance (racine fournie). Un octet modifié dans la plage signée est
  détecté.
- **Coût** : 0,3 s d'import et 0,3 s par signature ; le module ne sera importé qu'au moment
  de signer.
- **Dépendances** : une quinzaine de paquets, dont sept roues binaires `manylinux`
  (`aiohttp`, `lxml`, `yarl`, `multidict`, `frozenlist`, `propcache`, `cffi`). Aucune n'a de
  dépendance système, et toutes existent pour CPython 3.12 et 3.13.
  - Le projet installe déjà des roues binaires de ce type (`cryptography`, `pillow`) : pas
    de risque d'une nature nouvelle pour o2switch (règle n° 10).
  - L'ajout aux verrous se fera en L7.4, quand le code s'en servira, avec empreintes.
- **Garde de la clé** : le PKCS#12 déposé est déchiffré à la réception, puis **rechiffré par
  des clés dédiées** (`GESTCONF_SIGNING_ENCRYPTION_KEYS`, `MultiFernet`, comme les secrets
  2FA de L1.6). Son mot de passe n'est pas conservé ; la clé n'est jamais servie.

**Écart avec le plan** : aucun ; les précisions ci-dessus (enregistrement du service worker
à la demande, lots de 200 badges, pas de chiffrement de la liste) affinent K3 et K5.

## 12. Bilan de L7.1 (6 octobre 2026)

**Rôles** (`apps/accounts/roles.py`, migration `accounts/0006`) :

- **`SIGNATORY`** (« signataire »), 12ᵉ rôle d'édition (K18) ;
- `VOLUNTEER` et `SIGNATORY` **invitables** par `ADMIN` et `CHAIR` ;
- 2FA imposée aux deux (`MFA_REQUIRED_ROLES`) ;
- inviter un signataire exige une réauthentification récente, comme `ADMIN` et `CHAIR`
  (**précision de K18** : il signe au nom de l'édition).

**Capacités** (K1, K18) :

- **`checkin.scan`** : administrateur, bénévoles, tout le CO ;
- **`checkin.manage`** : administrateur, CO « secrétariat », « logistique » et « bénévoles » ;
- **`certificates.manage`** : administrateur, Chair, CO « secrétariat » ;
- **`letters.manage`** : administrateur, CO « secrétariat » et « relations extérieures » ;
- **`signature.manage`** : le signataire **seul**, l'administrateur compris exclu (un test le
  vérifie).

**CO « bénévoles »** (K1) :

- attributions **par fonction** au CO : `FUNCTION_GRANTORS` et `VISIBLE_MEMBER_ROLES`
  s'ajoutent à `GRANTORS` ;
- le CO « bénévoles » reçoit `members.read` et `members.manage`, mais ne voit, n'invite et ne
  retire **que des bénévoles**, sur le modèle du président du CS limité au comité
  scientifique ;
- la gestion recopie cette table pour l'interface (`core/grantors.ts`, tenant compte de la
  fonction).

**Application `events`** :

- **`Signature`** (une par compte et par édition) : nom affiché, fonction FR et EN, image.
  - **Précision de K18** : la signature est rattachée à l'édition, comme le rôle (règle n° 5) ;
    la fonction peut changer d'une édition à l'autre.
- **`Checkin`** (pointage, K4) : clé d'idempotence unique ; « clé active »
  `<inscription>:<session ou 0>`, nulle une fois le pointage annulé, faute d'index unique
  partiel sur MariaDB. Il est servi en L7.2.
- **Écart avec le §3 du plan** : les modèles des attestations et des lettres arriveront avec
  leurs services (L7.4, L7.5), par migrations additives, plutôt que vides dès L7.1.

**Signature du signataire** (`apps/events/services/signatures.py`) :

- le service revérifie le rôle actif : ni l'administrateur ni le CO ne peuvent écrire la
  signature d'autrui, même par un appel direct ;
- image PNG ou JPEG d'au plus 1 Mo, type vérifié par le contenu ;
  - garde contre les bombes de décompression ;
  - réencodée en PNG sans métadonnées, réduite à 1 200 px, refusée sous 60 × 20 px ;
- stockage privé (`signatures/`, règle n° 8), ancienne image effacée après validation,
  orphelins purgés par `cleanup` ;
- journal `signature.updated` et `signature.image_uploaded` (empreinte seulement).

**API** (gestion, 2FA) :

- `GET` et `PATCH …/signature` ;
- `GET` et `PUT …/signature/image` (aperçu en `no-store`, dépôt limité à 20 par heure) ;
- écritures sous réauthentification récente.

**Registre des données personnelles** (`events.events`) :

- export de la signature et des pointages de la personne ;
- anonymisation : signature vidée et image effacée. Un signataire actif ne peut pas être
  anonymisé (responsabilité à transmettre) ;
- les pointages restent, rattachés à une inscription anonymisée (K14).

**Matrice des droits** :

- quatre profils ajoutés (CO « bénévoles », CO « relations extérieures », bénévole,
  signataire) et les quatre cases de la signature ;
- un test compare désormais les capacités de chaque profil, lues par `/v1/me`, à la
  spécification, y compris les capacités encore sans route ;
- le CO « bénévoles » est testé sur son périmètre (bénévoles seuls) ;
- la 2FA des bénévoles et des signataires est testée.

**Hors périmètre, corrigé en passant** : quelques en-têtes de colonnes des exports de L6
étaient restés sans traduction anglaise ; `locale/check.sh` les signalait. Ils sont traduits.

**Tests** :

- backend : **4 112 réussis**, 9 ignorés (SQLite) ; sous MariaDB, `events`, `accounts`, le
  registre, le schéma et les règles de plateforme réussissent (234) ;
- matrice des droits : **2 955 cas** (2 273 à la fin de L6) ;
- `events` : 24 tests (signature : service, image, API, réauthentification ; registre) ;
- front : 388 tests, dont la table d'attribution de la gestion selon la fonction au CO ;
- `ruff`, `npm run lint`, `format:check`, `locale/check.sh`, schéma validé sous MariaDB,
  client régénéré.

**Critère de fin** (« Matrice au vert ») : atteint.
