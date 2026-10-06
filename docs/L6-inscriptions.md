# Lot L6 — Inscriptions et paiements : bilan et exploitation

Ce document résume ce que livre le lot L6 de GEST-CONF et comment l'exploiter. Le détail des
choix, des vérifications et des défauts trouvés est dans
[`L6-inscriptions-plan.md`](L6-inscriptions-plan.md) (décisions J1 à J16 au §2, bilans des
étapes aux §11 à §18). L'étude est mise à jour en conséquence (§22 « Mises à jour issues du
lot L6 »).

## 1. Ce qui est livré

| Étape | Contenu | Commit |
|---|---|---|
| L6.0 | Vérifications : CinetPay (API v1), `fpdf2`, `segno`, devises ISO 4217, `.htaccess` et webhook, appels sortants (V29) | `7700b7c` |
| L6.1 | Modèles `registrations` et `payments`, capacités, paramètres, mentions de facturation, matrice, registre | `f7aaec5` |
| L6.2 | Tarification : périodes, zones, catégories, grille, options à quota, codes promo, devis | `ebe3ff4` |
| L6.3 | Workflow d'inscription, commande, expiration, annulation, gratuité, justificatif ; paiement manuel ; factures, avoirs, pro forma (PDF) | `046d448` |
| L6.4 | Paiement en ligne : fournisseurs (factice, CinetPay), webhook, interrogation du statut, `sync_payments` ; RG-11 au programme | `ef70d64` |
| L6.5 | Suivi financier et exports (serveur) ; écrans de la gestion : inscriptions, paiements, pièces, finances, tarifs, facturation ; D13 pour les échéances | `173feee`, `bbe6fb0` |
| L6.6 | Portail : page publique « Inscription », espace « Mon inscription » | `5adafdd` |
| L6.7 | Parcours de bout en bout, recette, bilan, étude (§22), `CLAUDE.md` | dernier commit du lot |

Intégration continue : à faire passer par une PR (sur demande).

## 2. Parcours couverts (démo G)

- **CO « finances »** (et administrateur), dans la gestion, 2FA imposée :
  - « Paramétrage › Tarifs » :
    - devise, pays « locaux », moyens proposés (en ligne seulement avec un fournisseur
      configuré), délais de paiement ;
    - date limite d'annulation **à l'heure de l'édition** et parts remboursées ;
    - catégories et grille période × zone ;
    - options à quota ;
    - codes promo, dont la date limite est aussi à l'heure de l'édition ;
  - « Paramétrage › Facturation » : émetteur, TVA ou mention, coordonnées bancaires,
    préfixes (figés dès la première pièce) ;
  - « Inscriptions » :
    - liste filtrée et export CSV ;
    - saisie pour un compte existant ;
    - fiche : paiement reçu hors ligne, pro forma, gratuité, annulation motivée,
      remboursement fait hors plateforme qui émet l'avoir ;
  - « Paiements », « Factures et avoirs » (PDF, export comptable), « Finances » (tableau de
    bord, émission des factures en attente).
- **CO « secrétariat »** : mêmes actions sur les inscriptions, sans tarifs ni finances.
- **Chair** : consultation des inscriptions et des finances, sans action. **Autres membres du
  CO** : consultation des inscriptions et des tarifs.
- **Participant** (portail) :
  - page publique « Inscription » : dates, grille, options, moyens de paiement ;
  - « Mon inscription » (`/compte/mon-inscription`) :
    - prix calculé par le serveur ;
    - commande, puis paiement en ligne sur la page hébergée du prestataire, ou pro forma
      pour un virement ;
    - justificatif, identité de facturation ;
    - facture et code QR d'accès à la confirmation ;
    - annulation selon les règles de l'édition.
- **Programme** : avec « Exiger l'inscription d'un présentateur » (RG-11), une communication
  placée sans présentateur inscrit est un conflit, qui bloque la publication ; le
  planificateur le signale aussi sur la communication.

## 3. Sécurité et données personnelles, en bref

