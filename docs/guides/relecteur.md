# Guide — Relecteur

Pour les **membres du comité scientifique** qui évaluent les soumissions (rôle « Membre du
comité scientifique », `SC_MEMBER`) ; il vaut aussi pour le président du comité quand il
évalue. Adresses relatives à `/gestion/editions/<n°>/` ; conventions dans le
[README](README.md).

## 1. Ce que vous voyez, et ce que vous ne voyez pas

- Dans la gestion, la seule rubrique **Évaluation** : « Mes évaluations » et « Mes
  expertises », plus l'aide. Vous arrivez directement sur « Mes évaluations ».
- Vous ne voyez que les soumissions qui vous sont **affectées**, une fois l'évaluation
  ouverte par le président du comité (RG-03).
- **Double aveugle (RG-04)**, réglage de l'édition actif par défaut : le serveur ne vous
  transmet jamais le nom, l'adresse, l'affiliation des auteurs ni les métadonnées de leur
  fichier. Ce n'est pas un masquage à l'écran : l'information ne vous parvient pas. Si
  l'édition n'est pas en double aveugle, le formulaire affiche les auteurs.
- Les autres relecteurs ne vous connaissent que par un pseudonyme (« Relecteur 1 »…), et
  vous ne connaissez d'eux que le leur.

## 2. Premier accès

1. Ouvrir le lien de l'e-mail d'invitation (valable 14 jours) ; se connecter, ou créer son
   compte, **avec l'adresse invitée** ; « Accepter l'invitation ».
2. **Activer la double authentification**, obligatoire : portail, `/compte/securite` ›
   « Activer la double authentification » ; scanner le QR code avec une application
   (FreeOTP, Aegis, Google Authenticator…), saisir le code, **conserver les codes de
   secours**.
3. Ensuite, à chaque connexion : `/compte/connexion`, mot de passe, puis code à 6 chiffres ;
   « Accéder à l'espace de gestion » (ou `/gestion/`).
4. **Évaluation › Mes expertises** (`expertises`) : cochez vos thématiques de compétence,
   « Enregistrer ». Elles guident le président dans les affectations.

## 3. Évaluer une soumission

1. **Évaluation › Mes évaluations** (`evaluations`) : échéance et état de chacune
   (à faire, brouillon, envoyée, close). Un e-mail vous prévient à l'ouverture.
2. **Lire** : résumé, mots-clés, « Télécharger le PDF ». En double aveugle, le PDF a été
   nettoyé de ses métadonnées et porte la référence de la soumission.
3. **Noter** chaque critère sur l'échelle de la grille ; la « Note pondérée indicative »
   s'affiche pendant la saisie (le serveur la recalcule et fait foi). Un critère facultatif
   non noté est exclu du calcul.
4. Renseigner :
   - **Recommandation** : accepter, accepter avec corrections, rejeter, discuter ;
   - **Confiance** : de 1 (faible) à 5 (experte) ;
   - **Commentaire aux auteurs** : obligatoire à l'envoi, transmis aux auteurs sous
     pseudonyme avec la décision ;
   - **Commentaire confidentiel au comité** : jamais transmis aux auteurs ;
   - cases « Signalement d'éthique » et « Plagiat présumé » si besoin.
5. « **Enregistrer le brouillon** » à tout moment : rien n'est transmis tant que vous
   n'avez pas envoyé.

## 4. Envoyer, puis renvoyer (RG-06)

- « **Envoyer l'évaluation** », puis « Envoyer » dans la confirmation. L'envoi exige tous
  les critères obligatoires, la recommandation, la confiance et le commentaire aux auteurs.
- Jusqu'à la décision, vous pouvez corriger et « **Renvoyer l'évaluation modifiée** » :
  chaque envoi est une nouvelle version, la précédente reste dans l'historique.
- Dès qu'une décision est enregistrée, l'évaluation n'est plus modifiable (« Cette
  évaluation n'est plus modifiable ») ; elle reste consultable.

## 5. Discussion (RG-08)

- Vous ne lisez les autres évaluations qu'**après avoir envoyé la vôtre** et une fois la
  discussion **ouverte** : d'elle-même quand toutes les évaluations sont envoyées, ou plus
  tôt par le président (par exemple sur une divergence). Avant, l'écran affiche « La
  discussion n'est pas encore ouverte ».
- Le bloc « Discussion » donne la note finale et l'écart entre évaluations, les autres
  évaluations sous pseudonyme et les messages ; « Votre message » › « Publier ».
- Si la discussion vous convainc, modifiez votre évaluation et renvoyez-la (§ 4).

## 6. Décliner, déclarer un conflit (RG-03)

- En bas de l'évaluation, « **Décliner…** » : motif, et case « Je déclare un conflit
  d'intérêts avec cette soumission » si c'est le cas ; « Décliner », puis confirmer.
- L'affectation prend fin et vous ne voyez plus la soumission ; le président désigne un
  remplaçant. Une évaluation **déjà envoyée ne se décline plus**.
- Recommandation : si, malgré l'anonymat, vous pensez reconnaître les auteurs (travail
  d'un proche, de votre équipe), déclinez en déclarant le conflit plutôt que d'évaluer.

## 7. Échéances et relances

- L'échéance figure dans la liste ; le président peut la modifier.
- Relances automatiques par e-mail : sept jours et un jour avant l'échéance, puis après,
  une fois chacune.

## 8. Bonnes pratiques

- Les travaux sont inédits : ne diffusez ni le PDF ni le résumé, supprimez le fichier
  téléchargé une fois l'évaluation faite.
- Rédigez le commentaire aux auteurs pour eux : constructif, sans élément qui vous
  identifie. Ce qui ne doit pas leur parvenir va dans le commentaire confidentiel.
- Ne quittez pas une session ouverte sur un poste partagé : « Se déconnecter ».

## 9. Après la conférence

Si l'édition délivre des attestations d'évaluation, la vôtre se télécharge dans le
portail, « Mes documents » (`/compte/mes-documents`) ; elle indique seulement le nombre
d'évaluations envoyées, jamais les titres.

## Fiches d'aide liées

- `my-reviews` — Mes évaluations (fiche unique des écrans « Mes évaluations » et « Mes
  expertises », seule fiche de l'index du profil relecteur)
- `first-steps` — Premiers pas dans la gestion (fiche générale, lisible dans
  Aide › Guide)
- `security` — Double authentification et confirmation d'identité (idem)
