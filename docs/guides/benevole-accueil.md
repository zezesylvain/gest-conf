# Guide — Bénévole et accueil du jour J

Pour les **bénévoles** (rôle « Bénévole », `VOLUNTEER`), les **membres du CO** qui tiennent
l'accueil, le comptoir et les présences, et les **présidents de séance** (rôle « Président
de session », `SESSION_CHAIR`). Adresses relatives à `/gestion/editions/<n°>/` ;
conventions dans le [README](README.md).

## 1. Qui fait quoi le jour J

| Rôle | Écrans (rubrique Jour J) |
|---|---|
| Bénévole | Accueil (scan), Sessions du jour (émargement), Mon planning |
| Tout membre du CO | Accueil (scan), Sessions du jour, Badges |
| CO secrétariat, logistique, bénévoles ; administrateur | en plus : Présences, saisie manuelle d'une référence, remplacement d'un badge |
| CO finances, secrétariat ; administrateur | en plus : Comptoir |
| Président de séance | Sessions du jour, pour ses seules sessions |

Le bénévole n'a **aucun autre droit** : pas de liste des inscriptions, pas de comptoir, pas
de présences. Le **QR du badge est un titre d'accès** : ne photographiez pas les badges des
participants, ne laissez traîner ni planches ni fichiers de badges.

## 2. Avant le jour J (bénévole)

1. Accepter l'invitation (lien de l'e-mail, valable 14 jours), avec l'adresse invitée.
2. **Activer la double authentification**, obligatoire : portail, `/compte/securite` ›
   « Activer la double authentification » ; conserver les codes de secours.
3. **Jour J › Mon planning** (`jour-j/mon-planning`) : vos postes, lieux, horaires à l'heure
   du lieu et consignes ; « Télécharger mon planning (iCal) », à retélécharger après un
   changement. Chaque affectation ou retrait vous est notifié.
4. **Installer l'accueil sur le téléphone** : ouvrir Jour J › Accueil (scan) dans le
   navigateur du téléphone, puis la commande du navigateur « Ajouter à l'écran d'accueil ».
   L'application s'ouvre ensuite sur `/gestion/accueil`, même sans réseau.
5. Autoriser la caméra quand le navigateur le demande. Sans caméra, le bénévole ne peut pas
   saisir la référence à la main : il oriente la personne vers un membre du CO.

## 3. Le matin, avant l'ouverture

1. **En ligne**, se connecter (mot de passe et code). Une session dure 12 heures au plus :
   reconnectez-vous en début de journée plutôt qu'en pleine affluence.
2. Ouvrir **Accueil (scan)** › « Réglages du poste » : Mode (« Accueil de la conférence »
   ou une session du programme publié) et Nom du poste (ex. « entrée principale »), repris
   dans chaque pointage.
3. « **Télécharger la liste hors ligne** » : nom, catégorie et empreinte du badge des
   inscrits confirmés. Elle vaut **48 heures** ; « Mettre à jour la liste » ensuite.
   L'écran indique « En ligne » ou « Hors ligne » et la date de la liste.

## 4. Scanner un badge

« Allumer la caméra », présenter le QR (badge imprimé, ou « Code d'accès » affiché dans
« Mon inscription » sur le téléphone du participant). Le résultat s'affiche et se lit :

| Résultat | Que faire |
|---|---|
| Pointé | Laisser entrer |
| Déjà pointé | Laisser entrer (avertissement, pas une erreur) |
| En attente de paiement : diriger vers le comptoir | Envoyer au comptoir |
| Inscription annulée / expirée | Envoyer au comptoir |
| Badge remplacé : ancien badge refusé | Le participant a reçu un nouveau badge : comptoir |
| Badge inconnu / Badge d'une autre édition | Comptoir |
| Absent de la liste hors ligne : diriger vers le comptoir | Comptoir (hors ligne seulement) |

L'image reste sur le téléphone : seul le texte du QR est envoyé.

## 5. Sans réseau, puis synchroniser

