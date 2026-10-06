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

## 13. Bilan de L7.2 (6 octobre 2026)

**Pointage à l'accueil** (`apps/events/services/checkin.py`, K4, K5) :

- par le QR du badge (`checkin.scan`) ou par la référence de l'inscription (saisie manuelle,
  `checkin.manage`, car une référence se devine) ;
- un pointage vaut présence (RG-16) ; le second passage d'un badge rend « déjà pointé », sans
  nouvelle ligne ;
- refus distincts :
  - badge inconnu ;
  - badge d'une autre édition ;
  - inscription annulée, inscription expirée ;
  - badge remplacé ;
  - en attente de paiement (réponse du commanditaire) ;
- verrou de l'inscription : deux appareils qui lisent le même badge en même temps produisent
  un pointage et un « déjà pointé » ;
- heure de l'appareil ramenée entre la réception moins 24 heures et la réception ; heure de
  réception gardée à part ;
- annulation d'un pointage : motif obligatoire, journal ; la personne peut être repointée ;
- journal `checkin.recorded` et `checkin.cancelled`, sans jeton.

**Précision de K2 et K5 : la preuve d'un pointage est le jeton lui-même.**

- Le serveur n'accepte jamais une empreinte comme preuve. La liste hors ligne, qui ne contient
  que des empreintes, ne permet donc pas de pointer qui que ce soit sans son badge, même entre
  les mains d'un bénévole indélicat.
- Conséquence côté appareil : la file des pointages hors ligne garde les jetons lus jusqu'à
  la synchronisation. Elle est effacée avec la liste (déconnexion, 48 heures) ; à traiter en
  L7.6.

**Badges retirés** (`registrations.RetiredQrToken`, migration `registrations/0003`) :

- à l'annulation d'une inscription confirmée (workflow) et au remplacement d'un badge perdu,
  l'empreinte de l'ancien jeton est gardée, jamais le jeton ;
- l'accueil répond ainsi « inscription annulée » ou « badge remplacé », en ligne comme hors
  ligne, plutôt que « inconnu » (démo H : « un badge annulé »).

**Badge perdu** (K2) : `orders.regenerate_qr_token`.

- Inscription confirmée seulement ; motif obligatoire ; journal sans jeton.
- Capacité `checkin.manage` : l'accueil le fait sur place.

**Liste hors ligne** (K5, `GET …/checkin/bundle`) :

- contenu : empreinte SHA-256 du jeton, référence, nom, code de catégorie, « déjà pointé » ;
  catégories et badges retirés (empreinte, référence, motif) ;
- ni jeton, ni adresse, ni institution (test à traceurs) ;
- échéance à 48 heures ; téléchargement journalisé avec le nombre d'entrées ;
- servie en `no-store`.

**Synchronisation** (`POST …/checkin/sync`) :

- lots de 200 au plus ; chaque élément est revérifié par le serveur ;
- même clé d'idempotence, même résultat : le lot est rejouable ;
- une saisie manuelle reçue d'un appareil sans `checkin.manage` est rendue « non permise » ;
- un élément mal formé fait refuser tout le lot (400), sans écriture.

**Suivi** :

- compteurs (`…/checkin/summary`, `checkin.scan`) ;
- liste filtrable avec les pointages annulés en option, annulation, export CSV
  (`checkin.manage`, réauthentification, journal) ;
- contrôle d'intégrité `events.checkins` : pointage actif d'une inscription qui n'est plus
  confirmée, ou d'une autre édition.

**Badges** (K3, `apps/events/badges.py`) :

- format A6 pour le participant (`GET /v1/registrations/{id}/badge`, dès la confirmation) et
  pour un badge seul côté CO ;
- planches A4 de quatre badges avec traits de coupe, par lots de 200
  (`…/registrations/badges?category=&batch=`, nombre de lots par `…/badges/batches`) ;
