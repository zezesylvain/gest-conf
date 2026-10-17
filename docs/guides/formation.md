# Formation — déroulé des ateliers

Support de formation (plan L9, décision S11) : **trois ateliers d'une demi-journée** (3 h 30,
pause comprise), joués sur l'édition de démonstration. Chaque atelier s'appuie sur le guide
de son public et sur le [cahier de recette](../L9-cahier-de-recette.md), dont il reprend les
démos (« voir le cahier de recette, démo X »). Dates et publics restent à fixer par le
commanditaire (question 10 du plan L9).

| Atelier | Public | Guides |
|---|---|---|
| 1 | Comité scientifique et relecteurs | [comite-scientifique.md](comite-scientifique.md), [relecteur.md](relecteur.md) |
| 2 | Comité d'organisation (et présidence) | [comite-organisation.md](comite-organisation.md), [presidence-administration.md](presidence-administration.md) |
| 3 | Bénévoles et accueil | [benevole-accueil.md](benevole-accueil.md) |

## 1. L'édition de démonstration

Créée par l'exploitant, sur une base **sans aucune donnée réelle** (la commande le vérifie) :

```bash
python manage.py backup_db                         # avant : sauvegarde
python manage.py seed_demo --confirm-fictitious    # édition DEMO, courante sur le portail
```

- **Édition `DEMO`** (« Édition de démonstration »), publiée, fuseau `Africa/Abidjan`,
  conférence 90 à 92 jours après la création ; appel ouvert (clôture à J+30), fin des
  évaluations à J+50, version définitive à J+70 ; inscriptions ouvertes (tarif préférentiel
  jusqu'à J+20, clôture à J+85), par virement et sur place (en ligne seulement si un
  prestataire est configuré) ; deux thématiques (Intelligence artificielle, Santé
  publique), un type (Communication orale, PDF facultatif), la grille par défaut, une
  catégorie « Chercheur », des mentions de facturation fictives, deux salles (Amphithéâtre A,
  Salle B).
- **Un compte fictif par rôle**, `<nom>@fictif.invalid` :

| Comptes | Rôle |
|---|---|
| `admin` | Administrateur de l'édition |
| `presidence` | Président de la conférence |
| `president.cs` | Président du comité scientifique |
| `relecteur1`, `relecteur2`, `relecteur3` | Membres du comité scientifique |
| `co.programme`, `co.finances`, `co.secretariat`, `co.logistique`, `co.communication`, `co.relations`, `co.benevoles` | Membres du CO, une fonction chacun |
| `benevole` | Bénévole |
| `signataire` | Signataire |
| `intervenant` | Intervenant invité |
| `auteur1`, `auteur2`, `participant1`, `participant2` | Sans rôle (auteurs, participants) |

- **Mot de passe commun et secret TOTP commun**, affichés **une seule fois** par la commande.
  L'exploitant les remet au formateur par un canal sûr ; ils ne s'écrivent ni dans le dépôt
  ni dans un support distribué. Le secret TOTP sert à tous les comptes à double
  authentification (rôles de gestion, bénévole, signataire) ; l'intervenant, les auteurs et
  les participants n'en ont pas.
- **Aucun e-mail** ne parvient aux comptes fictifs : les exercices s'appuient sur les écrans
  et sur la cloche « Notifications » du portail. Invitations, vérification d'adresse et
  réinitialisation du mot de passe ne peuvent donc pas aller à leur terme pendant l'atelier.
- **Règle de l'atelier** : n'utiliser que des adresses en `@fictif.invalid` (comptoir,
  invitations). Une adresse réelle recevrait des e-mails, et la base ne serait plus
  fictive : les commandes de données fictives y seraient ensuite refusées.
- **Remise à zéro** : prendre une sauvegarde (`backup_db`) après la préparation de chaque
  atelier ; pour rejouer un atelier, l'exploitant la restaure dans une base neuve
  (`restore_db`, runbook de L9.8). Rien ne se défait depuis l'application : décisions et
  programmes publiés, pièces comptables et journal sont en ajout seul.

## 2. Prérequis communs

- Un ordinateur par stagiaire (navigateur à jour) et un **téléphone** ; pour l'atelier 3,
  le téléphone sert aussi de lecteur : caméra indispensable.
- Sur chaque téléphone, une **application d'authentification** (FreeOTP, Aegis, Google
  Authenticator…) dans laquelle on saisit à la main le secret TOTP de la démonstration
  (« saisir une clé » ; un seul ajout suffit pour tous les comptes fictifs).
