# Guide — Présidence et administration

Pour le **président de la conférence** (rôle « Président de la conférence », `CHAIR`) et les
**administrateurs de l'édition** (« Administrateur de l'édition », `ADMIN`). Adresses de la
gestion relatives à `/gestion/editions/<n°>/` ; conventions dans le [README](README.md).

## 1. Ce qui se fait hors de l'application

- **Créer une édition** et désigner son premier administrateur : l'exploitant, par commande
  (`create_edition --admin-email …`, qui envoie une invitation). Il n'existe aucun rôle
  global : chaque droit est attaché à une édition (décision D1).
- **Désigner l'édition affichée par le portail** : l'exploitant (`set_current_edition`).
- **Mettre le portail en ligne** après une modification : l'exploitant
  (`deploy/deploy.sh --portal-only`), à votre demande.
- **Réinitialiser la double authentification** d'une personne sans code de secours, rouvrir
  une édition archivée, retirer le dernier administrateur : l'exploitant, par commande
  journalisée, après vérification.

## 2. Accès et sécurité

1. **Accepter l'invitation** : ouvrir le lien de l'e-mail (valable 14 jours), se connecter
   ou créer son compte avec l'adresse invitée, vérifiée (RG-20), puis « Accepter
   l'invitation ».
2. **Activer la double authentification**, facultative mais vivement recommandée pour la
   gestion : portail, `/compte/securite` › « Activer la double authentification » ; scanner
   le QR code avec une application (FreeOTP, Aegis, Google Authenticator…), saisir le code,
   noter les **codes de secours**. Si l'exploitant l'impose (`GESTCONF_MFA_ENFORCED`), la
   gestion vous ramène sur cette page tant qu'elle n'est pas activée.
3. **Se connecter** : `/compte/connexion`, puis, si elle est activée, le code à 6 chiffres ;
   la gestion est sous
   `/gestion/`. Une session dure 12 heures au plus.
4. **Se repérer** : sélecteur « Édition » en haut ; « Rôle actif » réduit le rail aux
   rubriques d'un rôle (filtre d'affichage, pas un droit) ; Ctrl+K pour chercher un écran ;
   « ? » pour la fiche de l'écran.
5. **Réauthentification** : publier ou archiver l'édition, changer la confidentialité,
   retirer un rôle, inviter un administrateur, un président ou un signataire, publier les
   résultats ou le programme, exporter, etc. redemandent votre mot de passe (ou un code)
   au-delà de 5 minutes.

## 3. Paramétrer l'édition

Modifiable par l'administrateur et le président ; les autres rôles consultent.

- **Titres FR/EN, thème, dates, lieu, fuseau, langues des soumissions** : Paramétrage ›
  Informations générales (`parametrage/general`). Le code de l'édition (préfixe des
  références) est gelé à la première soumission (RG-19) ; seul un administrateur le change,
  avec un motif.
- **Thématiques et types de communication** : Paramétrage › Thématiques ; Paramétrage ›
  Types de communication › « Ajouter une thématique », « Ajouter un type ». Un élément déjà
  utilisé se désactive, il ne se supprime pas.
- **Échéances** : Paramétrage › Calendrier › « Ajouter une date clé », à l'heure de
  l'édition ; « Visible sur le portail » ; l'ordre des codes réservés est contrôlé.
- **Double aveugle, relecteurs par soumission, charge, divergence, note finale** :
  Paramétrage › Confidentialité (réauthentification) ; le double aveugle est gelé à la
  première soumission (RG-19).
- **Grilles d'évaluation** : Paramétrage › Grilles d'évaluation (RG-05), voir
  [comite-scientifique.md](comite-scientifique.md).
- **Tampon entre créneaux, inscription des présentateurs (RG-11)** : Paramétrage ›
  Programme ; administrateur et CO « programme », le président consulte.
- **Catégories, tarifs, options, codes promo** : Paramétrage › Tarifs ; administrateur et
  CO « finances », le président consulte.
- **Mentions de facturation** : Paramétrage › Facturation (réauthentification) ;
  administrateur et CO « finances », le président consulte.

## 4. Publier et archiver l'édition

- **Pilotage › Tableau de bord** : la liste « Paramétrage à compléter avant publication »
  (titres FR et EN, dates, une thématique et un type actifs, ouverture et clôture de
  l'appel), puis « Publier l'édition ». Une édition publiée ne redevient pas brouillon.
- Publier l'édition ne met pas le portail en ligne : le bandeau des écrans « Portail »
  compte les modifications non publiées ; demandez la mise en ligne à l'exploitant.
- « Archiver l'édition » : **administrateur seul**, après la fin de la conférence ; l'édition
  passe en lecture seule.

## 5. Membres et invitations

- **Comités › Invitations** › « Inviter des membres » : jusqu'à 50 adresses, le rôle (et la
  fonction au comité d'organisation : finances, programme, logistique, communication,
  relations extérieures, bénévoles, secrétariat), la langue et un message facultatif ;
  « Envoyer les invitations ». Suivi par statut ; « Relancer » (trois envois au plus),
  « Annuler l'invitation ».
