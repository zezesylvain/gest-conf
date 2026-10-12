# Guide — Comité d'organisation

Pour les **membres du comité d'organisation** (rôle « Membre du comité d'organisation »,
`OC_MEMBER`). Chaque membre a une **fonction** (finances, programme, logistique,
communication, relations extérieures, bénévoles, secrétariat) qui ajoute des droits
d'écriture ; une section par fonction ci-dessous. Adresses relatives à
`/gestion/editions/<n°>/` ; conventions dans le [README](README.md).

## 1. Commun à tout le CO

- **Accès** : invitation, double authentification obligatoire, réauthentification pour les
  opérations sensibles (voir [presidence-administration.md](presidence-administration.md),
  § 2). « Rôle actif » filtre le rail ; Ctrl+K cherche un écran ; « ? » ouvre la fiche.
- **Lecture pour tous** : Tableau de bord ; Soumissions (auteurs compris) ; Programme
  (planificateur, sessions, salles, publication) ; Inscriptions ; Paramétrage (dont Tarifs) ;
  Portail ; Rapports (sections de vos droits, chiffres agrégés).
- **Écriture pour tous** :
  - **Organisation › Tâches** : créer (titre, responsable, échéance, priorité, étiquette)
    › « Créer la tâche » ; liste « Déplacer vers » sur chaque carte (pas de glisser-déposer) ;
    la fiche réunit commentaires (« Commenter ») et pièces jointes ; « Archiver ». Rappel
    quotidien par e-mail des tâches en retard ou proches.
  - **Organisation › Activité** : les 50 dernières actions de l'organisation.
  - **Jour J › Accueil (scan)** et **Sessions du jour** : tout le CO peut pointer ;
    **Jour J › Badges** : planches PDF. Voir [benevole-accueil.md](benevole-accueil.md).
- **Aucun accès** aux évaluations (rubrique Évaluation), au journal, aux membres (sauf CO
  « bénévoles »).

## 2. Programme

1. **Programme › Salles** › « Ajouter une salle » : capacité, équipements, accessibilité et
   indications d'accès (publiées). Une salle utilisée se désactive.