- L'instance de formation est l'hébergement (ou un build de production) : l'accueil hors
  ligne n'est pas installable sous `ng serve` (pas de service worker en développement).
- Le formateur garde une session `admin` ouverte pour débloquer (invitations, paramétrage)
  et un terminal de l'exploitant joignable (clôture de l'appel, mise en ligne du portail).

## 3. Points à souligner dans chaque atelier

- **Double authentification** : facultative mais recommandée pour la gestion (l'exploitant
  peut l'imposer) ; une fois activée, demandée à chaque connexion et vérifiée par le serveur ;
  codes de secours à conserver ; téléphone perdu sans code de secours = l'exploitant.
- **Réauthentification** : fenêtre « Confirmez votre identité » sur les opérations sensibles
  (publications, exports, paiements, rôles) ; ce n'est pas une panne.
- **Droits par édition** : le rail ne montre que ce que vos rôles permettent ; « Rôle actif »
  n'est qu'un filtre ; le serveur refuse le reste.
- **Double aveugle** (RG-04) : le relecteur ne reçoit jamais l'identité des auteurs ; les
  auteurs ne voient jamais les noms ni les notes des relecteurs (RG-10).
- **Rien n'est public avant la mise en ligne du portail** : contenus, dates, programme
  publié, partenaires et actualités n'apparaissent sur le portail qu'après
  `deploy/deploy.sh --portal-only` par l'exploitant (le bandeau des écrans « Portail » compte
  les modifications en attente). Seul le bandeau de dernière minute paraît aussitôt.
- **Irréversible** : publication des résultats, versions publiées du programme, pièces
  comptables, attestations émises (révocables, jamais supprimées), journal.

## 4. Atelier 1 — Comité scientifique et relecteurs

**Objectifs** : se connecter avec la double authentification ; évaluer en double aveugle
(lire, noter, brouillon, envoyer, renvoyer, discuter, décliner) ; piloter (grille,
recevabilité, affectations, conflits, suivi, décisions, publication des résultats).

**Comptes** : `president.cs`, `relecteur1` à `relecteur3` ; `presidence` (publication
possible) ; `auteur1`, `auteur2` pour le côté auteur.

**Préparation par le formateur** (la veille, voir le cahier de recette, démo D) :

1. `auteur1` et `auteur2` prennent connaissance de la notice et soumettent chacun deux
   communications, dont une avec PDF (vérifier les métadonnées supprimées).
2. `admin` avance la « Clôture de l'appel » (Paramétrage › Calendrier) de quelques minutes ;
   après l'échéance, le cron `close_call` (horaire) fait passer les soumissions en
   recevabilité, ou l'exploitant lance `python manage.py close_call`.
3. `backup_db` (point de reprise de l'atelier).

**Déroulé** :

- **0:00–0:15** — Accueil, objectifs, rôles du comité ; règles : double aveugle, double
  authentification, journal (RG-17).
- **0:15–0:35** — Connexion sur `/compte/connexion` avec le code TOTP ; arrivée dans la
  gestion ; rail, Ctrl+K, bouton « ? », Aide › Guide. Chaque relecteur renseigne « Mes
  expertises ».
- **0:35–0:55** — `president.cs` : Paramétrage › Grilles d'évaluation ; essayer des poids
  dont la somme fait 90 (refus, RG-05) ; voir Paramétrage › Confidentialité en lecture
  seule. Voir le cahier de recette, démo E.
- **0:55–1:25** — Pilotage de l'évaluation : affecter `relecteur1` et `relecteur2` à chaque
  soumission ; « Conflit… » pour `relecteur3` sur l'une d'elles ; déclarer une soumission
  « Non recevable » (motif) et les autres « Recevable : ouvrir l'évaluation ».
- **1:25–1:40** — Pause.
- **1:40–2:20** — Relecteurs : Mes évaluations ; télécharger le PDF et constater l'absence
  d'identité ; noter (note pondérée indicative), « Enregistrer le brouillon », « Envoyer
  l'évaluation » ; un relecteur décline une évaluation en déclarant un conflit (le président
  réaffecte `relecteur3` sur une autre soumission que celle de son conflit). Noter
  volontairement très haut et très bas sur une même soumission.
- **2:20–2:40** — Divergence signalée au pilotage ; « Ouvrir la discussion » ; échanges sous
  pseudonymes ; un relecteur corrige et « Renvoyer l'évaluation modifiée » (RG-06, RG-08).