- droits : `registrations.read` ; journal sans jeton ; jamais stockés, servis en `no-store` ;
- contenu :
  - titre de l'édition ;
  - nom en grand, sur deux lignes au plus, sans couper de mot ;
  - institution et pays ;
  - QR vectoriel ;
  - référence sous le QR, secours de la saisie manuelle (K6) ;
  - bandeau de catégorie dans sa couleur (`RegistrationCategory.badge_color`, `#RRGGBB`,
    palette par défaut selon l'ordre), texte noir ou blanc selon la luminance.
- **Écarts** :
  - la couleur est portée par la catégorie, éditée avec elle (`pricing.write`), et non par le
    paramétrage des attestations (§3) ;
  - **le pays s'imprime en code ISO** (« SN ») : le serveur n'a pas de table des noms de pays
    (Angular les affiche par `Intl.DisplayNames`). Une table FR et EN versionnée serait à
    ajouter si le commanditaire veut le nom complet.
- La police DejaVu Sans passe de `apps/payments/fonts/` à `apps/core/fonts/`, avec
  `apps/core/pdf.py`, pour servir à toutes les applications.

**Reporté en L7.3** : le pointage en session (le modèle et le service le prévoient déjà par
leur clé de lieu).

**Tests** :

- backend : **4 363 réussis**, 9 ignorés (SQLite) ;
- sous MariaDB : `events`, `registrations`, `payments`, `accounts`, le registre, le schéma et
  les règles de plateforme (421), plus les cases nouvelles de la matrice (326) ;
  - dont deux appareils qui lisent le même badge en même temps : un pointage, un « déjà
    pointé » ;
- matrice des droits : **3 184 cas** (douze routes ajoutées) ;
- `events` : 47 tests (pointage, refus, idempotence, bornes, synchronisation, liste hors
  ligne à traceurs, badges A6 et planches, couleur, remplacement du badge) ;
- front : 388 tests ; client régénéré (aucun écran nouveau : L7.6) ;
- `ruff`, lint, `format:check`, `locale/check.sh`, schéma validé sous MariaDB.

**Critère de fin** (« Tests au vert ») : atteint.

## 14. Bilan de L7.3 (6 octobre 2026)

**Communication présentée** (K8) : transition `SCHEDULED → PRESENTED` ouverte dans
`apps/submissions/workflow.py`.

- Qui : `program.write` (administrateur, CO « programme »), et le **président de séance** de
  la session où la communication est placée.
- Le président de séance passe par une **délégation** que l'application `events` inscrit
  dans le workflow (`register_actor_grant`, par transition). `submissions` ne dépend pas
  d'`events`, et une délégation n'étend jamais une transition à d'autres statuts.
- **Correction** `PRESENTED → SCHEDULED` : `program.write` seulement, motif obligatoire,
  historique et journal.
  - **Précision de K8** : le plan disait « par l'administrateur » ; la capacité retenue
    inclut le CO « programme », qui tient le programme.
  - Le président de séance ne corrige pas.

**Émargement des sessions** (K7) :

- tout se lit dans le **programme publié** (dernier instantané), jamais dans le brouillon :
  seules ses sessions s'émargent, et le président de séance est celui qu'il désigne ;
- un président désigné au brouillon seulement n'a aucun droit ;
- un pointage de session vaut présence, même sans pointage d'accueil ; un lieu, un pointage
  actif (accueil, chaque session) ;
- la synchronisation hors ligne accepte un champ `session`, refusé (« session absente du
  programme publié ») hors du programme publié ;
- une session émargée ne se supprime plus du brouillon : garde inscrite dans
  `planning.delete_session` (`register_session_guard`), qui renvoie `in_use` au lieu d'une
  erreur de contrainte.

**API** (`…/day/sessions/…`, au lieu du `…/program/…` esquissé au §4) :

- liste des sessions publiées avec leurs créneaux, le **statut courant** de chaque
  communication, ses présentateurs et le nombre de présents ;
- présents d'une session, lecture du badge à l'entrée, export CSV (réauthentification,
  journal) ;
- « présentée » et sa correction.

**Droits** (`CapabilityOrSessionChair`) :

- la capacité de l'action, **ou** la présidence de la session du chemin au programme publié,
  pour les seules actions ouvertes au président :
  - liste des sessions (les siennes seulement) ;
  - présents, lecture du badge, « présentée » ;
- pas l'export, ni la correction, ni l'accueil ;
- le président de séance reste **sans 2FA** (K1 ne l'imposait pas) : il ne voit que les
  présents de sa session.

**Matrice** :

- six routes ajoutées, sur une session publiée créée à part (instantané posé directement),
  pour que les cas de publication du programme restent valables ;
- les objets paresseux du monde acceptent désormais plusieurs chargeurs ;
- la présidence de séance est testée hors de la matrice (`test_attendance.py`) : sa session,
  pas l'autre, ni l'export, ni la correction, ni la liste hors ligne.

**Non retenu** :

- saisie manuelle de la référence à l'entrée d'une session : l'accueil la couvre ;
- garde horaire sur « présentée » (pas avant le début de la session) : non demandée ; elle
  gênerait la recette.

**Tests** :

- backend : **4 489 réussis**, 10 ignorés (SQLite) ;
- sous MariaDB : `events`, `submissions`, `program`, le schéma et les règles de plateforme
  (258), plus les cases nouvelles de la matrice ;
- matrice des droits : **3 299 cas** ;
- `events` : 58 tests, dont 11 pour l'émargement et « présentée » ;
- front : 388 tests ; client régénéré ;
- `ruff`, lint, `format:check`, `locale/check.sh`, schéma validé sous MariaDB.

**Critère de fin** (« Tests au vert ») : atteint.

## 15. Bilan de L7.4 (6 octobre 2026)

**Modèle** (migration `events/0002`) :

- `CertificateSettings`, une ligne par édition :
  - mode de signature : image (défaut), PAdES ou prestataire ;
  - attestation d'évaluation, **désactivée par défaut** (réponse du commanditaire) ;
  - disposition : signature à droite et QR à gauche, ou l'inverse ;
  - en-tête du modèle officiel, certificat PAdES ;
- `DocumentTemplate`, par nature (participation, communication, évaluation, et lettre
  d'invitation pour L7.5) : titre, texte et pied de page FR et EN, signataire désigné ;
- `Certificate` : pièce **figée** en ajout seul, unique tant qu'elle n'est pas révoquée par
  (édition, personne, nature, communication).

**RG-16, vérifiée à l'émission** (`apps/events/services/certificates.py`) :

- **participation** : inscription confirmée **et** pointage actif, à l'accueil ou en session ;
- **communication** : présentateurs d'une communication `PRESENTED`, rattachés à un compte (le
  leur, ou celui qui a vérifié leur adresse) ;
  - les présentateurs sans compte sont comptés à part (« impossibles à remettre ») ;
- **évaluation** : relecteurs ayant envoyé au moins une évaluation, avec leur **nombre**
  seulement, jamais les titres (RG-04).

**Signataire (K18)** :

- rien ne s'émet sans signataire désigné, dont la signature est complète et le rôle actif
  (`signatory_missing`) ;
- seule une signature de l'édition, complète et de rôle actif, se désigne ;
- l'attestation fige le nom, la fonction FR et EN et l'empreinte de l'image.

**Modèle officiel (K19)** :

- textes à **variables fermées** par nature (`{name}`, `{edition}`, `{dates}`, `{venue}`, plus
  `{title}` et `{reference}`, ou `{count}`) ;
  - toute autre accolade, tout attribut, indice ou format est refusé à l'enregistrement ;
  - le remplissage n'est qu'un `format_map` sur des valeurs déjà calculées ;
- texte vide : texte par défaut ;
- dates écrites dans chaque langue (« du 1er au 3 juin 2027 », « from June 1 to 3, 2027 ») ;
- PDF `fpdf2`, A4 paysage :
  - en-tête de l'institution (image privée réencodée en PNG) ou bandeau du titre ;
  - titre et texte en français puis en anglais ;
  - date d'émission ;
  - bloc de signature et QR de vérification ;
  - pied de page ;
- aperçu du gabarit sur données fictives, ni signé ni stocké.

**PAdES (K19)** :

- `pyHanko` 0.37.0 ajouté aux verrous (`requirements/*.txt`, empreintes) ;
  - quatorze paquets, tous en roues ; `oscrypto` n'intervient pas dans la signature
    (essai) ;
- le PKCS#12 déposé est ouvert avec son mot de passe ;
  - refusé si illisible, s'il n'a ni clé ni certificat, si le certificat est hors période
    de validité, ou sans usage de signature ;
  - puis réexporté **sans** mot de passe et chiffré par `GESTCONF_SIGNING_ENCRYPTION_KEYS`
    (`MultiFernet`, hors racine web) ;
  - le mot de passe n'est jamais gardé, la clé jamais servie ;
- la clé est **facultative** et distincte de celle de la 2FA : sans elle, PAdES est refusé
  (`signing_unavailable`) ; documentée dans `.env.example` et `deploy/README.md` ;
- signature PAdES-B-B validée par `pyHanko` dans les tests : intègre, valide, de confiance ;
- mode « prestataire » refusé tant qu'aucun n'est branché (Q17).

**Émission (K11)** :

- par le CO (`certificates.manage`, réauthentification) : les conditions sont vérifiées tout
  de suite, puis la tâche `events.issue_certificates` part en file (`run_jobs`) ;
- traitement par **lots de 100** ; la tâche se relance tant qu'il reste des personnes ;
- idempotente : une demande en attente est réutilisée ; une émission complémentaire n'émet
  que les manquants ;
- conditions perdues entre la demande et l'exécution (signataire retiré…) : journal
  `certificates.issue_failed`, sans nouvelle tentative ;
- e-mail « Attestation disponible » (annexe A2) : lien vers « Mes documents »
  (`/compte/mes-documents`, L7.7), sans PDF ni code ;
- suivi par nature : activée, prête (ou code du problème), éligibles, émises, révoquées,
  présentateurs sans compte, émission en cours.

**Révocation** : motif obligatoire, journal ; la vérification répond « révoquée » ; une
nouvelle attestation peut ensuite être émise.

**Vérification publique (K10)** :

- `GET /v1/public/certificates/{code}`, code de 128 bits en base32 (26 caractères ; casse,
  tirets et espaces tolérés) ;
- répond : nature, nom, édition et ses dates, émission, statut ;
- ni institution, ni empreinte ;
- après anonymisation du titulaire : sans nom (K14) ;
- même 404 pour un code inconnu ou mal formé ;
- limitée à 30 requêtes par minute ; `noindex` (toute l'API) et `no-store`.

**Participant** : `GET /v1/me/certificates` et `…/{id}/pdf` (attestation valide seulement).

**Données personnelles, intégrité, conservation** :

- attestations exportées, **conservées** à l'anonymisation (K14) ;
- contrôle `events.certificate_files` : PDF présent et empreinte intacte ;
- purge des fichiers orphelins : PDF, en-têtes, certificats.

**Autres** :

- codes d'erreur `signing_unavailable` et `signatory_missing` (traduits dans la bibliothèque
  partagée) ;
- énumérations du schéma nommées ;
- treize routes de gestion ajoutées à la matrice (troisième chargeur paresseux du monde ;
  le test d'archivage charge tous les objets avant d'archiver).

**Tests** :

- backend : **4 825 réussis**, 10 ignorés (SQLite) ; la seule vue publique nouvelle
  (vérification) est inscrite dans la liste blanche des vues anonymes ;
- sous MariaDB : `events`, `registrations`, `submissions`, `program`, le registre, le schéma et
  les règles de plateforme (411), plus les cas d'attestation de la matrice (332) ;
- matrice des droits : **3 611 cas** ;
- `events` : 82 tests, dont 24 pour les attestations ;
- front : 388 tests ; client régénéré ;
- `ruff`, lint, `format:check`, `locale/check.sh`, schéma validé sous MariaDB, sans
  avertissement.

**Critère de fin** (« Tests RG-16 au vert ») : atteint.

## 16. Bilan de L7.5 (6 octobre 2026)

**Lettres d'invitation** (K12 ; modèle `InvitationLetter`, migration `events/0003` ;
`apps/events/services/letters.py`) :

- **demande** par le participant (`POST /v1/registrations/{id}/invitation-letter`) :
  - pour une inscription en attente ou confirmée ;
  - données : nom tel que sur le passeport, nationalité, numéro de passeport, dates de
    séjour (90 jours au plus), ambassade ou consulat ;
  - une demande en cours, ou une lettre émise, à la fois ;
  - le participant ne revoit que les trois derniers caractères du numéro ;
- **instruction** par le CO (`letters.manage`) :
  - émission sous réauthentification : signataire désigné **pour les lettres** (K18) ;
    gabarit officiel en A4 portrait, à variables fermées (`{embassy}`, `{passport}`,
    `{stay}`… ajoutées) ; signature PAdES si elle est choisie ; code de vérification ;
    e-mail au participant ;
  - refus motivé (e-mail avec le motif) : le participant peut redemander ;
  - révocation motivée d'une lettre émise ;
  - le numéro entier n'apparaît que dans le détail de l'instruction ;
- la lettre rappelle qu'elle n'engage pas la prise en charge des frais (texte par défaut) ;
- inscription annulée ou expirée : aucune lettre ne peut plus être émise ;
- **vérification publique** : même adresse que les attestations
  (`GET /v1/public/certificates/{code}`) ;
  - réponse de type « lettre » : nom du passeport, ou aucun nom si le titulaire est
    anonymisé ;
  - statut valide ou révoquée.

**Numéro de passeport (K14)** :

- jamais journalisé ;
- effacé à l'anonymisation du compte ;
- effacé par la tâche de conservation `events.passport_numbers`, 30 jours après la fin de
  l'édition ou à son archivage ;
  - **précision de K14** : « la clôture de l'édition » est lue comme ces deux échéances ;
  - tâche de sécurité, appliquée même en simulation des durées D15, la règle étant validée.

**Comptoir** (K13 ; `apps/events/services/counter.py`, `POST …/registrations/counter`,
`registrations.manage`) :

- adresse inconnue : compte **sans mot de passe** (inutilisable), adresse non vérifiée,
  profil minimal (nom, institution, pays) ; journal `registrations.counter_created` ;
- lien de définition du mot de passe envoyé par la réinitialisation d'allauth, en file ;
  - **précision de K13** : la réinitialisation ne vérifie pas l'adresse. À la première
    connexion, allauth demande donc la vérification (vérification obligatoire), soit un
    second e-mail ; aucune connexion n'est possible avant ;
- adresse connue d'un compte actif : inscription rattachée, profil inchangé, aucun lien ;
- compte désactivé ou anonymisé : refus ;
- inscription par le CO au tarif de la période (« sur place » après la clôture, J2) ;
- « réglé au comptoir » : paiement manuel « sur place » enregistré dans la même requête ;
  l'inscription est alors confirmée et son badge imprimable aussitôt ;
- **placé dans `events`** et non dans `registrations`, qui ne dépend pas de `payments`
  (L6).

**Autres** :

- l'émission partage avec les attestations le contexte de pièce (`document_context` :
  signataire, en-tête, PAdES) et l'écriture des intervalles de dates FR et EN
  (`date_range`) ;
