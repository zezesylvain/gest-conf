# Lot L9 — Cahier de recette (démos A à I)

> Décision S10 du plan [`L9-recette-plan.md`](L9-recette-plan.md). Les démos A à I des bilans
> [`L1-socle.md`](L1-socle.md) à [`L8-logistique.md`](L8-logistique.md) et de leurs plans,
> découpées en scénarios numérotés, à jouer **sur l'hébergement o2switch**, sur l'édition de
> démonstration, **avant toute donnée réelle** (étape L9.8, runbook
> `docs/L9-runbook-o2switch.md`).
>
> Écrans, menus et adresses vérifiés dans le code au 12 octobre 2026 : table de navigation de
> la gestion (`web/projects/gestion/src/app/core/navigation.ts`), routes de la gestion et du
> portail (`*.routes.ts`), traductions françaises, services du serveur. Ce qui ne se vérifie
> pas depuis le dépôt est marqué **à confirmer**.

## 1. Mode d'emploi

### 1.1 Principes

- La recette fonctionnelle est faite par le **commanditaire** (ou les testeurs qu'il désigne),
  sur la plateforme installée chez o2switch, sur l'édition de démonstration `DEMO`, avant toute
  donnée réelle (D18 ; plan L9, §2.1, hypothèse 4). Un **opérateur** (accès SSH) lance les
  commandes indiquées ; le prestataire prépare, assiste et corrige (S10, S15).
- Les démos se jouent **dans l'ordre** A → I : chacune réutilise les données des précédentes
  (§1.6). Dans une démo, les scénarios se jouent dans l'ordre de leur numéro.
- Chaque scénario se coche **OK** (tout le résultat attendu est obtenu) ou **KO** (tout écart).
  **Une anomalie = une ligne** du tableau du §12, qui cite le numéro du scénario.
- Gravité d'une anomalie :
  - **bloquante** : un parcours P1 est impossible, une donnée est perdue ou exposée, un droit
    ou une règle de gestion est violé (double aveugle, droits, paiement, numérotation des
    pièces). **L'ouverture** (appel, inscriptions) **est suspendue** jusqu'au correctif et au
    rejeu du scénario ;
  - **majeure** : résultat faux, ou parcours possible seulement par un détour, sans perte ni
    exposition de données. Corrigée avant l'ouverture, ou acceptée par écrit par le
    commanditaire ;
  - **mineure** : libellé, présentation, confort. Correctif possible dans un lot ultérieur.
- Un correctif est livré avec son test (S15), déployé, puis le scénario est **rejoué** : la case
  passe à OK avec la date, et la ligne d'anomalie reçoit le commit.
- Ne saisir **aucune donnée réelle** : pas d'autre personne réelle que les testeurs, pas de vrai
  numéro de passeport, pas de vraie carte bancaire. N'inviter que les adresses des testeurs.
- **Après la recette**, la base est **restaurée** à partir de la sauvegarde prise juste avant
  `seed_demo`, dans une base neuve (`deploy/restore.sh`, runbook), ou réinstallée, **avant toute
  donnée réelle**. Comptes fictifs, comptes réels des testeurs, soumissions, pièces de
  facturation et journal de la recette disparaissent. Il n'existe pas de commande de purge :
  les pièces comptables et le journal sont en ajout seul (RG-14, RG-17).

### 1.2 Préparation (opérateur)

1. Runbook déroulé jusqu'à l'étape de recette : déploiement et tests de fumée, lignes de cron
   actives (`deploy/cron.sh`), sauvegarde, copie rapatriée et restauration testées.
2. `python manage.py backup_db` : sauvegarde d'avant la démonstration, **à conserver**.
3. `python manage.py seed_demo --confirm-fictitious` (§1.3).
4. Remettre au testeur, **par un canal sûr**, le mot de passe commun et le secret TOTP commun
   affichés une seule fois. Ne jamais les écrire dans le dépôt, dans ce cahier ni dans un ticket.
5. Paiement en ligne (démo G), seulement si un fournisseur est configuré : CinetPay en bac à
   sable (**à confirmer** : compte marchand, Q7 ; appels sortants, V29), ou fournisseur factice
   déclaré pour la recette (`GESTCONF_PAYMENT_PROVIDER=fake` et
   `GESTCONF_ALLOW_FAKE_PAYMENTS=true`, **à retirer avant l'ouverture**). `seed_demo` ne propose
   le paiement en ligne que si le fournisseur était configuré à son lancement ; sinon, le
   CO « finances » coche le moyen dans « Paramétrage › Tarifs ». Sans fournisseur, les étapes de
   paiement en ligne sont notées « sans objet ».

### 1.3 Données de départ (`seed_demo`)

`python manage.py seed_demo --confirm-fictitious` crée, dans la conférence fictive
`gestconf-fictif`, l'édition `DEMO` (« Édition de démonstration »), publiée et désignée comme
édition publique courante :

- appel à communications ouvert pendant 30 jours ; date de fin des évaluations ; date de la
  version définitive ; inscriptions ouvertes (virement et sur place ; paiement en ligne
  seulement si un fournisseur est configuré) ;
- deux thématiques, un type de communication (PDF facultatif), la grille d'évaluation par
  défaut, une catégorie d'inscription « Chercheur » avec ses tarifs, les mentions de
  facturation, deux salles ;
- un compte par rôle (§1.4), adresses `<nom>@fictif.invalid` : domaine réservé, **aucun e-mail
  ne leur parvient** ; un mot de passe commun et un secret TOTP commun (tous les comptes à rôle
  de gestion, 2FA obligatoire), affichés **une seule fois** ;
- refus si la base contient un compte, une soumission ou une inscription réels, ou si l'édition
  `DEMO` existe déjà ; commande journalisée (`qa.demo_seeded`).

Valeurs lues dans `apps/qa/demo.py` (J = jour du lancement) : fuseau `Africa/Abidjan` ;
conférence du J+90 au J+92 (**J1** et **J2** désignent ci-dessous ses deux premiers jours) ;
clôture de l'appel à J+30, fin des évaluations à J+50, version définitive à J+70, fin du tarif
préférentiel à J+20, clôture des inscriptions à J+85 ; thématiques « Intelligence
artificielle » et « Santé publique » ; type « Communication orale » (PDF facultatif, 10 Mo) ;
« Grille de démonstration » (25/30/15/15/15, notes de 0 à 5) ; « Chercheur » : préférentiel
40 000 (local) et 100 000 (international), normal 50 000 et 120 000, en XOF ; pays local : CI ;
salles « Amphithéâtre A » et « Salle B ».

### 1.4 Comptes fictifs

| Compte (`@fictif.invalid`) | Rôle dans `DEMO` | 2FA | Nom affiché, institution |
|---|---|---|---|
| `admin` | administrateur de l'édition (ADMIN) | oui | Aya Konan, Université fictive |
| `presidence` | président de la conférence (CHAIR) | oui | Yao Kouassi, Université fictive |
| `president.cs` | président du comité scientifique (SC_CHAIR) | oui | Koffi Yao, Institut fictif |
| `relecteur1` | membre du CS (SC_MEMBER) | oui | Aminata Diallo, Centre fictif R1 |
| `relecteur2` | membre du CS (SC_MEMBER) | oui | Serge Ekra, Centre fictif R2 |
| `relecteur3` | membre du CS (SC_MEMBER) | oui | Claire Martin, Centre fictif R3 |
| `co.programme`, `co.finances`, `co.secretariat`, `co.logistique`, `co.communication`, `co.relations`, `co.benevoles` | membre du CO (OC_MEMBER), fonction : programme, finances, secrétariat, logistique, communication, relations extérieures, bénévoles | oui | Université fictive |
| `benevole` | bénévole (VOLUNTEER) | oui | Ali Touré |
| `signataire` | signataire (SIGNATORY) | oui | Brou Assi |
| `intervenant` | intervenant invité (SPEAKER) | non | Ama Owusu, Université fictive du Ghana |
| `auteur1`, `auteur2` | aucun | non | Awa Koné (A), Moussa Traoré (B) |
| `participant1`, `participant2` | aucun | non | Ousmane Ndiaye (C), Léa Dubois (D) |

### 1.5 Adresses réelles des testeurs

Les comptes fictifs ne reçoivent **aucun e-mail**. Tout scénario qui exige de **lire** un
e-mail (création de compte et vérification, invitation, accusé de réception, décision,
programme, facture, attestation, annonce, questionnaire) se joue avec une **adresse réelle**
dont le testeur dispose, en créant un compte depuis le portail :

- **R1** : compte créé en A ; autrice et participante de la recette (D à I) ;
- **R2** : invitée en B comme présidente du CS ; présidente de séance (F, H) ;
- **R3** : invitée en B comme relectrice (B, E) ;
- **R4** (facultative) : compte jetable du scénario A8.

Des alias d'une même boîte (`nom+r2@…`) conviennent si la messagerie les distingue (à vérifier
avant de commencer). Pour un e-mail destiné à un compte fictif, l'opérateur vérifie qu'il a
bien été produit : `python manage.py outbox --status cancelled` liste le gabarit, le
destinataire masqué et le motif « domaine réservé .invalid ».

### 1.6 Fil des données

| Compte | Usage dans la recette |
|---|---|
| R1 | A (compte) ; D (soumission S1) ; E (acceptée) ; F (présentatrice) ; G (inscription « Étudiant ») ; H (pointée, attestations) ; I (annonce, désabonnement, questionnaire) |
| R2 | B (présidente du CS invitée) ; E (e-mail de divergence) ; F, H (présidente de séance) |
| R3 | B (relectrice invitée) ; E (relectrice de S1) |
| `auteur1` | D (S2, S5) ; E (S2 acceptée, S5 non recevable) ; F (présentateur) ; G (inscription, RG-11) ; H, I |
| `auteur2` | D (S3, S4, S6 retirée) ; E (S3 acceptée sous réserve, S4 rejetée) ; F ; G (RG-11) ; H, I |
| `participant1` | G (virement, pro forma) ; H (pointé, lettre d'invitation) ; I (régime, questionnaire) |
| `participant2` | G (payée puis annulée : avoir ; badge gardé) ; H (badge annulé) |
| `intervenant` | F (conférence invitée) ; G (inscription gratuite) ; H (pointé) ; I (« Ma venue », questionnaire) |

Soumissions de D : **S1** (R1), **S2** (`auteur1`), **S3** et **S4** (`auteur2`), **S5**
(`auteur1`), **S6** (`auteur2`, retirée). Envoyées dans cet ordre, elles reçoivent les
références `DEMO-0001` à `DEMO-0006` (la référence est attribuée à l'envoi, F4).

### 1.7 Conventions

- `<domaine>` : domaine de production. `<id>` : identifiant numérique de l'édition `DEMO`, lu
  dans l'adresse de la gestion (`https://<domaine>/gestion/editions/<id>/…`).
- « Rubrique › Écran » désigne le rail de la gestion (par exemple « Évaluation › Pilotage de
  l'évaluation »). Si un écran manque, choisir « Tous mes rôles » dans « Rôle actif ».
- Connexion : `https://<domaine>/compte/connexion`, puis, pour un rôle de gestion, le code de
  l'application TOTP (« Double authentification »), puis « Mon compte › Accéder à l'espace de
  gestion » (`/gestion/`). Le secret TOTP commun s'ajoute **une fois** dans l'application
  d'authentification (saisie manuelle de la clé). Un code déjà utilisé pour le même compte est
  refusé : attendre le suivant.
- Une fenêtre privée (ou un profil de navigateur) par compte ; se déconnecter entre deux
  comptes.
- « Réauthentification » : fenêtre « Confirmez votre identité » (mot de passe ou code), exigée
  par les opérations sensibles.
- Chaque page du portail se vérifie aussi sur téléphone (375 px, sans défilement horizontal).

### 1.8 Actions de l'opérateur pendant la recette

| Action | Commande (environnement de l'application, voir le runbook) | Démos |
|---|---|---|
| Republier le portail pré-rendu | `deploy/deploy.sh --portal-only`, depuis le poste de l'opérateur (`DEPLOY_BASE_URL`) | C, F, G, I |
| Lancer une commande du cron sans attendre | `$HOME/gestconf-app/deploy/cron.sh <commande>` (`close_call`, `remind_drafts`, `remind_reviewers`, `run_jobs`) | D, E, H, I |
| Vérifier les e-mails produits | `python manage.py outbox [--status cancelled]` | toutes |
| Lire le journal | `python manage.py audit_query --email <adresse> --action <préfixe> --since AAAA-MM-JJ` | A, B |

## 2. Démo A — Compte (L1)

Source : plan L1, étape L1.4 (« Démo A ») ; bilan L1, §2. Préalable : adresse R1 sans compte ;
navigateur réglé en anglais pour A1.

| N° | Préalable | Étapes | Résultat attendu | Règle | OK/KO |
|---|---|---|---|---|---|
| A1 | R1 sans compte ; navigateur en anglais | 1. Ouvrir `https://<domaine>/`, puis la connexion et « Créer un compte » (`/compte/inscription`).<br>2. Saisir R1 et un mot de passe courant, puis un mot de passe de 12 caractères au moins.<br>3. Ouvrir le lien de l'e-mail reçu. | `/` redirige vers `/fr/` ; mot de passe courant refusé ; e-mail de vérification reçu **en anglais** ; adresse vérifiée | D4, D11 | ☐ OK ☐ KO |
| A2 | A1 | 1. Se connecter.<br>2. Lire la notice, « J'ai pris connaissance de la notice ». | « Mon compte » ; la notice n'est plus demandée ; le choix figure dans « Confidentialité › Historique de vos choix » | D15 | ☐ OK ☐ KO |
| A3 | A2 | 1. « Compléter mon profil » : prénom, nom, institution, pays.<br>2. ORCID mal formé, puis bien formé (0000-0000-0000-000X).<br>3. « Langue » : français ; se déconnecter, se reconnecter. | ORCID mal formé refusé avec un message ; profil enregistré ; langue conservée à la reconnexion | F6 | ☐ OK ☐ KO |
| A4 | A3 | 1. Se déconnecter ; « Mot de passe oublié ? » avec une adresse sans compte, puis avec R1.<br>2. Ouvrir le lien reçu, « Enregistrer le mot de passe ».<br>3. Se connecter avec l'ancien, puis le nouveau mot de passe. | Même réponse dans les deux cas (pas d'énumération) ; e-mail reçu pour R1 seulement, dans les minutes qui suivent (`run_jobs`) ; ancien mot de passe refusé | D4 | ☐ OK ☐ KO |
| A5 | A4 | « Sécurité » : « Changer le mot de passe » (mot de passe actuel faux, puis juste) ; facultatif : « Ajouter l'adresse » (alias de R1). | Refus avec un mot de passe actuel faux, puis « Mot de passe modifié. » ; ajout d'adresse soumis à réauthentification, lien de vérification envoyé | D12 | ☐ OK ☐ KO |
| A6 | A3 | « Mes données » › « Télécharger (JSON) ». | Fichier JSON : compte, profil, adresses, consentements, e-mails reçus ; aucun mot de passe ni secret | RG-18, D15 | ☐ OK ☐ KO |
| A7 | A1 à A6 ; opérateur | `python manage.py audit_query --email <R1> --since <date du jour>`. | Inscription, connexions, réinitialisation, profil, export apparaissent, datés et attribués | RG-17, D1 | ☐ OK ☐ KO |
| A8 | Facultatif, en fin de recette ; R4 avec un compte vérifié, sans rôle ni soumission | « Mes données », « Anonymiser mon compte » : saisir l'adresse, cocher « Je comprends… », « Anonymiser définitivement mon compte » (réauthentification). | Compte anonymisé, session fermée, connexion impossible avec R4 | RG-18, D15 | ☐ OK ☐ KO |

## 3. Démo B — Double authentification, paramétrage, invitations (L1)

Source : plan L1, critère de fin global et étape L1.7 (« Démo B ») ; bilan L1, §2 et §3. Dans
l'édition de démonstration, l'édition est déjà créée et publiée par `seed_demo` : la publication
elle-même n'est pas rejouable (une édition publiée ne revient pas en brouillon). Préalable :
`admin`, `relecteur1` ; adresses R2 et R3 sans compte.

| N° | Préalable | Étapes | Résultat attendu | Règle | OK/KO |
|---|---|---|---|---|---|
| B1 | `admin` | 1. Se connecter ; saisir un code TOTP faux, puis le bon.<br>2. Ouvrir la gestion. | « Code incorrect. », puis gestion ouverte sur « Pilotage › Tableau de bord » de `DEMO` ; « Double authentification : Activée sur votre compte. » | D2, D3 | ☐ OK ☐ KO |
| B2 | B1 | 1. « Paramétrage › Informations générales » : thème FR et EN, lieu, ville ; « Enregistrer ».<br>2. « Paramétrage › Calendrier » : lire l'heure de l'édition et « Votre heure ».<br>3. Ouvrir `https://<domaine>/api/v1/public/editions/current`. | « Modifications enregistrées. » ; heures saisies et affichées dans le fuseau de l'édition ; l'API publique renvoie `DEMO`, publiée, avec les textes FR et EN modifiés | D13, D14 | ☐ OK ☐ KO |
| B3 | B1 ; R2 sans compte | 1. « Comités › Invitations » : inviter R2, rôle « président du comité scientifique », langue, message.<br>2. R2 : ouvrir le lien de l'e-mail, créer un compte, vérifier l'adresse, rouvrir le lien, « Accepter l'invitation ». | Invitation « En attente », puis acceptée ; « Bienvenue ! Vous avez maintenant le rôle … » | RG-20, D6 | ☐ OK ☐ KO |
| B4 | B3 | 1. R2 : « Accéder à l'espace de gestion ».<br>2. « Sécurité » : « Activer la double authentification », scanner le QR, saisir le code, noter les codes de secours.<br>3. Rouvrir la gestion. | Avant : « Activez la double authentification pour accéder à l'espace de gestion. » ; après : tableau de bord, paramétrage en lecture seule | D3, D8 | ☐ OK ☐ KO |
| B5 | B4 ; R3 sans compte ; R1 | 1. R2 : « Comités › Invitations », inviter R3 (« membre du comité scientifique »).<br>2. Ouvrir le lien d'abord connecté avec R1.<br>3. R3 : créer son compte depuis le lien, accepter, activer la 2FA. | R2 ne peut inviter que des membres du CS et « Membres » ne montre que le CS ; avec R1 : « Votre compte ne contrôle pas l'adresse invitée… » ; R3 arrive sur « Évaluation › Mes évaluations » (vide) | RG-20, H1, H2 | ☐ OK ☐ KO |
| B6 | B5 ; `relecteur1` | R3 (puis `relecteur1`) : saisir `/gestion/editions/<id>/parametrage/general` ; facultatif : outils de développement, onglet Réseau. | Aucun écran de paramétrage dans le rail ; page « Accès refusé » ; l'API répond 403 | D8, règle n° 2 | ☐ OK ☐ KO |
| B7 | B1 à B6 | `admin` : « Contrôle › Journal », filtrer `invitation.`, `role.`, puis `edition.updated`. | Chaque étape (invitation créée, acceptée, rôle attribué, édition modifiée) avec acteur, date, avant et après ; adresses masquées | RG-17 | ☐ OK ☐ KO |

## 4. Démo C — Portail public (L2)

Source : plan L2, « Démo C » ; bilan L2, §2 et §6. Le portail est **pré-rendu** : une
modification n'y paraît qu'après republication par l'opérateur (E1, E9). Préalable :
`presidence` (ou `co.communication`) ; deux modèles de document PDF ; opérateur disponible.

| N° | Préalable | Étapes | Résultat attendu | Règle | OK/KO |
|---|---|---|---|---|---|
| C1 | `presidence` | Ouvrir « Portail › Sections ». | Bandeau d'état : « N modification(s) non publiée(s) sur le portail » ou « Le portail n'a encore jamais été mis en ligne. » | E1 | ☐ OK ☐ KO |
| C2 | C1 | 1. « Ajouter une section », type « Texte riche », titres FR et EN ; dans le texte, coller `<script>alert(1)</script><b>gras</b>` ; « Aperçu » ; enregistrer.<br>2. « Portail › Pages », « Accueil » › « Composer » : poser la section, la monter, la descendre. | Aperçu sans la balise `<script>`, gras conservé ; section posée ; « Ordre enregistré. » | E3 | ☐ OK ☐ KO |
| C3 | C2 | 1. « Portail › Pages » : « Ajouter une page » « Informations pratiques » (adresse `informations-pratiques`), « Créer et composer », poser une section.<br>2. « Portail › Menus » : « Ajouter une entrée » au menu d'en-tête, « Vers une page du portail ». | Page personnalisée et entrée de menu créées ; le compteur du bandeau augmente | E1 | ☐ OK ☐ KO |
| C4 | Deux PDF ; un fichier non PDF renommé en `.pdf` | « Portail › Documents et images » : « Ajouter un fichier », nature « Document », pour chaque fichier ; puis « Modifier », cocher « Publiée », enregistrer. | Faux PDF refusé (type vérifié par le contenu) ; « Fichier ajouté (non publié). », puis deux documents publiés | E4 | ☐ OK ☐ KO |
| C5 | C2 à C4 ; opérateur | Opérateur : `deploy/deploy.sh --portal-only` ; recharger « Portail › Sections ». | « Le portail est à jour. » ; « Dernière mise en ligne : … » | E9 | ☐ OK ☐ KO |
| C6 | C5 ; fenêtre privée | 1. `/fr/` : accueil, menu « Informations pratiques », « Appel à communications » (« Modèles et documents »), « Dates importantes », « Thématiques ».<br>2. Mêmes pages sous `/en/`.<br>3. Télécharger un modèle.<br>4. Refaire sur téléphone. | Contenus de C2 à C4 en FR et en EN (texte anglais vide : repli sur le français) ; dates dans le fuseau de l'édition, compte à rebours ; modèle téléchargé en pièce jointe ; 375 px sans débordement | E2, E8 | ☐ OK ☐ KO |
| C7 | C5 ; `presidence` | 1. Page « Comités » du portail.<br>2. `presidence` : « Confidentialité », « Apparaître dans l'annuaire » (facultatif : photo dans « Profil » et « Publier ma photo »).<br>3. Republication (C5) ; recharger « Comités ». | Avant : aucun nom, seulement « N membres » ; après : Yao Kouassi nommé (photo si consentie) ; les autres membres comptés, pas nommés ; aucune adresse | E5, E12 | ☐ OK ☐ KO |
| C8 | C5 | 1. `https://<domaine>/sitemap.xml` et `/robots.txt`.<br>2. Coller l'adresse d'une page dans l'outil d'aperçu de partage d'un réseau social. | Plan du site avec les pages FR et EN et la page personnalisée ; `robots.txt` servi ; aperçu Open Graph (titre, description) **à confirmer** : vérifiable en production seulement | E7 | ☐ OK ☐ KO |
| C9 | Une session de gestion | 1. `Ctrl+K` (`⌘K`), taper « affiche ».<br>2. Ouvrir l'écran trouvé, puis « ? » (« Aide sur cet écran »).<br>3. « Aide › Guide ». | « Documents et images » proposé ; fiche d'aide de l'écran ; guide `/gestion/aide` complet et imprimable | E13, E14 | ☐ OK ☐ KO |
| C10 | `co.secretariat` | « Portail › Sections » : tenter une modification. | « Lecture seule : vos rôles ne permettent pas de modifier le portail. » ; écriture refusée par le serveur | E11, règle n° 2 | ☐ OK ☐ KO |

## 5. Démo D — Soumission (L3)

Source : plan L3, « Démo D » ; bilan L3, §2. Préalable : R1 (profil complet, A3), `auteur1`,
`auteur2`, `admin`, `presidence`, `president.cs`, `co.secretariat` ; un PDF dont les propriétés
portent un nom d'auteur et un titre ; appel ouvert. **Calendrier de D9 à D11** : `close_call`
passe à la minute 11 de chaque heure dans l'exemple de `deploy/cron.sh` (à vérifier dans la
crontab réelle) ; régler la clôture juste après un passage, pour jouer D10 (dérogation) avant
le passage suivant, qui ferait passer les soumissions en recevabilité.

| N° | Préalable | Étapes | Résultat attendu | Règle | OK/KO |
|---|---|---|---|---|---|
| D1 | R1 | 1. « Mes soumissions » (`/compte/soumissions`), « Nouvelle soumission (DEMO) ».<br>2. « Informations » : titre, résumé, mots-clés, thématique, type « Communication orale », langue.<br>3. Fermer l'onglet, revenir. | « Enregistré à … » ; le brouillon (S1) est retrouvé avec ses données | F3, F17 | ☐ OK ☐ KO |
| D2 | D1 | « Auteurs » : ajouter Serge Ekra (`relecteur2@fictif.invalid`, Centre fictif R2) et un co-auteur fictif d'institution « Centre fictif R3 » (`coauteur@fictif.invalid`) ; R1 correspondante et présentatrice ; « Enregistrer les auteurs ». | « Auteurs enregistrés. » dans l'ordre voulu ; information des co-auteurs produite (`outbox`). Ces co-auteurs préparent les conflits de E3 | F5, F13 | ☐ OK ☐ KO |
| D3 | D2 ; PDF à métadonnées ; fichier non PDF | « Fichier » : déposer le fichier non PDF, puis le PDF ; retélécharger le PDF et lire ses propriétés. | Faux PDF refusé ; « version 1, N page(s) », « métadonnées supprimées » ; propriétés sans auteur ni titre | F2, RG-04, règle n° 8 | ☐ OK ☐ KO |
| D4 | D3 | 1. « Récapitulatif » avant de cocher les déclarations.<br>2. « Déclarations » : tout cocher ; « Récapitulatif » : « Soumettre ». | D'abord « Avant de soumettre, complétez : » et la liste des manques ; puis référence `DEMO-0001`, accusé de réception par e-mail à R1, notification dans la cloche | RG-01, F4, F13 | ☐ OK ☐ KO |
| D5 | `auteur1`, `auteur2` | 1. Soumettre dans cet ordre : S2 (`auteur1`), S3 et S4 (`auteur2`), S5 (`auteur1`), chacun présentateur.<br>2. `auteur1` : nouveau brouillon portant le titre de S2 ; « Récapitulatif » ; « Supprimer le brouillon ». | `DEMO-0002` à `DEMO-0005`, sans trou ; « doublon possible » signalé, non bloquant ; brouillon supprimé | F4, F15 | ☐ OK ☐ KO |
| D6 | `auteur2` | Soumettre S6, puis « Retirer la soumission », motif, « Retirer définitivement ». | `DEMO-0006` « Retirée » ; e-mail de retrait produit (`outbox`) ; S6 reste listée dans la gestion | F13, RG-17 | ☐ OK ☐ KO |
| D7 | D4 ; appel ouvert | R1 modifie le titre de S1. | « Historique » : « 1 version(s) enregistrée(s) après la soumission » ; état « Soumise » | F3 | ☐ OK ☐ KO |
| D8 | D4 ; `presidence` | « Paramétrage › Confidentialité » : décocher « Évaluation en double aveugle », enregistrer. | Refus « Réglage gelé : des soumissions existent… ». Ne pas tester le forçage par l'ADMIN avec motif : la suite suppose le double aveugle | RG-19, F9 | ☐ OK ☐ KO |
| D9 | D5 ; `admin` ; opérateur | 1. R1 : nouveau brouillon laissé non soumis.<br>2. `admin` : « Paramétrage › Calendrier », « Clôture de l'appel » à l'heure de l'édition, dans environ une heure (voir le calendrier ci-dessus).<br>3. Opérateur : `deploy/cron.sh remind_drafts`, deux fois. | R1 reçoit un seul rappel « l'appel ferme le … » (e-mail et cloche), même si la commande est relancée | F13, D13, règle n° 9 | ☐ OK ☐ KO |
| D10 | Clôture passée, avant le passage suivant de `close_call` | 1. R1 tente de modifier S1, puis de créer une soumission.<br>2. `president.cs` : « Soumissions », fiche de S1, « Dérogations (RG-02) » : échéance à 48 h, motif, « Accorder la dérogation ».<br>3. R1 modifie S1.<br>4. `presidence` : « Contrôle › Journal », action `submission.`. | Modification et création refusées ; dérogation accordée, e-mail à R1, modification acceptée ; `submission.extension_granted` avec le motif | RG-02, RG-17, F8 | ☐ OK ☐ KO |
| D11 | D10 ; opérateur | 1. `president.cs` : « Révoquer » la dérogation.<br>2. Opérateur : `deploy/cron.sh close_call`, deux fois. | S1 à S5 en « Vérification de recevabilité » ; S6 retirée et le brouillon de R1 inchangés ; second passage sans effet ; S1 n'est plus modifiable | RG-02, F8, règle n° 9 | ☐ OK ☐ KO |
| D12 | D11 ; `president.cs` | « Soumissions » : filtres (état, thématique, type, langue, recherche par nom d'auteur, « Doublons possibles seulement »), « Filtrer » ; fiche de S1 ; « Exporter (CSV) ». | Liste filtrée cohérente ; fiche avec auteurs, adresses, versions du PDF, historique ; export CSV téléchargé et journalisé ; une cellule commençant par « = » reste du texte dans le tableur | F10, RG-17 | ☐ OK ☐ KO |
| D13 | D11 ; `co.secretariat` | « Soumissions », fiche de S1. | Mêmes informations, identité des auteurs comprise ; ni dérogation ni export (absents ou refusés par le serveur) | F10, règle n° 2 | ☐ OK ☐ KO |

## 6. Démo E — Évaluation et décision (L4)

Source : plan L4, « Démo E » ; bilan L4, §2. Préalable : D terminée (S1 à S5 en recevabilité) ;
`president.cs`, `relecteur1` à `relecteur3`, R3 (relectrice réelle), R2, R1, `presidence`,
`co.secretariat` ; valeurs par défaut de l'édition : double aveugle, deux relecteurs par
soumission, seuil de divergence de 30 points, note finale non pondérée par la confiance. Notes
proposées : S1 4 partout (80) ; S2 5 partout et 3 partout (100 et 60) ; S3 4 partout ; S4 2 et
3 partout (40 et 60).

| N° | Préalable | Étapes | Résultat attendu | Règle | OK/KO |
|---|---|---|---|---|---|
| E1 | `president.cs` | « Paramétrage › Grilles d'évaluation », « Grille de démonstration », « Modifier » : poids donnant une somme différente de 100 ; « Enregistrer la grille » ; rétablir. | Refus, « Somme des poids : … (100 attendu). » ; grille 25/30/15/15/15, notes de 0 à 5 | RG-05, H3 | ☐ OK ☐ KO |
| E2 | D11 | « Évaluation › Pilotage de l'évaluation », S5 : « Non recevable : rejeter », motif. | S5 « Rejetée » ; e-mail avec le motif produit pour `auteur1` (`outbox`) | H10 | ☐ OK ☐ KO |
| E3 | D2 | Fiche de S1 dans le pilotage, « Relecteurs disponibles » : « Affecter… » Serge Ekra ; « Affecter… » Claire Martin sans motif, puis avec un motif (réauthentification) ; puis « Annuler… » son affectation, avec motif. | Conflits affichés : « auteur » (Serge Ekra), « même institution » (Claire Martin) ; Serge Ekra refusé sans levée possible ; Claire Martin refusée sans motif, affectée avec motif (« levé par … ») ; levée et annulation journalisées | RG-03, H8, RG-17 | ☐ OK ☐ KO |
| E4 | E3 | 1. Affecter : S1 → `relecteur1`, `president.cs` ; S2 → `relecteur2`, `relecteur3` ; S3 → `relecteur1`, `relecteur2` ; S4 → `relecteur3` seul.<br>2. S4 : « Recevable : ouvrir l'évaluation » ; affecter `president.cs`, recommencer ; ouvrir S1 à S3. | Ouverture refusée avec un seul relecteur (« Affectez d'abord le nombre de relecteurs requis. ») ; puis « En cours d'évaluation » ; e-mails d'affectation produits (`outbox`) | H6, H10 | ☐ OK ☐ KO |
| E5 | E4 | 1. `relecteur1` : « Mes évaluations », S1, « Décliner… », cocher « Je déclare un conflit d'intérêts avec cette soumission », motif, « Décliner ».<br>2. `president.cs` : affecter R3 à S1. | S1 disparaît de la liste de `relecteur1` ; conflit déclaré visible au pilotage ; R3 reçoit l'e-mail d'affectation avec le lien vers l'évaluation | RG-03, H8 | ☐ OK ☐ KO |
| E6 | E5 ; R3 | R3 : ouvrir S1 ; lire chaque écran ; « Télécharger le PDF » et lire ses propriétés ; facultatif : réponses de l'API dans les outils de développement. | « Double aveugle : les auteurs ne vous sont pas présentés. » ; ni nom, ni adresse, ni institution d'auteur, à aucun écran ; PDF sans métadonnées d'auteur | RG-04, H9 | ☐ OK ☐ KO |
| E7 | E4 ; `president.cs` | 1. S1 : laisser un critère obligatoire vide, « Envoyer l'évaluation ».<br>2. Noter 4 partout, recommandation, confiance, commentaire aux auteurs, commentaire confidentiel au comité ; « Enregistrer le brouillon », puis envoyer.<br>3. « Grilles d'évaluation » : tenter de modifier la grille. | Envoi refusé tant qu'un critère obligatoire manque ; « Note pondérée indicative : 80 » pendant la saisie ; « note retenue par le serveur : 80,00 / 100 » ; grille « verrouillée » : « Grille déjà utilisée… dupliquez-la » | RG-05, RG-06, H4 | ☐ OK ☐ KO |
| E8 | E7 ; R3, `relecteur2`, `relecteur3` | R3 envoie S1 (4 partout) ; `relecteur2` envoie S2 (5 partout), `relecteur3` S2 (3 partout). | S1 et S2 passent seules en « Évaluée » ; S2 : divergence de 40 points au pilotage (« Avancement ») et au tableau de bord ; e-mail de divergence aux présidents du CS (R2 le reçoit) ; discussion de S2 ouverte automatiquement | RG-07, H12, H14 | ☐ OK ☐ KO |
| E9 | E8 | 1. `relecteur3` : S2, « Discussion » : lire l'autre évaluation, « Publier » un message ; passer ses notes à 4, « Renvoyer l'évaluation modifiée ».<br>2. `relecteur1` tente d'ouvrir S2. | Autre évaluation sous « Relecteur N », jamais nominative ; nouvelle version historisée ; note finale de S2 : 90 ; `relecteur1` n'a pas accès à S2 | RG-08, RG-06, H11, H13 | ☐ OK ☐ KO |
| E10 | Facultatif : affectation active depuis plus de 24 h, sans évaluation envoyée | `president.cs` : « Échéance… » à moins de 24 heures ; opérateur : `deploy/cron.sh remind_reviewers`, deux fois. | Une seule relance J-1 produite pour le relecteur (`outbox`, ou e-mail reçu si le relecteur est R3) | H15, règle n° 9 | ☐ OK ☐ KO |
| E11 | E4 | `relecteur1` et `relecteur2` notent S3 (4 partout) ; `relecteur3` (2 partout) et `president.cs` (3 partout) notent S4. | Toutes « Évaluée » ; « Avancement » par relecteur et par thématique à jour | RG-07 | ☐ OK ☐ KO |
| E12 | E11 ; R1 | 1. `president.cs` : « Évaluation › Classement et décisions », seuil 70, « Simuler », « Préparer les décisions selon le seuil », « Enregistrer les décisions (4) ».<br>2. Fiche de S3 au pilotage : « Annuler la décision », issue « acceptée sous réserve de corrections », message du comité, « Enregistrer la décision ».<br>3. R1 consulte S1 dans le portail. | « 3 soumission(s) retenue(s) sur 4 au seuil de 70 », par type et par thématique ; décisions « provisoire » ; R1 ne voit aucune décision et ne reçoit aucun e-mail | RG-09, H16 | ☐ OK ☐ KO |
| E13 | E12 | 1. `president.cs` : « Publier les résultats (4) », réauthentification.<br>2. `presidence` : « Contrôle › Journal », action `decision.`. | S1, S2 « Acceptée », S3 « Acceptée sous réserve de corrections », S4 « Rejetée » ; e-mails de décision (R1 reçoit le sien) ; `decision.published` | RG-09, RG-17 | ☐ OK ☐ KO |
| E14 | E13 ; R1 | Portail, S1 : « Décision du comité ». | Issue, format attribué, message du comité, commentaires aux auteurs sous « Relecteur 1 » et « Relecteur 2 » ; ni nom de relecteur, ni note, ni commentaire confidentiel | RG-10, H11 | ☐ OK ☐ KO |
| E15 | E13 ; PDF finaux | 1. R1 : « Version finale », PDF, « Déposer la version finale ».<br>2. `auteur2` (S3) : sans lettre de réponse, puis avec.<br>3. `auteur1` (S2) : dépôt. | R1 : e-mail « Version finale reçue » ; S3 refusée sans lettre (« La lettre de réponse aux relecteurs est obligatoire. »), puis acceptée ; S1 à S3 « Version finale reçue » | H18 | ☐ OK ☐ KO |
| E16 | E13 | 1. `president.cs` : « Exporter les évaluations (CSV) » (réauthentification).<br>2. `co.secretariat` : chercher « Évaluation » dans le rail ; saisir `/gestion/editions/<id>/pilotage`. | Export téléchargé et journalisé ; le CO n'a aucun écran d'évaluation ; « Accès refusé » | RG-17, H19 | ☐ OK ☐ KO |
| E17 | E13 | `president.cs` : « Grilles d'évaluation », « Dupliquer en nouvelle version ». | « Nouvelle version créée. », modifiable ; l'ancienne reste verrouillée ; notes envoyées inchangées | RG-05 | ☐ OK ☐ KO |

## 7. Démo F — Programme (L5)

Source : plan L5, « Démo F » ; bilan L5, §2. La démo prévoit douze communications : la recette
dispose des trois acceptées en E (S1 à S3). Préalable : E terminée ; `co.programme`,
`presidence`, `admin`, `co.finances`, `intervenant`, R1, R2 ; sessions sur J1 et J2.

| N° | Préalable | Étapes | Résultat attendu | Règle | OK/KO |
|---|---|---|---|---|---|
| F1 | E15 ; R1, `auteur1`, `auteur2` | Portail, S1 : « Présentation », cocher les présentateurs, « Confirmer ma présentation » ; idem pour S2 et S3. | « Présentation confirmée. » ; état « Présentation confirmée » ; « Programme › Planificateur » : « À programmer (3) » | I5 | ☐ OK ☐ KO |
| F2 | `admin` ; R2 | « Comités › Invitations » : inviter R2, rôle « président de session » ; R2 accepte par le lien. | R2 cumule « président du comité scientifique » et « président de session » | I10, RG-20 | ☐ OK ☐ KO |
| F3 | `co.programme` | « Programme › Salles » : « Ajouter une salle » « Salle C » (capacité, « Vidéoprojecteur », « Micro », accessible). | Trois salles actives | I9 | ☐ OK ☐ KO |
| F4 | F2, F3 | « Programme › Sessions », « Ajouter une session » (heures de l'édition) :<br>J1 : Ouverture (Amphithéâtre A, 09:00–09:30) ; Conférence plénière (Amphithéâtre A, 09:30–10:30) avec élément libre « Conférence invitée », intervenant invité Ama Owusu ; Pause (10:30–11:00) ; Session parallèle 1 (Amphithéâtre A, 11:00–12:00) et Session parallèle 2 (Salle B, 11:30–12:30), présidente de séance R2 pour les deux ; Repas (12:30–14:00).<br>J2 : Session parallèle 3 (Salle C, 09:00–09:30) avec un élément libre « Discussion » ; Clôture (Amphithéâtre A, 11:00–11:30).<br>Essayer aussi une session hors des dates de l'édition. | Huit sessions sur deux jours ; « Session créée : ajoutez ses rôles et ses éléments libres. » ; hors des dates : « La session doit se tenir pendant l'édition. » | I2, I10, I11, I12 | ☐ OK ☐ KO |
| F5 | F1, F4 | « Programme › Planificateur » : S2 dans Session parallèle 1 à la souris ; S3 au clavier (« Placer dans… », session, « Placer ») ; S1 dans Session parallèle 3 au clavier ; monter et descendre au clavier ; sur téléphone, vue en liste. | Placements annoncés (« « … » placée dans « … » ») ; horaires calculés ; tout se fait au clavier | I3, I15 | ☐ OK ☐ KO |
| F6 | F5 | Lire « Conflits (N) » ; `presidence` : tenter « Publier le programme ». | « R2 est attendu(e) à deux endroits en même temps … (RG-12) » ; « Session parallèle 3 déborde de 10 min (RG-13) » (deux créneaux de 20 min, durée par défaut, pour 30 min) ; publication refusée (« Le programme contient des conflits… ») | RG-12, RG-13, I4 | ☐ OK ☐ KO |
| F7 | F6 | Session parallèle 2 : retirer R2 des rôles de séance, ajouter `president.cs` comme président de séance ; Session parallèle 3 allongée à 09:00–09:45 (ou durée réduite par « Appliquer la durée »). | « Aucun conflit. » | RG-12, RG-13 | ☐ OK ☐ KO |
| F8 | F7 | 1. `admin` : « Programme › Publication du programme ».<br>2. `presidence` : « Publier le programme », réauthentification. | `admin` : « Seul le président de la conférence publie le programme. » ; « Programme publié (version 1). » ; S1 à S3 « Programmée » ; e-mails aux présentateurs, à R2 et à l'intervenant (R1 et R2 reçoivent) ; historique des publications | I6, I16, RG-17 | ☐ OK ☐ KO |
| F9 | F8 ; opérateur | Opérateur : republication ; visiteur : `/fr/programme/` (filtres jour, salle, thématique, type ; recherche), page d'un jour (« Liste », « Grille par salle »), page d'une session ; `/en/program/`. | Programme publié visible sans compte, en FR et EN, heures locales ; noms et institutions des auteurs affichés (Q14 ouverte), aucune adresse ; avant la republication, l'ancienne page reste servie | I7 | ☐ OK ☐ KO |
| F10 | F8 ; R1, R2 | R1 : « Mon passage » (`/compte/mon-passage`), « Ajouter à mon agenda (.ics) », importer le fichier ; S1 dans « Mes soumissions ». R2 : « Mon passage ». | Passage, salle et présidence ; fichier iCal importé aux bonnes heures ; « Programmée : … » dans la soumission ; R2 voit sa présidence de la Session parallèle 1 | I8 | ☐ OK ☐ KO |
| F11 | F8 | `co.programme` : décaler Session parallèle 3 ; `presidence` : republier ; opérateur : `outbox`. | « Programme publié (version 2). », différences listées ; seule R1 reçoit un e-mail ; rien pour R2 ni pour les autres présentateurs | I16 | ☐ OK ☐ KO |
| F12 | `co.finances` | « Programme › Planificateur » et « Programme › Sessions ». | « Lecture seule : vos rôles ne permettent pas de modifier le programme. » | I1, règle n° 2 | ☐ OK ☐ KO |

## 8. Démo G — Inscriptions et paiements (L6)

Source : plan L6, « Démo G » ; bilan L6, §2. Préalable : F terminée ; `co.finances`,
`co.secretariat`, `co.programme`, `presidence`, `president.cs`, R1, `auteur1`, `auteur2`,
`participant1`, `participant2`, `intervenant` ; période préférentielle en cours ; montants en
XOF, sans décimales ; paiement en ligne selon §1.2, point 5.

| N° | Préalable | Étapes | Résultat attendu | Règle | OK/KO |
|---|---|---|---|---|---|
| G1 | `co.finances` | « Paramétrage › Tarifs » :<br>1. catégories « Étudiant » (« Justificatif demandé ») et « Intervenant invité » ;<br>2. grille préférentiel, normal, sur place × local, international (« Intervenant invité » à 0) ;<br>3. options « Atelier » (2 places) et « Dîner » ;<br>4. code promo `DEMO10`, 10 % ;<br>5. « Date limite d'annulation » (heure de l'édition), remboursé avant 100 %, après 0 %. | Tout est enregistré ; montants entiers ; dates affichées à l'heure de l'édition ; devise figée dès la première inscription | J2, J3, J4, J9, D13 | ☐ OK ☐ KO |
| G2 | `co.finances` | « Paramétrage › Facturation » : identifiants, coordonnées bancaires, mention sans TVA ; enregistrer (réauthentification). | « Mentions complètes : les factures s'émettent à la confirmation. » ; préfixes F, AV, PF | RG-14, J8 | ☐ OK ☐ KO |
| G3 | G1 ; opérateur | Opérateur : republication ; visiteur : `/fr/inscription/` et `/en/registration/`. | Dates, catégories, grille, options, moyens de paiement ; « S'inscrire » mène à « Mon inscription » | J13 | ☐ OK ☐ KO |
| G4 | G3 ; R1 | « Mon inscription » : « Étudiant », option « Atelier », code `DEMO10`, « Calculer le prix », moyen de paiement, « Confirmer la commande » ; « Déposer le justificatif ». | Prix calculé par le serveur (période préférentielle, zone selon le pays du profil, remise) ; « En attente de paiement » ; e-mail de commande ; justificatif enregistré | J2 à J5 | ☐ OK ☐ KO |
| G5 | G4 ; fournisseur configuré (sinon : virement, payé comme en G6) | R1 : « Payer en ligne » ; payer sur la page du prestataire (bac à sable) ; revenir. | Navigateur dirigé vers la page hébergée, aucune saisie de carte sur la plateforme ; « Paiement en cours de vérification » tant que le prestataire n'a pas confirmé, puis « Paiement reçu : votre inscription est confirmée. » ; facture `F-DEMO-<année>-00001` et code QR ; e-mail. Notification réelle reçue par l'hébergement : **à confirmer** (V29) | RG-15, J6, règle n° 7 | ☐ OK ☐ KO |
| G6 | `participant1`, `co.finances` | 1. `participant1` : « Chercheur », « Virement », « Organisme » : Université fictive C ; « Obtenir une facture pro forma ».<br>2. `co.finances` : « Inscriptions », fiche, « Enregistrer un paiement reçu » (réauthentification). | Pro forma `PF-DEMO-…`, non comptable ; puis « Paiement enregistré : inscription confirmée. » ; facture au numéro suivant, sans trou | J7, RG-14 | ☐ OK ☐ KO |
| G7 | `co.finances` | 1. « Inscriptions », « Saisir une inscription » pour `participant2@fictif.invalid`, virement ; paiement reçu.<br>2. Fiche : « Badge (PDF) », **à garder pour H6**.<br>3. « Annuler l'inscription » (motif), puis « Enregistrer un remboursement » (100 %). | Inscription confirmée et facturée ; annulation : places libérées, remboursement dû ; « Remboursement enregistré, avoir émis. » ; « Factures et avoirs » : facture et avoir `AV-DEMO-…`, aucune pièce supprimée | RG-14, J9 | ☐ OK ☐ KO |
| G8 | F8 ; `co.programme`, `presidence` | 1. « Paramétrage › Programme » : cocher « Exiger l'inscription d'un présentateur (RG-11) ».<br>2. Planificateur : lire les conflits ; `presidence` : modifier une session, tenter de publier.<br>3. `auteur1` (« Chercheur », option « Atelier ») et `auteur2` (même option) s'inscrivent par virement ; `co.finances` enregistre les paiements.<br>4. `presidence` publie. | Conflit « aucun présentateur inscrit (RG-11) » pour S2 et S3, badge « Présentateur non inscrit » ; publication refusée ; `auteur2` : « Plus de place disponible pour cette option. » (quota de 2 atteint), commande sans option ; après confirmation, conflits levés, publication acceptée | RG-11, J3, J10 | ☐ OK ☐ KO |
| G9 | G1 ; `co.finances` | « Saisir une inscription » pour `intervenant`, catégorie « Intervenant invité ». | Confirmée sans paiement (« sans paiement ») ; badge disponible. La catégorie à 0 est aussi proposée à tous les participants dans « Mon inscription » (aucune restriction par rôle) : point à apprécier, la « Gratuité » de la fiche étant l'alternative | J2, J5 | ☐ OK ☐ KO |
| G10 | G4 à G9 | `co.finances` : « Inscriptions › Finances » ; « Factures et avoirs », « Exporter (CSV) » ; « Paiements » ; « Inscriptions », « Exporter (CSV) » (réauthentification). | Encaissé, remboursé, net, impayés, par catégorie et par moyen ; export comptable conforme aux pièces ; exports journalisés | J12, RG-17 | ☐ OK ☐ KO |
| G11 | — | `presidence` : « Inscriptions », « Finances » ; `co.secretariat` : « Paramétrage › Tarifs » ; `president.cs` : `/gestion/editions/<id>/inscriptions`. | Chair : consultation sans action ; secrétariat : tarifs en lecture seule ; président du CS : « Accès refusé » | J1, règle n° 2 | ☐ OK ☐ KO |

## 9. Démo H — Jour J et attestations (L7)

Source : plan L7, « Démo H » ; bilan L7, §2. Préalable : F et G terminées (programme publié ;
inscriptions confirmées de R1, `auteur1`, `auteur2`, `participant1`, `intervenant` ; badge de
`participant2` imprimé avant son annulation) ; `benevole` sur un **téléphone réel** (un iOS et
un Android si possible) ; `signataire`, `admin`, `co.secretariat`, `co.programme`,
`co.relations`, R2 ; badges imprimés ou affichés sur un autre écran.

| N° | Préalable | Étapes | Résultat attendu | Règle | OK/KO |
|---|---|---|---|---|---|
| H1 | `signataire` ; `admin` | 1. `signataire` : « Attestations et lettres › Ma signature » : nom affiché, fonctions FR et EN, image PNG.<br>2. `admin` : saisir `/gestion/editions/<id>/signature`. | « Signature complète » ; l'administrateur n'y a pas accès | K18 | ☐ OK ☐ KO |
| H2 | H1 ; `co.secretariat` | « Attestations et lettres › Modèle des attestations » : mode « Image de la signature », en-tête officiel (PNG), signataire pour la participation, la communication et la lettre, textes FR et EN ; « Aperçu (PDF) ». | Aperçu avec en-tête, signature et QR ; le mode PAdES n'est proposé qu'avec les clés de chiffrement du serveur (sinon « Signature PAdES indisponible… ») | K18, K19 | ☐ OK ☐ KO |
| H3 | G ; `co.secretariat` | « Jour J › Badges » : « Préparer les fichiers », télécharger ; fiche d'une inscription : « Badge (PDF) ». | Planches A4 de quatre badges A6, inscriptions confirmées seulement ; badge seul ; pays en code ISO. Délai pour 200 badges **à confirmer** sur l'hébergement | K3 | ☐ OK ☐ KO |
| H4 | Téléphone ; `benevole` | 1. Se connecter (2FA) sur le téléphone ; ouvrir « Jour J › Accueil (scan) » en ligne ; l'installer depuis le navigateur (écran d'accueil).<br>2. « Réglages du poste » : mode « Accueil de la conférence », nom du poste.<br>3. « Télécharger la liste hors ligne ». | Application installée, rouverte depuis l'écran d'accueil ; « Liste de N participant(s), téléchargée le …, valable jusqu'au … » (48 h). iOS Safari et Android : **à confirmer** | K5, K15 | ☐ OK ☐ KO |
| H5 | H4 | En ligne : « Allumer la caméra » ; scanner R1, puis R1 à nouveau, puis `participant1`. | « Pointé », « Déjà pointé », « Pointé » ; nom du poste repris dans « Présences » | K2, K4 | ☐ OK ☐ KO |
| H6 | H5 ; badge de `participant2` (G7) | 1. « Mettre à jour la liste ».<br>2. Couper le réseau ; scanner `auteur1`, R1, `participant2`.<br>3. Rétablir le réseau (« Synchroniser » si la file ne part pas seule). | Hors ligne : `auteur1` accepté (« Décidé sans réseau… »), R1 « Déjà pointé », `participant2` « Inscription annulée » ; au retour du réseau, la file part et le serveur confirme le pointage de `auteur1` (« N pointage(s) envoyé(s)… ») ; aucun doublon dans « Présences » | K4, K5 | ☐ OK ☐ KO |
| H7 | `co.secretariat` ; `auteur2` | Fiche de l'inscription de `auteur2` : « Remplacer le badge » (motif) ; le bénévole scanne l'ancien, puis le nouveau. | Ancien : « Badge remplacé : ancien badge refusé » ; nouveau : « Pointé » | K2 | ☐ OK ☐ KO |
| H8 | `co.secretariat` ; `benevole` | 1. « Jour J › Comptoir » : `comptoir@fictif.invalid`, prénom, nom, institution, « Chercheur », « Paiement reçu au comptoir », « Inscrire » ; « Imprimer le badge ».<br>2. Le bénévole scanne ce badge et celui de `intervenant`. | « Compte créé sans mot de passe… » ; inscription confirmée au tarif de la période en cours (préférentiel sur `DEMO` : le tarif « sur place » ne s'applique qu'après la clôture des inscriptions), facture, badge ; deux « Pointé » | K13, J2 | ☐ OK ☐ KO |
| H9 | F8 ; R2 | R2 : « Jour J › Sessions du jour » ; Session parallèle 1 : « Émarger l'entrée » (scanner R1), « Marquer présentée » S2 et S3 ; chercher une session qu'elle ne préside pas. | Seules ses sessions sont listées, sans liste hors ligne ; présents comptés ; S2, S3 « Présentée » ; aucune action ailleurs | K1, K7, K8 | ☐ OK ☐ KO |
| H10 | H9 ; `co.programme` | « Sessions du jour » : « Marquer présentée » S1 ; « Corriger : non présentée » (motif) ; la marquer de nouveau. | S1 « Présentée » ; correction journalisée avec son motif | K8, RG-17 | ☐ OK ☐ KO |
| H11 | H5 à H8 ; `co.secretariat` | « Jour J › Présences » : rechercher `participant1`, « Annuler le pointage » (motif) ; le refaire (référence saisie à l'accueil) ; « Exporter (CSV) » (réauthentification). | Pointage annulé, motif conservé, puis refait ; export téléchargé | K4, RG-17 | ☐ OK ☐ KO |
| H12 | H2, H10, H11 | `co.secretariat` : « Attestations », « Émettre » la participation, puis la communication ; opérateur : `deploy/cron.sh run_jobs` (ou passage du cron). R1 : « Mes documents ». | Participation : les seules personnes présentes (R1, `auteur1`, `auteur2`, `participant1`, `intervenant`, compte du comptoir) ; communication : présentateurs de S1 à S3 ; rien pour `participant2` ; e-mail à R1 ; PDF téléchargeable | RG-16, K9, K11 | ☐ OK ☐ KO |
| H13 | H12 ; second téléphone | 1. Scanner le QR de l'attestation de R1.<br>2. `/verification/` avec un code inventé.<br>3. `co.secretariat` révoque une autre attestation (motif) ; vérifier son code. | « Attestation authentique » (titulaire, conférence, date) ; « Aucun document ne correspond à ce code. » ; « Attestation révoquée » | K10 | ☐ OK ☐ KO |
| H14 | G6 ; `participant1`, `co.relations` | 1. `participant1` : « Mes documents », « Demander une lettre d'invitation » (passeport fictif, séjour de moins de 90 jours, ambassade).<br>2. `co.relations` : « Attestations et lettres › Lettres d'invitation », fiche, « Émettre la lettre ».<br>3. `participant1` télécharge la lettre ; vérification par son QR. | Demande « À instruire », puis lettre émise, signée, vérifiable ; numéro de passeport masqué dans « Mes documents » ; effacement 30 jours après l'édition non vérifiable ici | K12, K14 | ☐ OK ☐ KO |
| H15 | H4 | Bénévole, hors réseau : pointer un badge, puis « Se déconnecter » avant la synchronisation. | Avertissement « Pointages non synchronisés » ; après confirmation, liste et file effacées de l'appareil | K5 | ☐ OK ☐ KO |

## 10. Démo I — Logistique, partenaires, communication et rapports (L8)

Source : plan L8, « Démo I » ; bilan L8, §2. Préalable : H terminée (cinq personnes présentes
avec un compte utilisable) ; `presidence`, `co.finances`, `co.relations`, `co.logistique`,
`co.benevoles`, `co.communication`, `co.secretariat`, `benevole`, `intervenant`,
`participant1`, R1.

| N° | Préalable | Étapes | Résultat attendu | Règle | OK/KO |
|---|---|---|---|---|---|
| I1 | `presidence` ; `co.logistique` | « Organisation › Tâches » : « Nouvelle tâche » (responsable `co.logistique`, échéance), une seconde ; « Déplacer vers » au clavier ; commentaire et pièce jointe ; `co.logistique` : cloche, « Organisation › Activité ». | Tâches dans les trois colonnes ; « Une tâche vous est confiée … » ; fil d'activité à jour | N3, N14 | ☐ OK ☐ KO |
| I2 | G ; `co.finances` | « Organisation › Budget » : lignes de dépense « Lieu » et « Restauration », prévu et réalisé, justificatif ; « Exporter (XLSX) ». | Lignes « Inscriptions » et « Partenariats » marquées « calculé », reprenant les montants ; soldes prévu et réalisé, écarts ; export | N4 | ☐ OK ☐ KO |
| I3 | `co.relations` ; opérateur | 1. « Partenaires › Niveaux de partenariat » : niveau « Or ».<br>2. « Nouveau partenaire » (niveau Or, contribution convenue, contact), logo, cocher « Publier sur le portail », montant reçu.<br>3. Opérateur : republication ; `/fr/partenaires/`. | Partenaire et logo publiés, sans contact, montant ni statut ; logo non public avant la publication ; ligne « Partenariats » du budget mise à jour | N5 | ☐ OK ☐ KO |
| I4 | F4 ; `co.logistique`, `intervenant` | 1. `co.logistique` : « Logistique › Intervenants invités », fiche d'Ama Owusu : hôtel, nuits, « Réservé », note interne.<br>2. `intervenant` : « Ma venue » (`/compte/ma-venue`) : besoins (dont « Interprétation »), arrivée, moyen, référence. | L'intervenant voit l'hôtel et la prise en charge, jamais la note interne ; la liste signale « Manque en salle : … » pour l'équipement absent de la salle de sa session | N6 | ☐ OK ☐ KO |
| I5 | `participant1` | « Régime et annonces » (`/compte/preferences`) : « Sans gluten », enregistrer sans cocher le consentement, puis en le cochant. | « Cochez la case de consentement pour enregistrer. », puis « Régime enregistré. » ; mention de l'effacement 30 jours après la conférence | RG-23, N7 | ☐ OK ☐ KO |
| I6 | I5 ; `co.logistique`, `co.finances` | 1. `co.logistique` : « Logistique › Restauration » : déjeuner de J1 pour les inscrits, marge 10 % ; « Commande au traiteur (PDF) » ; « Liste nominative (CSV) » (réauthentification).<br>2. `co.finances` : saisir `/gestion/editions/<id>/logistique/restauration`. | Effectifs et régimes agrégés sans nom ; noms seulement dans la liste nominative, export journalisé ; `co.finances` : « Accès refusé » | RG-23, N8, règle n° 2 | ☐ OK ☐ KO |
| I7 | `co.benevoles`, `benevole` | 1. « Logistique › Postes des bénévoles » : poste « Accueil » de J1 (2 bénévoles), « Affecter » `benevole`.<br>2. `benevole` : « Jour J › Mon planning », « Télécharger mon planning (iCal) » ; notifications du portail. | « 1 bénévole(s) sur 2 », « 1 place(s) à pourvoir » ; planning et iCal aux heures du lieu ; « Un poste de bénévole vous est confié … » | N9 | ☐ OK ☐ KO |
| I8 | G ; `co.communication` | « Communication › Annonces » : « Nouvelle annonce » « Salle B fermée : plénière en salle A » ; canaux « Bandeau », « E-mail », « Cloche » ; destinataires « Inscrits confirmés » ; aperçus FR et EN ; « M'envoyer un essai » ; « Publier » (réauthentification). | Bandeau visible aussitôt sur le portail, sans republication, refermable ; R1 reçoit l'e-mail (raison de l'envoi, lien de désabonnement) ; compteurs « Destinataires », « E-mails partis » ; essai produit (`outbox`) ; envoi limité à la moitié du plafond horaire | RG-22, N10, N11 | ☐ OK ☐ KO |
| I9 | F8 ; `co.communication` ; opérateur | Annonce sur le canal « Actualités », publiée ; opérateur : republication ; `/fr/actualites/` et `/fr/intervenants/`. | Actualité publiée ; page « Intervenants » avec Ama Owusu, lue dans le programme publié | N10 | ☐ OK ☐ KO |
| I10 | H12 ; `co.communication` | « Communication › Questionnaires » : « Nouveau questionnaire », « Partir du modèle… », ouverture maintenant, clôture à 7 jours ; « Publier » ; opérateur : `deploy/cron.sh run_jobs`. | Invitations aux seules personnes présentes (cloche et e-mail ; R1 reçoit) ; `participant2` n'est pas invitée | RG-21, N12 | ☐ OK ☐ KO |
| I11 | I10 | 1. R1, `auteur1`, `auteur2`, `participant1` : « Questionnaires », « Répondre », « Envoyer ma réponse » ; `co.communication` : « Résultats ».<br>2. `intervenant` répond ; « Résultats ».<br>3. R1 tente de répondre de nouveau. | À 4 réponses : « Moins de 5 réponses : les résultats restent masqués… » ; à 5 : moyennes ; textes libres seulement dans l'export, mélangés ; seconde réponse refusée ; ni date ni lien entre une personne et sa réponse | RG-21, N12 | ☐ OK ☐ KO |
| I12 | I8, I11 ; R1 | Lien de désabonnement de l'e-mail (`/desabonnement/<jeton>`), « Confirmer le désabonnement » ; « Régime et annonces ». | « C'est fait : vous ne recevrez plus les annonces… » ; abonnement décoché ; une annonce suivante n'arrive pas ; e-mails de service maintenus | RG-22, N11 | ☐ OK ☐ KO |
| I13 | I1 à I12 ; `presidence` | « Rapports » : parcourir les sections ; « Exporter (XLSX) ». | Sections Soumissions, Relecture, Inscriptions, Recettes, Présence, Satisfaction, Budget, Partenaires ; taux de présence, taux de réponse, satisfaction, écart budgétaire ; graphiques doublés de tableaux ; aucun nom | N13 | ☐ OK ☐ KO |
| I14 | — | `co.logistique` : « Rapports ». | Sections limitées à ses capacités (soumissions, inscriptions, présence) | N2, N13 | ☐ OK ☐ KO |

## 11. Points à confirmer et contrôles différés

**À confirmer sur l'hébergement** (non vérifiables depuis le dépôt) :

- aperçu Open Graph réel sur les réseaux sociaux (C8) ;
- réception de la notification de paiement, appels sortants vers le prestataire, délai de
  réponse au webhook (G5 ; V29) ;
- caméra et installation de l'accueil sur iOS Safari et Android, service worker servi sous
  `/gestion/`, en-têtes par chemin (`Permissions-Policy`) (H4 à H6) ;
- délai de génération des planches de 200 badges (H3) ;
- compression HTTP des pages pré-rendues (F9) ; Pillow pour les images (V28 ; C4, C7, I3) ;
- plafond réel d'e-mails et délai d'un envoi groupé (I8) ;
- fréquence réelle du cron (`run_jobs`, minute de `close_call`) (D9 à D11, H12, I10).

**Non jouables dans la journée**, couverts par les tests du dépôt, à observer si la recette
dure plusieurs jours : relances de confirmation de présentation à 3 et 10 jours
(`remind_presentations`), expiration d'une commande impayée (`expire_registrations`, délai d'au
moins une heure en ligne), relance du questionnaire à mi-parcours, rappel quotidien des tâches
(`remind_tasks`), effacement des passeports et des régimes 30 jours après l'édition
(`cleanup`).

## 12. Anomalies

Une ligne par anomalie. Gravité : bloquante, majeure ou mineure (§1.1).

| N° | Scénario | Gravité | Description (constaté, attendu) | Correctif | Commit |
|---|---|---|---|---|---|
| AN-01 | | | | | |
| AN-02 | | | | | |
| AN-03 | | | | | |
| AN-04 | | | | | |
| AN-05 | | | | | |

## 13. Bilan de la recette

| Démo | Scénarios | OK | KO | Dates | Testeur |
|---|---|---|---|---|---|
| A — Compte | 8 (A8 facultatif) | | | | |
| B — 2FA, paramétrage, invitations | 7 | | | | |
| C — Portail public | 10 | | | | |
| D — Soumission | 13 | | | | |
| E — Évaluation et décision | 17 (E10 facultatif) | | | | |
| F — Programme | 12 | | | | |
| G — Inscriptions et paiements | 11 | | | | |
| H — Jour J et attestations | 15 | | | | |
| I — Logistique, partenaires, communication, rapports | 14 | | | | |
| **Total** | **107** | | | | |

Anomalies bloquantes ouvertes : ……  Anomalies majeures ouvertes : ……

Recette prononcée le …… par …… (commanditaire), sous réserve des anomalies listées au §12.
Restauration de la sauvegarde d'avant la démonstration faite le …… par …… (opérateur).