- **Aucune donnée de carte** (règle n° 7) : paiement sur la page hébergée du prestataire, le
  navigateur y est **dirigé** (aucun formulaire vers l'extérieur, CSP `form-action 'self'`).
- **RG-15** : une notification n'est qu'un signal.
  - Elle est enregistrée (ajout seul) et son jeton de transaction comparé à temps constant
    (empreinte SHA-256 seulement en base).
  - **Seule l'interrogation du statut** chez le prestataire confirme.
  - Rejeu sans effet.
  - Le retour du navigateur ne confirme rien : « Mon inscription » interroge à son tour.
- **Montants calculés par le serveur seul**, en `Decimal`, exacts dans la devise ; le
  navigateur n'envoie que des codes.
- **Pièces de facturation** : numérotées sans trou par série et par année, en ajout seul,
  PDF figés hors racine web, empreinte vérifiée à chaque téléchargement et par
  `check_integrity` ; servies par des endpoints authentifiés (règle n° 8), comme les
  justificatifs (type vérifié par contenu) et le QR.
- **Droits** :
  - `registrations.read` (administrateur, Chair, CO) ;
  - `registrations.manage` (administrateur, CO « finances » et « secrétariat ») ;
  - `pricing.write` (administrateur, CO « finances ») ;
  - `finance.read` (administrateur, Chair, CO « finances ») ;
  - réauthentification récente pour le paiement manuel, le remboursement, les exports et
    les mentions de facturation ;
  - le président du CS et les relecteurs n'ont aucun accès.
- **Journal** : chaque écriture financière et chaque export (RG-17).
- **Données personnelles** :
  - inscriptions, paiements, pièces et remboursements figurent à l'export ;
  - anonymisation refusée tant qu'une inscription est active dans une édition non archivée ;
  - ensuite, identité de facturation et jeton QR effacés ;
  - **factures et avoirs conservés** avec l'identité figée (obligation légale, durée à
    préciser avec Q8).

## 4. Exploitation

- **Cron**, à ajouter dans cPanel (voir [`deploy/README.md`](../deploy/README.md)) :

  ```text
  37 * * * *   $HOME/gestconf-app/deploy/cron.sh expire_registrations
  41 * * * *   $HOME/gestconf-app/deploy/cron.sh sync_payments
  ```

- **Variables d'environnement** (`backend/.env.example`), jamais dans le dépôt :
  - `GESTCONF_PAYMENT_PROVIDER` : vide (paiement manuel seul), `fake` ou `cinetpay` ;
  - pour CinetPay : `CINETPAY_API_KEY`, `CINETPAY_API_PASSWORD`, `CINETPAY_SANDBOX`,
    `CINETPAY_TIMEOUT_SECONDS`.
  - La production refuse un fournisseur inconnu, le fournisseur factice (sauf recette
    déclarée par `GESTCONF_ALLOW_FAKE_PAYMENTS`) et CinetPay sans identifiants.
- **URL de notification à déclarer chez le prestataire** :
  `https://<domaine>/api/v1/payments/webhook/cinetpay`. Le `.htaccess` la laisse passer vers
  Passenger.