- Sans réseau, l'appareil décide sur la liste téléchargée : « Décidé sans réseau : confirmé
  par le serveur à la synchronisation ». Les pointages sont mis en file (« N pointage(s) en
  attente d'envoi »).
- Au retour du réseau, la file part seule, ou par « **Synchroniser** ». Le serveur revérifie
  chaque pointage ; ceux qu'il refuse s'affichent sous « Refusés à la synchronisation » :
  la personne n'est pas pointée, elle doit passer au comptoir.
- **Sans réseau ni liste** : « Pas de réseau ni de liste hors ligne : impossible de
  vérifier ». Téléchargez la liste chaque matin.
- À vérifier en recette (démo H) : le comportement si la session expire pendant une
  coupure. En attendant, synchronisez dès que le réseau revient.

## 6. Fin de poste

**Synchronisez avant de vous déconnecter** : la déconnexion efface de l'appareil la liste
et les pointages non envoyés. Si des pointages attendent, la fenêtre « Pointages non
synchronisés » le rappelle.

## 7. Entrée des sessions

- **Jour J › Sessions du jour** : les sessions du programme publié. « Émarger l'entrée »
  ouvre l'accueil en mode session : chaque badge lu vaut présence à la session, même sans
  pointage à l'accueil.
- **Président de séance** : il ne voit que ses sessions ; il émarge en ligne (pas de liste
  hors ligne), consulte « Présents » et « Marquer présentée » sur chaque communication
  (son présentateur pourra recevoir une attestation de communication). Il n'a pas besoin
  de double authentification et n'a aucun autre droit. Une erreur se corrige par le CO
  « programme » ou l'administrateur (« Corriger : non présentée », motif).

## 8. Comptoir (CO finances, secrétariat ; administrateur)

**Jour J › Comptoir** (`jour-j/comptoir`) : adresse e-mail, prénom, nom, institution, pays ;
catégorie et options ; « Paiement reçu au comptoir » si la personne règle ; « Inscrire » ;
puis « Imprimer le badge ». Une adresse inconnue crée un compte sans mot de passe (la
personne reçoit un lien pour le définir) ; une adresse connue est rattachée à son compte,
sans le modifier. Une inscription en attente de paiement se règle depuis sa fiche :
Inscriptions › fiche › « Enregistrer un paiement reçu ».

## 9. Présences et badges (CO)

- **Jour J › Présences** (CO secrétariat, logistique, bénévoles ; administrateur) :
  recherche par nom ou référence ; « Annuler le pointage » (motif ; rien n'est supprimé) ;
  « Exporter (CSV) » (réauthentification). Ces mêmes membres peuvent, à l'accueil, saisir la
  « Référence de l'inscription » imprimée sous le QR (ex. `GC27-I00042`) › « Pointer ».
- **Jour J › Badges** (tout le CO) : une catégorie ou toutes › « Préparer les fichiers » ;
  un PDF par lot de 200 badges (planches A4 de quatre badges A6) ; imprimer **à 100 %**,
  sans ajustement à la page. Chaque téléchargement est journalisé.
- **Badge perdu** : Inscriptions › fiche › « Remplacer le badge » (motif) ; l'ancien est
  refusé à l'accueil ; imprimer le nouveau (« Badge (PDF) »).

## 10. Après la conférence

Une présence enregistrée (accueil ou session) ouvre droit à l'attestation de participation
(RG-16), émise par le CO secrétariat (voir [comite-organisation.md](comite-organisation.md),
§ 4). Les questionnaires de satisfaction ne sont proposés qu'aux personnes présentes.

## Fiches d'aide liées

- `first-steps` — Premiers pas dans la gestion
- `security` — Double authentification et confirmation d'identité
- `reception` — Accueil (scan des badges)
- `day-sessions` — Sessions du jour
- `my-shifts` — Mon planning
- `volunteer-shifts` — Postes des bénévoles
- `attendance` — Présences
- `badges` — Badges
- `counter` — Comptoir
- `registrations` — Inscriptions
