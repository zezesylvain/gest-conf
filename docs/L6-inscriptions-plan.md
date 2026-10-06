# Lot L6 — Inscriptions et paiements : plan d'implémentation

> **Statut : proposition, à valider** (décisions J1 à J16 au §2, questions au §10). Rien n'est
> implémenté avant validation. L5 est clos (bilan : `docs/L5-programme.md`).
>
> Sources :
> - étude §4 M9, §5.3 (parcours d'inscription et de paiement), §6 (RG-11, RG-14, RG-15,
>   RG-17, RG-18), §7 (bibliothèques : `fpdf2` ou ReportLab, `segno`, agrégateur), §8.2
>   (« Inscriptions, paiements, jour J »), §8.3 (numérotation), §9.2, §9.3 (« Paiement »),
>   §10.1 et §10.2, §11 (cron `sync_payments`), §14 (L6 : 12 à 16 j-h), §15 (Q7, Q8, Q12,
>   Q14) ;
> - mises à jour §17 à §21 (dates clés `registration_open`, `early_bird_end`,
>   `registration_close` déjà réservées en L1 ; RG-11 désactivable en L5 ; page « Inscription »
>   « à venir » depuis L2) ;
> - CLAUDE.md, règles n° 7 (aucune donnée de carte ; paiement valide sur webhook vérifié),
>   n° 8 (fichiers hors racine web) et n° 9 (cron idempotent et verrouillé).

## En bref