- **Qui invite qui** : l'administrateur, tous les rôles ; le président, tous sauf
  administrateur et président. Le président du CS invite les relecteurs, le CO « bénévoles »
  les bénévoles.
- Intervenants invités et présidents de séance : rôles « Intervenant » et « Président de
  session », à inviter avant de les placer au programme.
- **Signataire** des attestations et lettres : rôle « Signataire » (réauthentification) ;
  lui seul renseigne « Ma signature ».
- **Comités › Membres** : « Retirer le rôle » (motif journalisé, réauthentification, e-mail
  à la personne) ; « Afficher les rôles retirés ». Le dernier administrateur ne se retire
  pas ici.

## 6. Portail

Administrateur, président et CO « communication » rédigent ; les autres consultent.
Portail › Sections (blocs réutilisables), Pages (« Composer », « Poser à la fin »), Menus,
Documents et images (publiés un à un, affiche). Détail dans
[comite-organisation.md](comite-organisation.md), section « Communication ».

## 7. Évaluation, programme, inscriptions, jour J

- **Évaluation** : le président a les mêmes écrans que le président du CS (Pilotage de
  l'évaluation, Classement et décisions) et peut décider et **publier les résultats**
  (RG-09) ; il n'évalue pas. L'administrateur pilote (recevabilité, affectations) et lit le
  classement, mais ne décide ni ne publie. Voir [comite-scientifique.md](comite-scientifique.md).
- **Soumissions** : liste, détail (auteurs compris), « Exporter (CSV) », dérogations après la
  clôture (RG-02).
- **Programme** : l'administrateur l'écrit comme le CO « programme » ; **le président seul
  le publie** : Programme › Publication du programme › « Publier le programme »
  (réauthentification), refusé tant qu'il reste un conflit ou si rien n'a changé. Les
  intervenants concernés reçoivent un e-mail ; le portail suit à sa mise en ligne.
- **Inscriptions et finances** : le président consulte (Inscriptions, Paiements, Factures et
  avoirs, Finances) ; l'administrateur gère aussi (paiement reçu, gratuité, annulation,
  remboursement), comme le CO « finances ».
- **Jour J** : l'administrateur a tous les écrans (Accueil (scan), Présences, Comptoir,
  Badges) ; le président ne voit que les badges. Voir [benevole-accueil.md](benevole-accueil.md).
- **Attestations et lettres** : président et administrateur émettent et révoquent les
  attestations et règlent leur modèle ; les lettres d'invitation sont instruites par
  l'administrateur et le CO (secrétariat, relations extérieures).
- **Organisation et communication** : tâches et activité, annonces, questionnaires pour les
  deux ; budget, partenaires et logistique en lecture pour le président.

## 8. Contrôle et rapports

- **Contrôle › Journal** (administrateur et président) : qui a fait quoi, avant et après ;
  filtre par action exacte (`edition.updated`) ou par préfixe (`role.`), par objet, par
  période. Inaltérable ; ni adresse IP ni adresse e-mail en clair.
- **Rapports** : sections selon vos droits, chiffres agrégés sans nom ; exports CSV, XLSX
  ou PDF, inscrits au journal.

## 9. Ce que ces rôles ne font pas

- **Administrateur** : n'évalue pas, ne décide pas, ne publie ni les résultats ni le
  programme, ne signe pas à la place du signataire, ne préside pas de séance.
- **Président** : n'archive pas, n'écrit pas le programme, ne modifie ni les tarifs ni les
  mentions de facturation, n'enregistre pas de paiement, ne pointe pas, n'instruit pas les
  lettres d'invitation, ne signe pas.

## Fiches d'aide liées

- `first-steps` — Premiers pas dans la gestion
- `security` — Double authentification et confirmation d'identité
- `roles` — Rôles et droits
- `dashboard` — Tableau de bord
- `settings-general` — Informations générales
- `settings-lists` — Thématiques et types de communication
- `settings-calendar` — Calendrier
- `settings-confidentiality` — Confidentialité et paramètres de l'évaluation
- `settings-program` — Paramétrage du programme
- `settings-pricing` — Tarifs
- `settings-billing` — Mentions de facturation
- `grids` — Grilles d'évaluation
- `members` — Membres
- `invitations` — Invitations
- `portal-publish` — Publier le portail
- `submissions` — Soumissions
- `ranking` — Classement et décisions
- `program-publication` — Publication du programme
- `certificates` — Attestations
- `certificate-settings` — Modèle des attestations
- `audit` — Journal
- `reports` — Rapports