- **2:40–3:10** — Classement et décisions : « Simuler » un seuil, « Préparer les décisions
  selon le seuil », ajuster (une liste d'attente), « Enregistrer les décisions » ; vérifier
  avec `auteur1` que rien n'est visible ; « Publier les résultats » (réauthentification) ;
  vérifier côté auteur : décision et commentaires « Relecteur N », sans nom ni note
  (RG-09, RG-10) ; « Accepter depuis la liste d'attente ».
- **3:10–3:25** — Soumissions : filtres, doublons, dérogation (RG-02) ; « Exporter les
  évaluations (CSV) » (nominatif, réauthentification, journal) ; Rapports, section relecture.
- **3:25–3:30** — Bilan, questions, remise des guides.

**À souligner** : un relecteur ne voit que ses affectations ; « Envoyer » n'est pas
définitif avant la décision, la publication l'est ; ce que l'auteur reçoit et ne reçoit
jamais ; le président voit l'identité des auteurs, pour juger des conflits.

## 5. Atelier 2 — Comité d'organisation

**Objectifs** : organiser le travail du CO (tâches) ; construire et faire publier le
programme ; tenir les inscriptions et la facturation ; préparer logistique, partenaires,
communication, portail ; préparer attestations et lettres. Chaque fonction s'exerce sur son
compte, en parallèle, après une partie commune.

**Comptes** : les sept `co.*`, `presidence` (publication du programme), `signataire`,
`intervenant`, `participant1`, `participant2`, `auteur1`, `auteur2`.

**Préparation** (après l'atelier 1, ou rejouée par le formateur) :

1. Au moins deux communications acceptées ; leurs auteurs déposent la version finale et
   « Confirmer ma présentation » (voir le cahier de recette, démo F).
2. `participant1` et `participant2` prennent connaissance de la notice (pays du profil
   renseigné par la démonstration : tarif international).
3. `backup_db`.

**Déroulé** :

- **0:00–0:15** — Rôle et fonctions du CO, ce que chacun voit et ne voit pas (pas
  d'évaluations) ; réauthentification ; portail pré-rendu.
- **0:15–0:35** — Commun : Tableau de bord ; Organisation › Tâches (créer, confier,
  « Déplacer vers ») ; Activité. Voir le cahier de recette, démo I.
- **0:35–1:15** — Programme (`co.programme`, puis `presidence`) : sessions dans les deux
  salles, rôles de séance ; Planificateur (« Placer dans… », flèches) ; provoquer un conflit
  de personne (même président de séance dans deux sessions simultanées, RG-12) et un
  débordement (RG-13), les corriger ; `presidence` publie (réauthentification) ; constater
  que le portail attend sa mise en ligne. Voir le cahier de recette, démo F.
- **1:15–1:30** — Pause.
- **1:30–2:10** — Inscriptions (`co.finances`, `co.secretariat`) : Paramétrage › Tarifs
  (catégorie « Étudiant » avec justificatif, option à quota, code promo) ; `participant1`
  s'inscrit par virement (pro forma) ; « Enregistrer un paiement reçu » (facture) ;
  `participant2` s'inscrit et paie, puis le CO annule son inscription et « Enregistrer un
  remboursement » (avoir) ; `auteur1` commande sans payer (reste en attente) ; Finances,
  Factures et avoirs, export (réauthentification). Voir le cahier de recette, démo G.
- **2:10–2:50** — En parallèle, par fonction (voir le cahier de recette, démos C et I) :
  - `co.logistique` : `intervenant` remplit « Ma venue » ; fiche de venue, repas et
    régimes (`participant1` déclare un régime dans « Régime et annonces ») ;
  - `co.relations` : niveau « Or », partenaire publié sur le portail ;
  - `co.communication` : annonce au bandeau et « M'envoyer un essai » ; questionnaire en
    brouillon ; page personnalisée « Aide » composée avec le texte de
    [aide-portail.md](aide-portail.md) ;
  - `co.benevoles` : postes des bénévoles, affectation de `benevole` ;
  - `co.finances` : budget, lignes calculées.
- **2:50–3:15** — Attestations et lettres (`signataire`, `co.secretariat`) : « Ma
  signature » ; Modèle des attestations (signataire désigné pour chaque nature, lettre
  comprise ; « Aperçu (PDF) ») ;
  `participant1` demande une lettre d'invitation (« Mes documents ») ; « Émettre la
  lettre » ; vérification publique par le QR. Voir le cahier de recette, démo H.
- **3:15–3:30** — Rapports et exports ; demande de mise en ligne du portail
  (`deploy.sh --portal-only`) et vérification du programme, des partenaires et de la page
  « Aide » publiés ; bilan.

**À souligner** : le CO « programme » écrit, le président publie ; un paiement en ligne
n'est valide que confirmé par le prestataire (RG-15) ; une pièce comptable ne se corrige
que par un avoir (RG-14) ; les régimes sont des données sensibles (RG-23) ; un envoi groupé
est étalé et porte un lien de désabonnement (RG-22) ; rien n'est public avant la mise en
ligne du portail.

## 6. Atelier 3 — Bénévoles et accueil

**Objectifs** : installer l'accueil sur son téléphone ; télécharger la liste hors ligne
(valable 48 heures) ; scanner ; travailler sans réseau puis synchroniser ; orienter vers le
comptoir ; tenir le comptoir, les présences et les badges (CO) ; émarger une session.

**Comptes** : `benevole`, `co.benevoles`, `co.secretariat`, `co.logistique`,
`co.programme` ; `participant1`, `participant2`, `auteur1`, `auteur2` (badges sur leur
téléphone ou imprimés).

**Préparation** (après l'atelier 2, voir le cahier de recette, démo H) :

1. Programme publié ; `participant1` confirmé, `participant2` annulé, `auteur1` en attente
   de paiement (atelier 2) ; `auteur2` inscrit et confirmé, puis son badge remplacé
   (Inscriptions › fiche › « Remplacer le badge ») pour disposer d'un ancien badge.
2. `co.benevoles` a affecté `benevole` à un poste « Accueil ».
3. Badges imprimés (Jour J › Badges, à 100 %) ou affichés sur un second écran.
4. Facultatif : rôle « Président de session » attribué par l'exploitant (`grant_role`) à
   un compte fictif désigné président d'une session publiée (à vérifier en préparation).
5. `backup_db`.

**Déroulé** :

- **0:00–0:15** — Rôle du bénévole, ce qu'il voit (Accueil (scan), Sessions du jour, Mon
  planning) ; le QR est un titre d'accès ; double authentification.
- **0:15–0:40** — Sur le téléphone : connexion avec le code ; Jour J › Mon planning et
  iCal ; Accueil (scan), « Ajouter à l'écran d'accueil » ; « Réglages du poste ».
- **0:40–1:20** — En ligne : « Télécharger la liste hors ligne » ; « Allumer la caméra » ;
  scanner un badge confirmé (Pointé), le même (Déjà pointé), l'inscription en attente
  (comptoir), l'annulée, l'ancien badge remplacé (refus).
- **1:20–1:35** — Pause.
- **1:35–2:15** — Sans réseau (mode avion) : scanner, voir la file d'attente ; réseau
  rétabli, « Synchroniser » ; lire les « Refusés à la synchronisation ». Déconnexion avec
  des pointages en attente : l'avertissement.
- **2:15–2:45** — CO : Jour J › Comptoir (adresse `@fictif.invalid`, « Paiement reçu au
  comptoir », « Imprimer le badge ») ; Présences (« Annuler le pointage », export
  réauthentifié) ; saisie manuelle d'une référence ; badge perdu.
- **2:45–3:10** — Sessions du jour : « Émarger l'entrée » ; « Marquer présentée » et sa
  correction (`co.programme`).
- **3:10–3:25** — Après : `co.secretariat` émet les attestations de participation et de
  communication (RG-16) ; l'émission passe par la file de tâches (`run_jobs`, toutes les
  5 minutes) ; `participant1` télécharge la sienne dans « Mes documents » ; vérification
  publique par le QR.
- **3:25–3:30** — Bilan ; consignes du jour J (se connecter en ligne le matin, liste du
  jour, synchroniser avant de se déconnecter).

**À souligner** : synchroniser avant de se déconnecter ; une personne refusée va au
comptoir, jamais d'entrée « à vue » ; ne pas photographier les badges des participants ni
laisser traîner planches et fichiers ;
la présence enregistrée ouvre droit à l'attestation (RG-16) ; tester l'accueil sur les
téléphones réels de l'équipe (iOS et Android), réseau coupé, avant le jour J.

## 7. Après les ateliers

- Recueillir les questions et les difficultés : une question récurrente appelle une
  correction de fiche d'aide ou de guide ; une demande de fonction est notée pour un lot
  ultérieur (S15).
- Avant toute donnée réelle, l'exploitant restaure la sauvegarde prise avant `seed_demo`
  dans une base neuve (D18) : il n'existe pas de commande de purge de la démonstration, qui
  supprimerait des pièces comptables et le journal.
