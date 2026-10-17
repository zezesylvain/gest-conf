# Guide — Comité scientifique (présidence)

Pour le **président du comité scientifique** (rôle « Président du comité scientifique »,
`SC_CHAIR`). Le président de la conférence dispose des mêmes écrans de pilotage, de décision
et de publication des résultats. Pour évaluer vous-même, voir [relecteur.md](relecteur.md).
Adresses relatives à `/gestion/editions/<n°>/` ; conventions dans le [README](README.md).

## 1. Ce que vous voyez

- Rubriques : Pilotage (tableau de bord), Soumissions, Évaluation (Mes évaluations, Mes
  expertises, Pilotage de l'évaluation, Classement et décisions), Programme (lecture),
  Rapports, Paramétrage (lecture, sauf les grilles), Comités (membres du comité
  scientifique seulement).
- Double authentification facultative mais recommandée (obligatoire si l'exploitant
  l'impose) ; certaines opérations redemandent votre mot de
  passe (voir [presidence-administration.md](presidence-administration.md), § 2).
- Vous voyez l'**identité des auteurs** (Soumissions, fiche complète), nécessaire pour juger
  des conflits d'intérêts. Les relecteurs ne la reçoivent jamais en double aveugle (RG-04) :
  ne la leur transmettez pas.

## 2. Constituer le comité

1. **Comités › Invitations** › « Inviter des membres », rôle « Membre du comité
   scientifique » (le seul que vous puissiez attribuer) ; suivre, « Relancer »,
   « Annuler l'invitation ».
2. **Comités › Membres** : les membres du comité scientifique ; « Retirer le rôle »
   (motif, réauthentification).
3. Demandez à chaque relecteur de déclarer ses thématiques dans Évaluation › **Mes
   expertises** : elles s'affichent lors des affectations.

## 3. Préparer la grille (RG-05)

- **Paramétrage › Grilles d'évaluation** › « Créer la grille » : elle reprend la grille par
  défaut de l'étude (25 / 30 / 15 / 15 / 15, notes de 0 à 5). Une grille par édition, et au
  besoin une par type de communication.
- Pour chaque critère : code, libellés FR et EN, poids, obligatoire ou non ;
  « Ajouter un critère », puis « Enregistrer la grille ». **La somme des poids vaut
  exactement 100**, sinon l'enregistrement est refusé.
- Dès la première évaluation enregistrée, la grille est **verrouillée** : « Dupliquer en
  nouvelle version » pour la changer ; les évaluations déjà faites gardent leur version.
- Paramétrage › Confidentialité (double aveugle, relecteurs par soumission, charge
  maximale, seuil de divergence, note finale) : lecture seule pour vous ; modifié par
  l'administrateur ou le président de la conférence.

## 4. Pendant l'appel

- **Soumissions** : filtres (états, thématique, type, langue), recherche, détail (auteurs,
  versions du PDF, déclarations, historique), « Exporter (CSV) » (journalisé), filtre
  « Doublons possibles ».
- Après la clôture, **dérogation** (RG-02), par exemple pour un auteur dont le brouillon a
  été interrompu par la clôture : fiche de la soumission › Dérogations › échéance et motif ›
  « Accorder la dérogation » ; l'auteur est prévenu ; « Révoquer » à tout moment. Une
  soumission déjà passée en recevabilité n'en reçoit plus.

## 5. Recevabilité et affectations

À la clôture de l'appel, les soumissions passent d'elles-mêmes en recevabilité, dans
l'heure (cron `close_call`).

1. **Évaluation › Pilotage de l'évaluation** : filtres « Relecteurs requis non affectés » et
   « Évaluations en retard » ; ouvrez une soumission.
2. **Affecter** : bloc « Relecteurs disponibles » (charge, institution, expertises,
   conflits) › « Affecter… », échéance facultative (par défaut la fin des évaluations).
   Au-delà de la charge maximale, l'affectation est refusée.
3. **Recevabilité** : une fois les relecteurs requis affectés, « Recevable : ouvrir
   l'évaluation » (les relecteurs sont prévenus par e-mail), ou « Non recevable : rejeter »
   avec un motif transmis à l'auteur (définitif).

## 6. Conflits d'intérêts (RG-03)

- Un relecteur **auteur** de la soumission ne peut jamais l'évaluer.
- **Même institution** ou conflit **déclaré** : levée possible avec un motif, journalisée,
  après confirmation de votre identité.
- Déclarer un conflit pour un relecteur : « Conflit… » dans la liste des relecteurs
  disponibles ; une affectation éventuelle est annulée.
- Un relecteur peut décliner en déclarant un conflit : désignez un remplaçant.

## 7. Suivre l'évaluation

- Bloc « Avancement » : charge de chaque relecteur, retards, soumissions **divergentes**
  (écart au-delà du seuil de l'édition, signalé aussi par e-mail).
- Relances automatiques des relecteurs : sept jours et un jour avant l'échéance, puis après.
- Affectation : « Échéance… » (les relances repartent de zéro), « Annuler… » (motif).
- **Discussion** (RG-08) : elle s'ouvre seule quand toutes les évaluations sont envoyées ;
  « Ouvrir la discussion » plus tôt, notamment sur une divergence. Vous y écrivez comme
  « Président du comité » ; les relecteurs n'y sont connus que par pseudonyme.

## 8. Décider (RG-07, RG-09)

- Une soumission devient « évaluée » quand le nombre requis de relecteurs a envoyé son
  évaluation (RG-07).
- **Décision individuelle** : fiche de la soumission › Décision › Issue (acceptée,
  acceptée sous réserve de corrections, liste d'attente, rejetée), Format attribué, Message
  du comité aux auteurs › « Enregistrer la décision ». Elle reste **provisoire**, invisible
  des auteurs ; « Annuler la décision » la retire. Après une décision, les évaluations ne
  se modifient plus.
- **Évaluation › Classement et décisions** : soumissions évaluées par note finale, avec
  divergence et recommandations.
  1. « Simulation de seuil » › « Simuler » : retenues au total, par type, par thématique.
  2. « Préparer les décisions selon le seuil », ajuster ligne à ligne, puis « Enregistrer
     les décisions (N) » (tout ou rien) : décisions provisoires.
  3. « **Publier les résultats (N)** » : confirmation d'identité ; les statuts changent et
     les auteurs sont prévenus. **Irréversible.**
- Les auteurs reçoivent la décision, le format, votre message et les commentaires des
  relecteurs sous pseudonyme (« Relecteur 1 »…) ; **jamais** leurs noms, leurs notes ni les
  commentaires confidentiels (RG-10).
- **Liste d'attente** : fiche de la soumission › « Accepter depuis la liste d'attente » ;
  les auteurs sont prévenus aussitôt.
- « Exporter les évaluations (CSV) » : une ligne par évaluation, **avec le nom du
  relecteur** ; réauthentification, journal (RG-17). Fichier à protéger.

## 9. Après les décisions

- Les auteurs déposent la version finale puis confirment leur présentation ; le programme
  est construit par le CO « programme » et publié par le président de la conférence
  (Programme, en lecture pour vous).
- Rapports : sections soumissions et relecture, chiffres agrégés, exports journalisés.
- Attestations d'évaluation (si l'édition les active) : émises par le comité après la
  conférence ; elles ne portent que le nombre d'évaluations.

## 10. Ce que vous ne faites pas

Modifier le paramétrage de l'édition (hors grilles), inviter d'autres rôles que les
relecteurs, écrire ou publier le programme, accéder aux inscriptions, aux finances, au
jour J ou au journal.

## Fiches d'aide liées

- `first-steps` — Premiers pas dans la gestion
- `security` — Double authentification et confirmation d'identité
- `roles` — Rôles et droits
- `dashboard` — Tableau de bord
- `members` — Membres
- `invitations` — Invitations
- `grids` — Grilles d'évaluation
- `settings-confidentiality` — Confidentialité et paramètres de l'évaluation
- `submissions` — Soumissions
- `review-follow-up` — Pilotage de l'évaluation
- `ranking` — Classement et décisions
- `my-reviews` — Mes évaluations
- `program-planner` — Planificateur du programme
- `reports` — Rapports