- registre des données personnelles (lettres, passeport compris, à l'export) ;
- contrôle `events.letter_files` ; purge des PDF orphelins ;
- e-mails « lettre disponible » et « demande refusée » ;
- sept routes de gestion ajoutées à la matrice (quatrième chargeur paresseux du monde).

**Tests** :

- backend : **4 971 réussis**, 10 ignorés (SQLite) ;
- sous MariaDB : `events`, `registrations`, `payments`, le registre, le schéma et les règles
  de plateforme (297), plus les cas nouveaux de la matrice (162) ;
- matrice des droits : **3 746 cas** ;
- `events` : 93 tests, dont 11 pour les lettres et le comptoir ;
- front : 388 tests ; client régénéré ;
- `ruff`, lint, `format:check`, `locale/check.sh`, schéma validé sous MariaDB, sans
  avertissement.

**Critère de fin** (« Tests au vert ») : atteint.

## 17. Bilan de L7.6 (6 octobre 2026)

**Navigation** (K15) : deux nouvelles catégories du rail.

- **« Jour J »** :
  - accueil (`accueil`, `checkin.scan`) ;
  - sessions du jour (`jour-j/sessions`, `checkin.scan` **ou** `sessions.chair`) ;
  - présences (`checkin.manage`) ;
  - badges (`registrations.read`) ;
  - comptoir (`registrations.manage`).
- **« Attestations et lettres »** :
  - suivi des attestations et modèle (`certificates.manage`) ;
  - lettres d'invitation (`letters.manage`) ;
  - « Ma signature » (`signature.manage`).
- Une capacité d'écran peut être une liste, dont **l'une** suffit (`screenAllowed`,
  `anyCapabilityGuard` dans `shared`).
- Menus du rôle actif pour `VOLUNTEER`, `SESSION_CHAIR` et `SIGNATORY` ; le CO reçoit
  aussi « Comités » (le CO « bénévoles » gère les bénévoles).
- Accueil d'une édition sans `edition.read` :
  - le bénévole arrive sur l'accueil ;
  - le président de séance, sur les sessions du jour ;
  - le signataire, sur sa signature.

**Capacité `sessions.chair`** (backend) :

- le président de séance n'avait aucune capacité ; ses éditions n'apparaissaient donc pas
  dans la gestion ;
- il reçoit `sessions.chair`, simple porte d'entrée : la présidence reste vérifiée session
  par session par le serveur (`CapabilityOrSessionChair`, L7.3) ;
- l'administrateur ne la reçoit pas ;
- test `test_k7_session_chair_capability_belongs_to_the_session_chair_alone`.

**Correctif du schéma** :

- quatre listes courtes étaient décrites comme paginées :
  - les sessions du jour ;
  - le suivi des attestations ;
  - les gabarits ;
  - les signataires ;
- elles sont servies par des vues sans pagination : `DaySessionListViewSet`,
  `CertificateOverviewViewSet` et `pagination_class = None` des gabarits ;
- le client généré type désormais des tableaux.

**Accueil (PWA)** (K4 à K7 ; `core/checkin-desk.ts`, `core/checkin-offline.ts`,
`core/qr-scanner.ts`, `pages/events/reception-page`) :

- **en ligne d'abord** : chaque badge est soumis au serveur, qui répond ;
- **sans réseau** (erreur réseau seulement, jamais un refus de droits) :
  - décision sur la liste téléchargée, par l'empreinte SHA-256 du jeton (Web Crypto),
    identique à celle du serveur ;
  - pointage mis en **file IndexedDB** avec le jeton, seule preuve acceptée ;
  - badge retiré (annulé, remplacé) : refusé ;
  - absent de la liste : dirigé vers le comptoir, rien n'est mis en file ;
  - « déjà pointé » connu de l'appareil (liste et pointages locaux) ;
- **synchronisation** :
  - automatique au retour du réseau, ou par le bouton ;
  - lots de 200 ;
  - chaque réponse sort de la file ;
  - les refus du serveur sont affichés avec le nom ;
- **liste** : effacée à 48 h (à la lecture) et à la déconnexion, comme la file ; la coque
  avertit avant de se déconnecter s'il reste des pointages non envoyés ;
- **mode session** : choix d'une session publiée (titres gardés pour le hors-ligne), ou
  `?session=` depuis les sessions du jour ;
  - le président de séance n'y a que ses sessions ;
  - pas de liste hors ligne pour lui (la liste demande `checkin.scan`) ;
- **caméra** : `getUserMedia` ; `BarcodeDetector` s'il lit les QR, sinon `jsQR`, chargé à
  la demande dans le morceau de l'écran ;
- **résultat** annoncé dans une zone `aria-live` ; couleur doublée d'un texte ;
  vibration ;
- **saisie de la référence** en secours (`checkin.manage`, revérifiée par le serveur) ;
- **nom du poste** repris dans chaque pointage.

**PWA** :

- manifeste et service worker **ajoutés par l'écran d'accueil seul** (bilan de L7.0) ;
  rien en développement ;
- `ngsw-config.json` : coquille en cache ;
- `start_url` `/gestion/accueil` mène à l'accueil de la dernière édition, même hors
  ligne ;
- démarrée sans réseau, la gestion ne renvoie plus vers la connexion du portail (qui ne
  serait pas joignable) ; l'accueil s'ouvre sur la liste de l'appareil
  (`Connectivity.startedOffline`, `receptionGuard`) ;
- icônes 192 et 512 px ;
- `.htaccess` de la gestion :
  - `Permissions-Policy: camera=(self)` ;
  - type du manifeste ;
  - `no-cache` du service worker et de `ngsw.json` ;
- `deploy/smoke-test.sh` contrôle :
  - la caméra permise sous `/gestion/`, refusée au portail ;
  - le manifeste ;
  - `ngsw.json` sans cache long.

**Autres écrans** :

- **sessions du jour** :
  - présents (première page, export complet) ;
  - « Marquer présentée » (président de cette séance ou `program.write`) ;
  - correction motivée (`program.write`) ;
- **présences** : recherche, état, annulation motivée, export ;
- **badges** :
  - lots de 200 par catégorie, téléchargés par lien authentifié (rien n'est stocké) ;
  - dans la fiche d'une inscription : badge, et « Remplacer le badge » (`checkin.manage`,
    motif) ;
- **comptoir** :
  - compte créé ou rattaché ;
  - paiement reçu ;
  - badge à imprimer aussitôt ;
- **attestations** :
  - suivi par nature : éligibles, émises, révoquées, sans compte, condition manquante
    traduite (`signatory_missing`, `signing_unavailable`) ;
  - émission confirmée, puis passage en file ;
  - émission complémentaire ;
  - liste, PDF, révocation motivée ;
- **modèle** :
  - mode de signature, disposition, attestation d'évaluation ;
  - en-tête officiel ;
  - certificat PKCS#12 et mot de passe : le mot de passe n'est ni gardé ni réaffiché ;
  - par nature : signataire désigné, textes FR et EN, variables permises, aperçu PDF ;
  - un texte par défaut laissé tel quel part vide et suit le défaut au lieu d'être figé ;
- **lettres** :
  - liste des demandes à instruire, numéro masqué ;
  - fiche avec le numéro en clair ;
  - émettre, refuser ou révoquer, avec motif ;
- **ma signature** : nom, fonction FR et EN, image (aperçu par l'endpoint authentifié) ;
- **tableau de bord** : carte « Jour J et attestations » (pointés, attestations émises,
  lettres à instruire) ;
- **tarifs** : couleur du badge de chaque catégorie.

**Aide** :

- neuf fiches nouvelles ;
- fiche « Rôles et droits » complétée ;
- bénévole, président de séance et signataire dans l'index par profil.

**Vérifié au navigateur** (build de production, Chromium, API coupée) :

- un autre écran de la gestion n'enregistre aucun service worker ;
- l'accueil ajoute le manifeste et enregistre le service worker (portée `/gestion/`, état
  « NORMAL ») ;
- réseau coupé puis rechargement : l'accueil s'affiche depuis le cache, « Hors ligne »,
  sans erreur JavaScript.

Cette vérification a révélé trois défauts, corrigés :

- **empreinte de `index.html`** : `inject-csp.mjs` réécrit `index.html` après le build,
  donc après le calcul des empreintes de `ngsw.json`. Le service worker aurait refusé la
  version. Le script `build` régénère maintenant `ngsw.json` (`ngsw-config`) puis contrôle
  toutes les empreintes (`web/scripts/check-ngsw.mjs`, testé ; `deploy/README.md`) ;
- **réponse du service worker sans réseau** : une page contrôlée ne voit jamais le
  statut 0 ; le service worker répond lui-même **504**. La gestion prenait ce 504 pour une
  absence de session et renvoyait vers la connexion du portail. Désormais 0, 502, 503 et
  504 valent « serveur injoignable » (`isUnreachable`), au démarrage comme à l'accueil ;
- **mise en page de l'édition** : `/me` étant inconnu hors ligne, elle affichait « accès
  refusé » au lieu de l'écran d'accueil.

**Budget** :

- l'avertissement à la déconnexion (fenêtre Material) est chargé à la demande, comme la
  réauthentification ; sans cela, il ajoutait 290 ko au bundle initial ;
- bundle initial de la gestion : **382 ko** (avertissement à 500 ko) ;
- `jsQR` : morceau à la demande de 130 ko (27 ko compressés), déclaré en
  `allowedCommonJsDependencies` ;
- portail inchangé : 368,6 ko, avertissement déjà connu (L5, L6).

**Écarts et précisions** :

- **précision de K5** :
  - la file de pointages garde le jeton jusqu'à l'envoi (bilan de L7.2) ;
  - un pointage « déjà pointé » ou refusé sur l'appareil n'est pas mis en file ;
  - un QR de plus de 128 caractères est « inconnu » sans appel au serveur ;
- **portail et gestion partagent l'origine** (un seul domaine) : la liste et la file en
  IndexedDB sont lisibles par tout script du domaine. La protection reste celle de K5 :
  minimisation, 48 h, effacement à la déconnexion. Elle s'ajoute à la CSP à empreintes des
  deux applications ;
- le parcours complet (pointage hors ligne puis synchronisation, avec une vraie session)
  relève de l'E2E de L7.8.

**Tests** :

- backend : **4 972 réussis**, 10 ignorés (SQLite) ;
- sous MariaDB : `events`, rôles, schéma et règles de plateforme (153) ;
- matrice des droits : 3 746 cas, inchangés ;
- deux tests des scripts de déploiement adaptés : après la CSP, seules les étapes du
  service worker ;
- front : **453 tests** (scripts 13, `shared` 79, portail 144, gestion 217), dont 65
  nouveaux :
  - poste d'accueil : en ligne, hors ligne, 504 du service worker, refus, lots ;
  - liste et file : empreinte identique à celle du serveur, expiration, effacement ;
  - lecture du QR ;
  - gardes et démarrage hors ligne ;
  - navigation ;
  - redirections ;
  - les neuf écrans ;
  - empreintes de `ngsw.json` ;
- `ruff`, lint, `format:check`, `locale/check.sh`, schéma validé sous MariaDB, sans
  avertissement ;
- build de production vérifié au navigateur (voir plus haut).

**Critère de fin** (« Démo H côté gestion ») : atteint pour la gestion. La démo complète,
téléphone réel compris, relève de L7.8.

## 18. Bilan de L7.7 (6 octobre 2026)

**« Mes documents »** (K15 ; `/compte/mes-documents`, `account/documents/`) :

- **badge** :
  - pour l'inscription confirmée dont le QR existe : téléchargement du PDF par l'endpoint
    authentifié (généré à la demande, jamais stocké) ;
  - rappel que le QR est l'accès à l'accueil et ne se partage pas ;
  - avant la confirmation : renvoi vers « Mon inscription » ;
- **attestations** (`GET /v1/me/certificates`) :
  - nature, édition et titre de la communication ;
  - date d'émission, PDF et page de vérification ;
  - une attestation révoquée est signalée, sans PDF (le serveur le refuse) ;
- **lettre d'invitation** (K12), pour l'inscription en cours :
  - demande : nom du passeport, nationalité, numéro, dates du séjour, ambassade ;
  - suivi :
    - en cours d'examen ;
    - refusée avec son motif, puis nouvelle demande pré-remplie (sans le numéro de
      passeport, jamais renvoyé en clair) ;
    - émise : PDF et rappel de sa portée ;
    - révoquée ;
  - erreurs de champ posées sur le formulaire ; refus de règle (409), message du serveur ;
- liens :
  - menu de l'espace compte ;
  - accueil du compte ;
  - « Mon inscription », sous le QR ;
- l'e-mail « attestation disponible » (L7.4) pointait déjà vers cette adresse.

**Vérification publique** (K10 ; `/verification/<code>` et `/verification`) :

- page hors des préfixes de langue, **rendue dans le navigateur** (`RenderMode.Client`,
  jamais pré-rendue), servie par le repli SPA existant du `.htaccess` ;
- résultat :
  - nature ;
  - titulaire, ou « non communiqué » si la personne est anonymisée ;
  - conférence et ses dates ;
  - date d'émission ;
  - statut : authentique, ou révoquée avec sa date ;
  - lettre d'invitation distinguée de l'attestation ;
- code inconnu ou mal formé : un seul message, sans détail ; débit dépassé : message
  d'erreur ;
- saisie manuelle du code : majuscules, espaces et tirets de recopie retirés ;
- `noindex` :
  - balise meta posée par la page ;
  - `Disallow: /verification` dans `robots.txt` ;
  - **précision de K10** : pas d'en-tête `X-Robots-Tag` par chemin (`<If>` du
    `.htaccess`), dont la prise en charge chez o2switch n'est pas vérifiée ;
- `deploy/smoke-test.sh` contrôle :
  - le `Disallow` ;
  - le service de `/verification/<code>` par la coquille rendue dans le navigateur.

**Vérifié au navigateur** (build de production du portail, API de vérification
simulée) :

- titre de la page ;
- résultat « Attestation authentique » avec titulaire, conférence et dates ;
- balise `noindex` ;
- code inconnu : message unique ;
- aucune erreur JavaScript.

**Tests** :

- portail : **158 tests**, dont 14 nouveaux :
  - « Mes documents » : badge, attestations valides et révoquées ;
  - lettre : demande, refus de règle, nouvelle demande, lettre émise ;
  - vérification : valide, révoquée et anonymisée, lettre, inconnue, débit, saisie ;
- lint, `format:check` ;
- build complet ;
- budget du portail : 368,9 ko (avertissement déjà connu, +0,3 ko pour les deux routes).

**Critère de fin** (« Démo H côté portail ») : atteint, hors démo sur o2switch (L7.8).