2. **Programme › Sessions** › « Ajouter une session » : type, titre, salle, début et fin à
   l'heure de l'édition ; puis rôles de séance (président de séance, discutant, modérateur,
   panéliste : personnes ayant un rôle dans l'édition, sinon à faire inviter) et éléments
   libres (conférence invitée, discours…).
3. **Programme › Planificateur** : un jour à la fois, une colonne par salle ; liste « À
   programmer » (communications confirmées par leurs auteurs). « Placer dans… » (ou
   glisser), flèches pour l'ordre, « Actions… » pour déplacer, changer la durée ou
   « Retirer du programme ». Les horaires se recalculent, tampon compris.
4. **Conflits** signalés après chaque action, « Voir » pour y aller : salle ou personne à
   deux endroits (RG-12), session qui déborde (RG-13), présentateur non inscrit (RG-11, si
   le paramètre est actif).
5. **Paramétrage › Programme** : tampon de 0 à 30 minutes ; inscription des présentateurs
   (RG-11).
6. **Programme › Publication du programme** : vérifier les modifications non publiées, les
   conflits, les communications encore à programmer. **Le président de la conférence
   publie** ; le programme public suit à la mise en ligne du portail.
7. Jour J › Sessions du jour : « Marquer présentée » ; « Corriger : non présentée » avec
   motif (vous et l'administrateur seuls).

## 3. Finances

1. **Paramétrage › Tarifs** : paramètres (devise, moyens de paiement, pays locaux, délais
   de paiement, date limite et parts d'annulation), « Ajouter une catégorie » (justificatif
   éventuel, couleur du badge), grille par période et zone, « Ajouter une option » (quota),
   « Ajouter un code promo ». Un élément utilisé se désactive.
2. **Paramétrage › Facturation** : émetteur, adresse, TVA, coordonnées bancaires, préfixes
   (réauthentification). Sans raison sociale ni adresse, aucune facture ne s'émet.
3. **Inscriptions › Inscriptions** : filtres, « Exporter (CSV) » (réauthentification) ;
   « Saisir une inscription » pour un compte existant. Fiche d'une inscription :
   - « Enregistrer un paiement reçu » (virement ou sur place, montant total) : confirmation
     et facture ;
   - « Accorder la gratuité » (motif) ; « Émettre une facture pro forma » ;
   - « Annuler l'inscription » (motif), puis « Enregistrer un remboursement » une fois fait :
     un avoir est émis.
4. **Inscriptions › Paiements** : rapprochement ; un paiement en ligne n'est valide que sur
   notification vérifiée auprès du prestataire (RG-15).
5. **Inscriptions › Factures et avoirs** : pièces figées, numérotées sans trou (RG-14) ;
   une erreur se corrige par un avoir. **Inscriptions › Finances** : encaissé, impayés,
   remboursements dus ; « Émettre les factures en attente ».
6. **Organisation › Budget** : lignes de dépenses et de recettes par poste, prévu et réalisé
   avec justificatif ; lignes « inscriptions » et « partenariats » calculées ; exports CSV
   ou XLSX (réauthentification).
7. Partenaires en lecture ; **Jour J › Comptoir** (voir [benevole-accueil.md](benevole-accueil.md)).

## 4. Secrétariat

- **Inscriptions** : mêmes actions que les finances dans la liste et la fiche (§ 3,
  point 3). Les écrans Paiements, Factures et avoirs, Finances, Facturation et Budget, et
  l'écriture des tarifs, restent au CO « finances ».
- **Jour J › Comptoir** et **Jour J › Présences** (voir [benevole-accueil.md](benevole-accueil.md)).
- **Attestations et lettres › Modèle des attestations** : mode de signature (image ou
  PAdES), en-tête, certificat `.p12` le cas échéant, textes FR/EN par nature, **signataire
  désigné**, « Aperçu (PDF) ».
- **Attestations et lettres › Attestations** : par nature (participation, communication,
  évaluation si activée), éligibles et émises ; « Émettre », puis « Émettre les
  manquantes » après un pointage tardif ; « Révoquer » (motif). Le serveur revérifie la
  présence (RG-16).
- **Attestations et lettres › Lettres d'invitation** : fiche de la demande (passeport en
  clair, séjour, ambassade, état de l'inscription) › « Émettre la lettre » ou « Refuser »
  (motif transmis) ; « Révoquer ».
- Logistique en lecture ; **Communication › Questionnaires** (§ 6).

## 5. Logistique

- **Logistique › Intervenants invités** : fiche de venue ; la part de l'intervenant (besoins
  techniques, voyages) et la vôtre (hôtel, nuits, prise en charge, **note interne jamais
  montrée** à l'intervenant) ; équipement manquant en salle signalé.
- **Logistique › Restauration** : « Ajouter le repas », convives, marge ; effectifs et
  régimes sans nom ; « Commande au traiteur » (CSV, XLSX, PDF). La « Liste nominative
  (CSV) » des régimes demande votre mot de passe et est journalisée (RG-23).
- **Logistique › Postes des bénévoles** (§ 8) ; **Jour J › Présences**.

## 6. Communication

- **Portail** : Sections (« Ajouter une section », texte en HTML simple, « Aperçu »), Pages
  (« Ajouter une page », « Composer », « Poser à la fin », « Monter », « Descendre »),
  Menus (« Ajouter une entrée »), Documents et images (fichier publié un à un, affiche).
  Le bandeau d'état compte les modifications non publiées : **demandez la mise en ligne à
  l'exploitant**. Page « Aide » : texte proposé dans [aide-portail.md](aide-portail.md).
- **Communication › Annonces** › « Créer et ouvrir l'annonce » : titre et texte FR/EN ;
  canaux (actualités, bandeau, cloche, e-mail) ; destinataires par segment ; aperçu et
  « M'envoyer un essai » ; publication (réauthentification). Le bandeau paraît aussitôt,
  une seule annonce à la fois ; les actualités, à la mise en ligne du portail. Après la
  publication, l'envoi est parti ; « Retirer » annule les e-mails pas encore partis. Envois
  étalés et lien de désabonnement (RG-22).
- **Communication › Questionnaires** › « Créer et ouvrir le questionnaire » : portée
  (conférence ou session), questions, ouverture et clôture ; publication
  (réauthentification). Réponses anonymes, résultats à partir de 5 réponses (RG-21) ;
  questions verrouillées dès la première réponse (« Dupliquer »).
- Partenaires en lecture.

## 7. Relations extérieures

- **Partenaires › Niveaux de partenariat** › « Ajouter le niveau » : noms FR/EN, montant
  indicatif, contreparties, taille du logo.
- **Partenaires › Partenaires** › « Créer et ouvrir la fiche » : partie publique (nom,
  niveau, site, présentations, logo, « Publier sur le portail ») et partie privée (statut,
  contribution convenue et reçue, contact, note interne). Contribution « reçue » : montant
  et date, reportés au budget. Exports avec contacts : réauthentification.
- **Attestations et lettres › Lettres d'invitation** (§ 4).

## 8. Bénévoles

- **Comités › Invitations** : rôle « Bénévole » seulement ; **Comités › Membres** : les
  bénévoles seulement, « Retirer le rôle ».
- **Logistique › Postes des bénévoles** › « Ajouter le poste » (intitulé FR/EN, lieu,
  horaires à l'heure du lieu, nombre, consignes) ; « Affecter », « Retirer ». Un bénévole
  ne tient pas deux postes en même temps ; il est prévenu et voit ses postes dans « Mon
  planning ».
- **Jour J › Présences**.

## Fiches d'aide liées

- `first-steps` — Premiers pas dans la gestion ; `security` — Double authentification
  et confirmation d'identité ; `roles` — Rôles et droits ; `dashboard` — Tableau de bord
- `tasks` — Tâches ; `activity` — Fil d'activité ; `budget` — Budget ; `reports` — Rapports
- `submissions` — Soumissions ; `settings-lists` — Thématiques et types de communication
- `program-rooms` — Salles ; `program-sessions` — Sessions ; `program-planner` —
  Planificateur du programme ; `program-publication` — Publication du programme ;
  `settings-program` — Paramétrage du programme
- `settings-pricing` — Tarifs ; `settings-billing` — Mentions de facturation ;
  `registrations` — Inscriptions ; `payments` — Paiements ; `billing-documents` — Factures
  et avoirs ; `finance-dashboard` — Finances
- `certificates` — Attestations ; `certificate-settings` — Modèle des attestations ;
  `letters` — Lettres d'invitation
- `speakers` — Intervenants invités ; `catering` — Restauration ; `volunteer-shifts` —
  Postes des bénévoles
- `portal-sections` — Sections du portail ; `portal-pages` — Pages et composeur ;
  `portal-menus` — Menus du portail ; `portal-files` — Documents et images ;
  `portal-publish` — Publier le portail
- `announcements` — Annonces ; `surveys` — Questionnaires
- `sponsors` — Partenaires ; `sponsor-levels` — Niveaux de partenariat
- `members` — Membres ; `invitations` — Invitations
- `reception` — Accueil (scan des badges) ; `day-sessions` — Sessions du jour ;
  `attendance` — Présences ; `badges` — Badges ; `counter` — Comptoir