| | |
|---|---|
| **Objectif** | Un participant s'inscrit dans le portail : catégorie, options, code promo, puis paiement en ligne (agrégateur) ou manuel (virement, sur place, bon de commande). L'inscription n'est confirmée que sur **webhook vérifié** (RG-15) ou validation manuelle par le CO « finances ». Il reçoit facture, reçu et QR (pour L7). Le CO suit les inscriptions, rapproche les paiements, émet avoirs et exports comptables. RG-11 devient effective pour le programme. |
| **Point dur** | **Argent et obligations légales** : montants en `Decimal` selon la devise (le franc CFA n'a pas de décimales) ; factures numérotées sans trou par année (RG-14), jamais supprimées ; idempotence des webhooks et de la réconciliation ; aucune donnée de carte. **L'agrégateur n'est pas choisi (Q7)** et l'entité de facturation n'est pas connue (Q8). |
| **Hors périmètre** | Remboursement automatique par l'API de l'agrégateur (P3 : saisi à la main, avec avoir) ; inscriptions de groupe en un seul paiement (proposé en P2 tardif, §1) ; hébergement groupé ; badges et check-in (L7) ; « Mon programme » du participant et notification des inscrits (proposés ici en option, J15) ; sponsors (L8). |
| **Charge** | **24 à 31 j-h** (étude : 12 à 16). Détail au §8. |
| **Démo G** | Le CO « finances » crée les catégories (auteur, étudiant, participant, intervenant invité gratuit), les tarifs préférentiel, normal et sur place, local et international, deux options (atelier, dîner) et un code promo. Une étudiante s'inscrit et paie en mobile money (bac à sable) : le webhook confirme, elle reçoit sa facture et son QR. Un enseignant demande un bon de commande pour son université ; le CO valide le virement à réception. Une annulation produit un avoir. Avec RG-11 active, le programme refuse de publier une communication dont aucun présentateur n'est inscrit. Le tableau de bord financier et l'export comptable sont à jour. |

## 1. Périmètre

| Fonction (étude M9, §5.3) | Priorité | Dans L6 |
|---|---|---|
| Catégories, tarifs par période et par zone (local, international) | P2 | Oui (J2) |
| Options (atelier, dîner, visite) avec quota | P2 | Oui (J3) ; hébergement groupé : non |
| Codes promo, gratuités | P2 | Oui (J4) |
| Groupes (plusieurs personnes, un paiement) | P2 | **Non** : bon de commande par personne (J7) ; à reprendre si besoin |
| Paiement en ligne (mobile money, carte) via agrégateur | P2 | Oui, derrière une interface de fournisseur (J6) ; agrégateur à choisir (Q7) |
| Virement, sur place, bon de commande (pro forma) | P2 | Oui (J7) |
| Factures et reçus PDF numérotés ; avoirs (RG-14) | P2 | Oui (J8) |
| Annulations et remboursements selon règles | P2 | Oui, remboursement saisi à la main (J9) |
| RG-11 (présentateur inscrit) | P1 (règle) | Oui (J10) |
| Exports comptables, tableau de bord financier | P2 | Oui (J12) |
| QR d'inscription | P2 | Oui, généré ; lu en L7 (J11) |

**Écarts avec l'étude, à valider** :

- statuts d'inscription et transitions par un service unique, comme les soumissions (J5) ;
- RG-11 traitée comme un conflit bloquant à la publication du programme, et non comme un
  filtre de la liste « à programmer » (J10) ;
- facture émise au paiement seulement ; le bon de commande est une pro forma non numérotée
  dans la série des factures (J7, J8).

## 2. Décisions à valider

| # | Sujet | Proposition |
|---|---|---|
| J1 | Droits (Q12, matrice §3.3) | Capacités nouvelles. **`registrations.read`** : `ADMIN`, `CHAIR`, `OC_MEMBER` (toutes fonctions). **`registrations.manage`** (validation manuelle, gratuités, annulations, modification d'une inscription) : `ADMIN`, CO « finances » et « secrétariat ». **`pricing.write`** (catégories, tarifs, options, codes promo, règles d'annulation, mentions de facturation) : `ADMIN`, CO « finances ». **`finance.read`** (paiements, factures, avoirs, tableau de bord, exports comptables) : `ADMIN`, `CHAIR`, CO « finances ». Le président du CS n'a aucun accès aux inscriptions. 2FA déjà imposée à ces rôles. Réauthentification récente pour : validation manuelle d'un paiement, avoir, export comptable, modification des mentions de facturation |
| J2 | Catégories et tarifs | Catégories par édition, **liste éditable** préremplie (auteur, participant, étudiant, chercheur, professionnel, accompagnant, intervenant invité, membre de comité), libellés FR et EN, justificatif demandé ou non (étudiant). **Tarif** = catégorie × **période** × **zone**. Périodes déduites des dates clés : préférentiel jusqu'à `early_bird_end`, normal jusqu'à `registration_close`, puis « sur place » (inscription en ligne fermée, tarif appliqué par le CO). Zone : « local » (pays listés pour l'édition, défaut : pays de l'édition) ou « international », d'après le pays du profil. Un montant nul vaut gratuité. **Une devise par édition** (défaut XOF), décimales selon ISO 4217 (0 pour XOF, 2 pour EUR) ; pas de conversion |
| J3 | Options | Article facultatif (atelier, dîner, visite) : prix (par zone), **quota** (places), catégories autorisées, libellés FR et EN. Le quota se réserve à la commande et se libère à l'expiration ou à l'annulation. Hébergement : hors L6 |
| J4 | Codes promo | Code par édition : pourcentage ou montant, sur l'inscription seule ou avec options, catégories visées, nombre maximal d'utilisations, date limite. Une utilisation est **réservée** à la commande et **consommée** à la confirmation (compteur sous verrou). Gratuité nominative : décidée par le CO (`registrations.manage`), motif journalisé |
| J5 | Cycle de vie | Une inscription par personne et par édition. Statuts : **`pending`** (commande, montant figé, quota et code réservés) → **`confirmed`** (paiement validé, ou gratuité) → **`cancelled`** (par le participant avant échéance, ou par le CO) ; **`expired`** (commande non payée à l'échéance). Transitions par un **service unique** (`registrations/workflow.py`), journalisées, comme pour les soumissions (règle n° 4 transposée). Échéance de paiement d'une commande en ligne : 72 h ; d'un bon de commande : 30 jours, sans dépasser la veille de la conférence. Commande `expire_registrations` (cron horaire) |
| J6 | Paiement en ligne (RG-15) | **Interface de fournisseur** (`PaymentProvider` : initier un paiement, vérifier une notification, interroger un statut) ; un fournisseur **factice** pour les tests et la démonstration ; **premier fournisseur réel : CinetPay**, candidat de l'étude, à vérifier en L6.0 (contrat, bac à sable, signature des notifications, mobile money et carte, frais). Paiement sur la **page hébergée** de l'agrégateur (aucune donnée de carte chez nous, règle n° 7). Une inscription n'est confirmée que par une **notification vérifiée** (signature) **et** une interrogation du statut côté serveur ; le retour du navigateur n'affiche qu'un état « en cours ». Notifications **idempotentes** (référence de transaction unique), montant et devise contrôlés. `POST /v1/payments/webhook/{provider}` : public, sans CSRF, limité en débit, corps brut journalisé sans donnée sensible. Commande **`sync_payments`** (cron horaire) : réconciliation des paiements en attente |
| J7 | Paiement manuel | **Virement** et **sur place** : le participant choisit ; une **pro forma** (bon de commande, PDF, mentions de facturation, références bancaires) est émise. Le CO « finances » valide le paiement reçu (moyen, référence, date, montant), avec réauthentification : l'inscription est confirmée et la facture émise. Montant partiel : non (P3) |
| J8 | Factures (RG-14) | **Facture émise au paiement**, numérotée **sans trou par année** (compteur verrouillé en transaction, préfixe paramétrable, ex. `F2027-00001`) ; elle vaut reçu (mention « acquittée », moyen et date). Jamais supprimée ni modifiée : une annulation produit un **avoir** numéroté dans sa propre série, lié à la facture. Pro forma : série distincte, non comptable. PDF généré par **`fpdf2`** (pur Python, à confirmer en L6.0 face à ReportLab), stocké hors racine web (règle n° 8), servi par un endpoint authentifié ; empreinte SHA-256 conservée. **Mentions de facturation** de l'édition (entité, adresse, identifiants fiscaux, TVA éventuelle, pied de page) : Q8 ; tant qu'elles manquent, **aucune facture ne s'émet** (paiements possibles, factures émises a posteriori) |
| J9 | Annulation et remboursement | Règles par édition : date limite d'annulation par le participant, pourcentage remboursé avant et après. Le remboursement lui-même se fait **hors plateforme** (tableau de bord de l'agrégateur, virement) ; le CO l'enregistre, l'avoir s'émet. Remboursement par l'API de l'agrégateur : P3 |
| J10 | RG-11 | Si `presenter_registration_required` (paramètre de L5) est actif, une communication placée dont **aucun présentateur** n'a d'inscription confirmée produit un **conflit `registration`** dans le planificateur : signalé dans le brouillon, **bloquant à la publication** (comme RG-12 et RG-13, I6). Un présentateur s'identifie par son compte ou son adresse vérifiée. Le CO voit l'état d'inscription des présentateurs dans la liste « à programmer » |
| J11 | Confirmation et QR | À la confirmation : e-mail (facture en lien, pas en pièce jointe), **jeton QR** unique et non devinable (`segno`, pur Python), affiché dans « Mon inscription » ; il servira au check-in (L7). Révocable (annulation) |
| J12 | Gestion | Rubrique « Inscriptions » : liste filtrable (catégorie, statut, moyen, impayés), détail (historique, paiements, factures), validation manuelle, gratuité, annulation ; « Paiements » (rapprochement, notifications reçues) ; « Factures et avoirs » ; « Tableau de bord financier » (recettes par moyen et catégorie, impayés, prévisions) ; « Paramétrage › Tarifs » (catégories, périodes, zones, options, codes promo, règles d'annulation, mentions de facturation). Exports CSV (inscriptions, factures, paiements) journalisés, protégés contre l'injection de formules. Chaque écran est inscrit dans le rail et a sa fiche d'aide |
| J13 | Portail | Page publique « Inscription » (fin du « à venir ») pré-rendue : catégories, tarifs par période et par zone, options, dates, moyens de paiement. Espace compte **`/compte/inscription`** : parcours catégorie → options → code promo → récapitulatif → paiement ; suivi (statut, échéance), factures, pro forma, QR, annulation. Accessible au clavier, sans Material dans le pré-rendu public |
| J14 | Données personnelles et conservation | Inscriptions, paiements et factures au registre (export). **Les factures et avoirs sont conservés** avec l'identité de facturation (obligation légale, durée à préciser, Q8) : l'anonymisation d'un compte les **exclut** et le signale ; le reste de l'inscription est anonymisé selon RG-18. Point resté ouvert depuis L1 (§17, RG-18) : à trancher |
| J15 | Option : inscrits | Après validation de L6, « Mon programme » du participant (sessions favorites, `.ics`) et notification des inscrits d'un changement de programme (prolongement d'I16) : **proposés en option** (+2 à 3 j-h), sinon reportés |
| J16 | Ordre | L6.0 vérifications ; L6.1 à L6.4 serveur ; L6.5 et L6.6 écrans ; L6.7 E2E et documentation |

## 3. Modèle de données (nouvelles applications `registrations` et `payments`, additif)

- `registrations` :
  - `registration_category` : édition, code, libellés FR et EN, justificatif demandé, actif,
    position ;
  - `fee` : catégorie, période (`early`, `regular`, `onsite`), zone (`local`,
    `international`), montant ; unique par (catégorie, période, zone) ;
  - `registration_option` et son tarif par zone ; quota, places réservées ;
  - `promo_code` : édition, code (unique, sans tenir compte de la casse), type et valeur,
    portée, catégories, utilisations maximales, réservées et consommées, date limite ;
  - `registration` : édition, compte, catégorie, statut, période et zone retenues, lignes
    figées (inscription, options, remise), total, devise, échéance, jeton QR (unique),
    moyen de paiement choisi, dates ; unique par (édition, compte) hors annulées ;
  - `registration_status_history` : en ajout seul.
- `payments` :
  - `payment` : inscription, fournisseur, référence de transaction (unique par
    fournisseur), montant, devise, statut, notifications reçues (empreintes), dates ;
  - `payment_notification` : en ajout seul (fournisseur, référence, signature valide ou non,
    reçue le, corps sans donnée sensible) ;
  - `invoice` : édition, nature (`invoice`, `credit_note`, `proforma`), numéro (unique par
    série et année), inscription, facture d'origine (avoir), montant, devise, mentions
    figées, fichier privé, empreinte, émise le ;
  - numérotation par le compteur sans trou de L3 (`core.Counter`, une portée par série et
    par année, `apps.core.counters.next_value`), prévu dès L3 pour les factures.
- Édition : devise, pays « locaux », mentions de facturation, règles d'annulation, délais de
  paiement (ou table de paramètres dédiée).
- **Contrôles d'intégrité** : numérotation continue de chaque série ; inscription confirmée
  ⇔ paiement validé ou gratuité ; total = somme des lignes ; quotas et utilisations de codes
  cohérents.

## 4. API

**Public** : `GET /v1/public/registration` (catégories, tarifs, options, dates, moyens de
paiement ; lu au build du portail).

**Participant** : `GET/POST /v1/registrations` (commande : catégorie, options, code promo,
moyen) ; `POST /v1/registrations/{id}/quote` (calcul sans engagement) ;
`POST /v1/registrations/{id}/pay` (lien vers la page de l'agrégateur, ou pro forma) ;
`POST /v1/registrations/{id}/cancel` ; `GET …/invoices/{n}` (PDF, authentifié).

**Agrégateur** : `POST /v1/payments/webhook/{provider}` (public, signé, idempotent).

**Gestion** (`…/manage/editions/{id}/…`, 2FA) : `registrations` (liste, détail, validation
manuelle, gratuité, annulation), `payments`, `invoices` (avoirs), `pricing` (catégories,
tarifs, options, codes promo, règles, mentions), `finance/dashboard`, exports CSV.

## 5. Frontend

- **Gestion** : rubrique « Inscriptions » (J12) et « Paramétrage › Tarifs » ; carte
  « Inscriptions » au tableau de bord ; fiches d'aide.
- **Portail** : page « Inscription » pré-rendue ; `/compte/inscription` (J13) ; lien dans la
  navigation du compte.
- **Planificateur** : conflit `registration` (RG-11) et état d'inscription des présentateurs.

## 6. Sécurité

- **Aucune donnée de carte** ; page de paiement hébergée par l'agrégateur.
- **RG-15** : notification signée **et** statut interrogé côté serveur ; montant, devise et
  référence contrôlés ; notifications rejouées sans effet ; secret de signature dans
  l'environnement (règle n° 11), jamais dans le dépôt.
- Endpoint de notification : sans session ni CSRF, limité en débit ; `.htaccess` à vérifier
  (il ne doit pas intercepter `/api/v1/payments/webhook/…`).
- **Montants calculés par le serveur seul** (`Decimal`) ; le navigateur n'envoie que des
  choix.
- Factures immuables, servies par un endpoint authentifié ; empreinte vérifiée par le
  contrôle d'intégrité.
- Réauthentification et journal pour les actions financières (J1) ; matrice des droits
  étendue, un test par case.
- Concurrence : quota, code promo et numérotation sous verrou ; tests sur MariaDB.

## 7. Tests

- **Unitaires** : calcul du prix (période, zone, options, remise, arrondi par devise),
  quotas, codes promo, échéances, numérotation sans trou sous concurrence (MariaDB).
- **Workflow** : transitions d'inscription, expiration, annulation et avoir, RG-11.
- **Paiement** : fournisseur factice ; notification valide, invalide, rejouée, montant
  différent ; réconciliation ; retour du navigateur sans effet (RG-15).
- **API** : matrice des droits ; aucune donnée de paiement sensible dans les réponses ;
  factures servies au seul titulaire et au CO habilité.
- **PDF** : contenu des factures, avoirs et pro forma, mentions, numéro, devise.
- **Front** : parcours d'inscription, écrans de gestion.
- **E2E** (L6.7) : inscription → paiement factice → webhook → facture et QR ; bon de
  commande → validation manuelle ; annulation → avoir ; RG-11 au programme.

## 8. Étapes

| Étape | Contenu | Critère de fin | Charge |
|---|---|---|---|
| L6.0 | Vérifications : agrégateur (bac à sable, signature, mobile money, carte, frais), `fpdf2` ou ReportLab, `segno`, devise XOF, `.htaccess` et notification | Choix consignés | 1 – 1,5 |
| L6.1 | Modèles `registrations` et `payments`, capacités, paramètres, matrice, registre | Matrice au vert | 2,5 – 3 |
| L6.2 | Tarification : catégories, tarifs, options, codes promo, calcul du prix, quotas | Tests de calcul au vert | 2,5 – 3 |
| L6.3 | Inscriptions : workflow, commande, expiration, annulation ; paiement manuel ; factures, avoirs, pro forma (PDF) ; numérotation | Tests du workflow et des factures au vert | 4 – 5 |
| L6.4 | Paiement en ligne : interface, fournisseur factice, premier fournisseur réel, notifications, `sync_payments` ; RG-11 au programme | Tests RG-15 au vert | 3 – 4 |
| L6.5 | Écrans de gestion : inscriptions, paiements, factures, tableau de bord, tarifs, exports, aide | Démo G côté gestion | 5 – 6 |
| L6.6 | Portail : page « Inscription », parcours `/compte/inscription`, suivi, factures, QR | Démo G côté portail | 3,5 – 4,5 |
| L6.7 | E2E, recette, documentation, étude (§22) | Démo G sur o2switch | 1,5 – 2 |
| **Total L6** | | | **23 – 29** (+ marge de 1 à 2 j-h → **24 – 31**) |

## 9. Risques et hypothèses non vérifiées

| Risque | Mesure |
|---|---|
| Agrégateur non choisi ou contrat tardif (Q7) | Interface de fournisseur et fournisseur factice ; paiement manuel en repli (étude §14.4) |
| Documentation de l'agrégateur mal comprise (signature, statuts) | Vérification en bac à sable en L6.0 ; ne rien supposer de son API sans l'avoir testée |
| Notification perdue ou rejouée | Réconciliation horaire `sync_payments` ; idempotence par référence |
| Factures non conformes (Q8) | Aucune facture émise sans mentions de facturation ; modèle validé par le commanditaire avant la démo |
| Conservation légale contre droit à l'effacement (RG-18) | Factures exclues de l'anonymisation, durée à préciser (J14) |
| Numérotation avec trous sous concurrence | Compteur verrouillé en transaction, test de concurrence sur MariaDB, contrôle d'intégrité |
| Fuseau et périodes tarifaires | Bascule de période aux dates clés (instants UTC), tests autour de minuit dans le fuseau de l'édition |
| o2switch : appels sortants vers l'agrégateur, `.htaccess` | À vérifier en L6.0 (fiche `docs/L1-verifications-o2switch.md`) |

## 10. Questions au commanditaire

1. Validation de J1 à J16, en particulier :
   - J1 : droits du CO « finances » et « secrétariat » ;
   - J5 : échéances de paiement (72 h en ligne, 30 jours sur bon de commande) ;
   - J8 : facture émise au paiement, pro forma hors série ;
   - J10 : RG-11 comme conflit bloquant à la publication ;
   - J15 : « Mon programme » et notification des inscrits, maintenant ou plus tard.
2. **Q7** : inscription payante ? Montants, catégories, devises, moyens de paiement ;
   **agrégateur** (CinetPay proposé ; un second pour la carte internationale ?) et
   disponibilité d'un compte marchand et d'un bac à sable.
3. **Q8** : entité de facturation (raison sociale, adresse, identifiants fiscaux), TVA
   éventuelle, mentions obligatoires, durée de conservation des factures.
4. Règles d'annulation et de remboursement (dates, pourcentages).
5. Inscriptions de groupe (une institution paie pour plusieurs personnes) : nécessaires pour
   cette édition ?
6. Charge de 24 à 31 j-h, contre 12 à 16 dans l'étude.