- **Avant d'ouvrir les inscriptions** :
  - dates clés `registration_open`, `early_bird_end`, `registration_close` ;
  - tarifs et mentions de facturation (sans elles, les paiements passent mais aucune facture
    ne s'émet : « Émettre les factures en attente » une fois les mentions complètes) ;
  - remise en ligne du portail (`deploy/deploy.sh --portal-only`) : la page publique est
    pré-rendue.
- **Liens des e-mails** : `/compte/mon-inscription` (commande, confirmation, annulation,
  expiration) ; retour de paiement : `/compte/mon-inscription?paiement=<référence>`.
- **Contrôles d'intégrité** (`check_integrity`) :
  - `registrations.totals` : total égal à la somme des lignes ; confirmée payée, offerte ou
    gratuite ;
  - `registrations.reservations` : places d'options et utilisations de codes cohérentes ;
  - `billing.series` : séries continues ;
  - `billing.files` : PDF présents et intacts.
- **À vérifier sur o2switch** :
  - appels sortants vers CinetPay (contrôle V29 de `deploy/check-o2switch.sh`) ;
  - réception des notifications (pare-feu applicatif éventuel) ;
  - délai de réponse au webhook (moins de 10 secondes).

## 5. Tests

- **Backend** : 3 395 tests sous SQLite et 3 404 sous MariaDB (suite complète), dont la
  matrice des droits (2 273 cas). Ils couvrent notamment :
  - calcul du prix : périodes, zones, options, remises arrondies à la devise ;
  - quotas et codes promo sous verrou, avec un test de concurrence sur MariaDB ;
  - workflow (seul écrivain du statut, méta-test), expiration, annulation et remboursement
    dû ;
  - paiement manuel, factures, avoirs et pro forma :
    - numérotation sans trou ;
    - PDF identiques pour des données identiques ;
    - empreinte vérifiée ;
  - paiement en ligne avec le fournisseur factice :
    - notification valide, jeton faux, rejeu, montant différent ;
    - fournisseur injoignable puis tâche de reprise ;
    - paiement après expiration, réconciliation et abandon ;
  - client CinetPay sur HTTP simulé ;
  - RG-11 ; D13 (heure inexistante ou ambiguë) ; matrice des droits ; données
    personnelles ; lien des e-mails vers « Mon inscription ».
- **Front (Vitest)** : 385 tests (shared 78, portail 144, gestion 163) et 11 tests des scripts de build. Ils couvrent :
  - les écrans de la gestion : liste, fiche et actions, tarifs, mentions, finances ;
  - le badge RG-11 du planificateur ;
  - la page publique et « Mon inscription » : devis, commande, redirection, retour de
    paiement confirmé, en vérification ou échoué, annulation.
- **Bout en bout (Playwright)** : le parcours en série se prolonge :
  - le CO « programme » exige RG-11 : la présentatrice non inscrite est signalée ;
  - le CO « finances » complète les mentions de facturation ;
  - l'auteure s'inscrit :
    - page publique, puis devis (préférentiel, tarif local) ;
    - commande en ligne, page du fournisseur factice, « Payer » ;
    - confirmation par la notification vérifiée ;
    - facture (PDF) et code QR ; RG-11 levée ;
  - le CO « finances » saisit l'inscription d'un second participant par virement,
    enregistre le paiement (facture), annule avec remboursement intégral, enregistre le
    remboursement (avoir) ; le tableau de bord le reflète.
- **Recette locale dans Chromium**, sur la base laissée par le parcours :
  - écrans de la gestion à 1366 et 375 px, formulaires ouverts compris ;
  - page publique et « Mon inscription » à 1366 et 375 px ;
  - aucun débordement horizontal, aucune erreur dans la console. Deux défauts trouvés et
    corrigés en chemin (voir le plan, §18).

## 6. Ce qui reste à faire ou à décider

**Avant la mise en ligne des inscriptions** :

- démo G sur o2switch, avec les lignes de cron et la notification de paiement réelle ;
- compte marchand CinetPay et clés de bac à sable (Q7) ;
- fournisseur d'e-mails de production (D10).

**Décisions du commanditaire** :

- **Q7** :
  - tarifs ;
  - agrégateur : CinetPay retenu (API v1), mais **la carte bancaire n'apparaît pas dans son
    API v1**, à confirmer avec CinetPay ; sinon, la carte passe par le virement ou par un
    second agrégateur ;
  - pas d'euro chez CinetPay : une édition en EUR n'a que le paiement manuel.
- **Q8** :
  - entité de facturation et mentions légales ;
  - durée de conservation des factures ;
  - format du numéro (`F-<édition>-<année>-<rang>`) : si une même entité facture toutes les
    éditions, la loi peut exiger une série unique.
- **J15** (« Mon programme » du participant, notification des inscrits) : reportée, à
  redemander si utile.
- **Adresse de l'espace** : `/compte/mon-inscription` au lieu de `/compte/inscription` (J13),
  occupée par la création de compte depuis L1.
- **Ouverts depuis L5** :
  - Q14 ;
  - transition `ACCEPTED_MINOR → WITHDRAWN` ;
  - seuil d'avertissement du bundle initial du portail : 368,6 ko pour 365 ko, dont 0,8 ko
    venu de L6.

**Reporté** :

- inscription au comptoir d'une personne **sans compte** (L7, jour J) ;
- remboursement par l'API de l'agrégateur, paiement partiel, groupes en un seul paiement
  (P3) ;
- hébergement groupé ; lecture des QR au check-in (L7).
