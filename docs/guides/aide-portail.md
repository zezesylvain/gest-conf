# Aide du portail — texte proposé

**Statut : proposition** (plan L9, décision S11), à relire et valider par le commanditaire
avant publication. Le texte ne décrit que ce que la plateforme fait au 12 octobre 2026
(portail `/fr/…`, `/en/…` et espace personnel `/compte/…`) ; il est à revoir à chaque
évolution des écrans du portail. Il s'adresse aux auteurs, aux participants et aux
intervenants invités ; les membres des comités ont l'aide intégrée de la gestion.

## 1. Mode d'emploi pour les organisateurs

La page « Aide » est une **page personnalisée** du CMS (L2), composée de cinq sections de type
« Texte riche ». Chaque section porte le texte français **et** le texte anglais : le bloc
français ci-dessous va dans le champ « Texte » français de la section, le bloc anglais de
même numéro dans le champ anglais.

1. **Sections** : Portail › Sections › « Ajouter une section », type « Texte riche », codes
   proposés `aide-compte`, `aide-soumission`, `aide-decision`, `aide-inscription`,
   `aide-apres`. Titre FR et EN : les titres des sections ci-dessous. Coller les blocs HTML,
   puis « Aperçu » pour vérifier le rendu.
2. **Page** : Portail › Pages › « Ajouter une page », identifiant `aide` (adresses
   `/fr/p/aide/` et `/en/p/aide/`), titres « Aide » et « Help », descriptions courtes ;
   « Créer et composer ». Poser les cinq sections dans l'ordre (« Poser à la fin »), cocher
   « Publiée ».
3. **Menu** : Portail › Menus › « Ajouter une entrée » (en-tête ou pied de page), libellés
   « Aide » et « Help », destination : la page `aide`.
4. **Mise en ligne** : la page n'apparaît qu'à la mise en ligne suivante du portail, faite
   par l'exploitant (`deploy/deploy.sh --portal-only`).

Contraintes du CMS (assainissement au serveur et au rendu) :

- balises gardées : `p`, `br`, `strong`, `em`, `ul`, `ol`, `li`, `a`, `h3`, `h4`,
  `blockquote` ; tout le reste (tableaux, images, `h1`, `h2`, styles) est retiré ;
- liens : `https:`, `mailto:`, `tel:` ou adresse du portail commençant par `/` ;
- 20 000 caractères au plus par texte (chaque bloc ci-dessous en est loin).

À adapter avant publication :

- `[CONTACT]` : à remplacer par l'adresse du comité d'organisation, par exemple
  `<a href="mailto:contact@exemple.org">contact@exemple.org</a>` (aucun formulaire de contact
  n'existe sur le portail) ;
- les paragraphes et éléments de liste qui commencent par une mention entre crochets en
  majuscules (`[SI …]`, laissée en français dans les deux langues) dépendent du paramétrage
  de l'édition : garder le passage sans la mention si la condition est remplie, sinon le
  supprimer en entier :
  - `[SI DOUBLE AVEUGLE]` : Paramétrage › Confidentialité ;
  - `[SI INSCRIPTION DES PRÉSENTATEURS EXIGÉE]` : Paramétrage › Programme (RG-11) ;
  - `[SI PAIEMENT EN LIGNE]` : seulement si un prestataire de paiement est configuré (Q7) ;
  - `[SI ATTESTATIONS D'ÉVALUATION]` : Attestations et lettres › Modèle des attestations ;
- les adresses publiques des blocs français (`/fr/appel`, `/fr/inscription`,
  `/fr/programme`) ont leur équivalent anglais dans les blocs anglais ; l'espace personnel
  (`/compte/…`) et la vérification (`/verification`) n'ont qu'une adresse.

## 2. Texte français

### Section 1 — « Votre compte » (`aide-compte`)

```html
<h3>Comment créer mon compte ?</h3>
<p>En haut de page, « Connexion », puis « Créer un compte »
(<a href="/compte/inscription">création de compte</a>). Un seul compte sert à soumettre une
communication, à vous inscrire et à retrouver vos documents. Le mot de passe compte au moins
12 caractères et ne doit pas être un mot de passe courant.</p>
<h3>Je n'ai pas reçu l'e-mail de vérification.</h3>
<p>Votre adresse doit être vérifiée avant la première connexion. Les e-mails partent en
différé : comptez quelques minutes et regardez dans vos courriers indésirables. Sinon,
essayez de vous connecter : un nouveau lien vous est envoyé (au plus un toutes les trois
minutes).</p>
<h3>J'ai oublié mon mot de passe.</h3>
<p>Sur la page de connexion, « Mot de passe oublié ? » : indiquez l'adresse de votre compte.
Vous recevez un lien, valable deux heures, pour choisir un nouveau mot de passe.</p>
<h3>Que faire à la première connexion ?</h3>
<p>Prenez connaissance de la notice d'information sur vos données, puis complétez votre
« Profil » : nom, prénom, institution et pays sont nécessaires pour soumettre, et le pays
détermine votre tarif d'inscription (local ou international). La langue choisie en haut de
page est enregistrée dans votre compte ; elle sert aussi aux e-mails.</p>
<h3>Dois-je activer la double authentification ?</h3>
<p>Elle est <strong>obligatoire pour les membres des comités</strong> et les autres rôles
d'organisation de la conférence (présidence, comités scientifique et d'organisation,
bénévoles, signataire) : sans elle, l'espace de gestion leur est refusé. Elle est facultative
pour les auteurs et les participants.</p>
<p>Pour l'activer : « Sécurité » › « Activer la double authentification » ; scannez le QR
code avec une application d'authentification (FreeOTP, Aegis, Google Authenticator…),
saisissez le code affiché, puis conservez vos codes de secours en lieu sûr. Le code à six
chiffres de l'application vous est ensuite demandé à chaque connexion.</p>
<h3>J'ai perdu mon téléphone.</h3>
<p>Connectez-vous avec l'un de vos codes de secours (chacun ne sert qu'une fois), puis, dans
« Sécurité », désactivez et réactivez la double authentification avec votre nouveau
téléphone. Sans code de secours, écrivez au comité d'organisation ([CONTACT]) : la
réinitialisation est faite par l'exploitant de la plateforme, après vérification de votre
identité.</p>
<h3>J'ai été invité à rejoindre un comité.</h3>
<p>Ouvrez le lien de l'e-mail d'invitation (valable 14 jours), connectez-vous, ou créez
votre compte, avec l'adresse à laquelle l'invitation a été envoyée, puis « Accepter
l'invitation ». Le lien seul ne donne aucun rôle. Activez ensuite la double
authentification (« Sécurité ») ; l'espace de gestion s'ouvre depuis « Mon compte » ›
« Accéder à l'espace de gestion ».</p>
<h3>Où trouver les messages de la plateforme ?</h3>
<p>Dans votre espace, « Notifications » (la cloche) : accusés de réception, décisions,
annonces, questionnaires… Les e-mails correspondants partent en différé, quelques minutes
plus tard.</p>
```

### Section 2 — « Soumettre une communication » (`aide-soumission`)

```html
<h3>Comment soumettre une communication ?</h3>
<p>Pendant l'appel à communications : « Mon compte » › « Mes soumissions » › « Nouvelle
soumission ». L'assistant compte cinq étapes : Informations, Auteurs, Fichier, Déclarations
et Récapitulatif. Le récapitulatif indique ce qui manque ; « Soumettre » n'est possible que
lorsque tout est complet. Vous recevez alors un accusé de réception par e-mail, avec la
référence de votre soumission. Formats, échéances et modèles de documents : page
<a href="/fr/appel">Appel à communications</a>.</p>
<h3>Mon brouillon est-il enregistré ?</h3>
<p>Oui : les informations et les déclarations s'enregistrent automatiquement pendant la
saisie ; les auteurs, par « Enregistrer les auteurs ». Vous pouvez quitter la page et
reprendre plus tard. Si la soumission a été modifiée dans un autre onglet ou sur un autre
appareil, un message vous demande de la recharger. Un brouillon n'est pas une soumission :
il ne sera pas évalué. Un rappel vous est envoyé avant la clôture si votre brouillon n'est
pas soumis.</p>
<h3>Comment indiquer mes co-auteurs ?</h3>
<p>À l'étape « Auteurs », indiquez tous les auteurs dans l'ordre de publication, vous
compris, avec leur adresse e-mail ; cochez au moins un « Auteur correspondant » et, si vous
le savez, qui « Présentera la communication ». « Monter » et « Descendre » changent l'ordre.
Les co-auteurs reçoivent un e-mail quand la soumission est envoyée ; seul l'auteur qui l'a
créée peut la modifier et la suivre.</p>
<h3>Quel fichier déposer ?</h3>
<p>Un PDF, selon le type de communication : aucun, facultatif ou obligatoire, avec la taille
maximale indiquée à l'étape « Fichier ». Le type du fichier est contrôlé d'après son
contenu.</p>
<p>[SI DOUBLE AVEUGLE] L'évaluation est en double aveugle : retirez de votre fichier vos noms,
affiliations et remerciements. Les métadonnées du PDF (auteur, logiciel) sont supprimées au
dépôt.</p>
<h3>Quelles déclarations dois-je accepter ?</h3>
<p>À l'étape « Déclarations » : originalité du travail, respect des règles d'éthique,
déclaration des conflits d'intérêts et accord pour la publication du résumé dans le
programme et les actes en cas d'acceptation. Si leur texte change, une nouvelle acceptation
vous sera demandée.</p>
<h3>Puis-je modifier ma soumission après l'avoir envoyée ?</h3>
<p>Oui, jusqu'à la clôture de l'appel (« modifiable jusqu'au … ») ; chaque version
enregistrée après l'envoi est conservée dans l'historique. Après la clôture, toute
modification est refusée, sauf délai supplémentaire accordé par le comité, dont vous êtes
informé par e-mail.</p>
<h3>Puis-je retirer ma soumission ?</h3>
<p>Ouvrez-la dans « Mes soumissions » › « Retirer la soumission », avec un motif. Le retrait
est possible après l'envoi et jusqu'à la clôture de l'appel, puis, si la communication est
acceptée, jusqu'à sa programmation (une communication « acceptée sous réserve de
corrections » se retire après le dépôt de sa version finale). Il n'est pas proposé pendant la
vérification de recevabilité et l'évaluation : écrivez alors au comité ([CONTACT]). Un
brouillon, lui, se supprime (« Supprimer le brouillon »).</p>
```

### Section 3 — « Décision, version finale et présentation » (`aide-decision`)

```html
<h3>Quand vais-je connaître la décision ?</h3>
<p>Après la clôture de l'appel, votre soumission passe en « Vérification de recevabilité »,
puis « En cours d'évaluation » ; son état est affiché dans « Mes soumissions ». La décision
n'est visible qu'à la publication des résultats par le comité scientifique : vous en êtes
prévenu par e-mail et par une notification. Une soumission jugée non recevable n'est pas
évaluée ; le motif vous est transmis.</p>
<h3>Que contient la décision ?</h3>
<p>La décision (acceptée, acceptée sous réserve de corrections, liste d'attente, non
retenue), le format attribué, le message éventuel du comité et les commentaires des
relecteurs, présentés sous les pseudonymes « Relecteur 1 », « Relecteur 2 »… Vous ne recevez
jamais l'identité des relecteurs, leurs notes ni leurs commentaires confidentiels au comité.
En liste d'attente, un e-mail vous prévient si une place se libère.</p>
<h3>Comment déposer la version finale ?</h3>
<p>Si votre communication est acceptée, ouvrez-la dans « Mes soumissions » : la partie
« Version finale » indique la date limite. Déposez le PDF de la version nominative (noms et
affiliations des auteurs) ; un nouveau dépôt remplace le précédent jusqu'à la date limite.
Pour une acceptation sous réserve de corrections, la « Lettre de réponse aux relecteurs »
est obligatoire : indiquez comment chaque commentaire a été pris en compte.</p>
<h3>Comment confirmer ma présentation ?</h3>
<p>Après le dépôt de la version finale, partie « Présentation » : désignez, parmi les
auteurs, qui présentera la communication, puis « Confirmer ma présentation ». La
communication ne peut être programmée qu'après cette confirmation. Vous pouvez ensuite
changer les présentateurs (« Mettre à jour les présentateurs »).</p>
<p>[SI INSCRIPTION DES PRÉSENTATEURS EXIGÉE] Au moins un présentateur doit avoir une
inscription confirmée pour que la communication figure au programme.</p>
<h3>Où trouver l'horaire de mon passage ?</h3>
<p>Dès la publication du programme, « Mon passage » donne pour chaque présentation la date,
l'heure (heure locale de la conférence), la salle, la durée, les autres intervenants et les
consignes de la session. « Ajouter à mon agenda (.ics) » télécharge un fichier lisible par
la plupart des agendas ; téléchargez-le de nouveau après un changement. Un co-auteur
présentateur y trouve aussi son passage si son compte porte, vérifiée, l'adresse indiquée
dans la soumission. Si votre passage change, vous recevez un e-mail. Le
<a href="/fr/programme">programme public</a> peut être mis à jour avec un léger décalage.</p>
```

### Section 4 — « Inscription, paiement et accueil » (`aide-inscription`)

```html
<h3>Comment m'inscrire à la conférence ?</h3>
<p>Catégories, tarifs, options et moyens de paiement sont présentés sur la page
<a href="/fr/inscription">Inscription</a>. L'inscription se fait depuis votre compte, « Mon
inscription » : choisissez la catégorie, les options éventuelles et, le cas échéant, un
code promo, puis « Calculer le prix » et « Confirmer la commande ». Le prix dépend de la date
de la commande (tarif préférentiel ou normal) et du pays de votre profil (tarif local ou
international) ; il est calculé par la plateforme et ne change plus une fois la commande
passée. Si votre catégorie demande un justificatif (carte d'étudiant…), déposez-le après la
commande (« Déposer le justificatif » : PDF, JPEG ou PNG, 5 Mo au plus).</p>
<h3>Comment payer ?</h3>
<ul>
<li><strong>Virement</strong> : une facture pro forma vous est remise (sinon, « Obtenir une
facture pro forma ») ; rappelez la référence de votre inscription dans le virement. Le
comité confirme l'inscription à réception.</li>
<li><strong>Sur place</strong> : règlement au comptoir de la conférence ; votre inscription
reste en attente de paiement jusque-là.</li>
<li>[SI PAIEMENT EN LIGNE] <strong>En ligne</strong> : « Payer en ligne » vous dirige vers
la page sécurisée du prestataire de paiement. Aucune donnée de carte n'est saisie sur ce
site. L'inscription est confirmée quand le prestataire a confirmé le paiement, ce qui peut
prendre quelques minutes ; vous recevez alors un e-mail.</li>
</ul>
<p>Une commande non réglée dans le délai affiché dans « Mon inscription » expire : les
places réservées sont libérées.</p>
<h3>Où trouver ma facture ?</h3>
<p>Dans « Mon inscription », partie « Documents » : la facture est émise à la confirmation
d'une inscription payante, un avoir en cas de remboursement. La facture pro forma ne vaut pas
facture. Le nom et l'organisme à facturer se modifient dans « Facturation » › « Modifier »,
tant que la facture n'est pas émise.</p>
<h3>Puis-je annuler mon inscription ?</h3>
<p>« Mon inscription » › « Annuler mon inscription », jusqu'à la date limite d'annulation
affichée ; la part remboursée est indiquée avant votre confirmation. Une commande en attente
de paiement s'annule sans frais. Après la date limite, écrivez au comité ([CONTACT]). Le
remboursement est effectué par le comité ; un avoir est alors émis.</p>
<h3>Où est mon badge ?</h3>
<p>Dès que votre inscription est confirmée : « Mes documents » › « Télécharger mon badge » ;
le code QR d'accès est aussi affiché dans « Mon inscription » (« Code d'accès »). Imprimez
votre badge ou gardez-le sur votre téléphone, et présentez le QR à l'accueil. Ce QR est
votre titre d'accès : ne le partagez pas. En cas de perte, présentez-vous au comptoir : un
nouveau badge vous est remis et l'ancien ne fonctionne plus. Une inscription en attente de
paiement est dirigée vers le comptoir.</p>
<h3>J'ai besoin d'une lettre d'invitation pour mon visa.</h3>
<p>Une inscription en cours est nécessaire. « Mes documents » › « Demander une lettre
d'invitation » : nom exactement comme sur le passeport, nationalité, numéro de passeport,
dates d'arrivée et de départ (séjour de 90 jours au plus), ambassade ou consulat. Le comité
examine la demande et vous prévient par e-mail. La lettre signée se télécharge dans « Mes
documents » et se vérifie par son code QR. Elle facilite votre demande de visa mais n'engage
pas l'organisation à prendre en charge vos frais. Votre numéro de passeport n'est transmis
qu'au comité et il est effacé après la conférence. En cas de refus, le motif est affiché et
vous pouvez faire une nouvelle demande.</p>
<h3>Comment signaler un régime alimentaire ou une allergie ?</h3>
<p>« Régime et annonces » : pour chaque conférence où vous êtes inscrit ou membre d'un
comité, indiquez un régime ou une allergie et cochez la case de consentement. Le traiteur ne
reçoit que des effectifs, sans nom. Vous pouvez retirer votre déclaration à tout moment ;
elle est effacée 30 jours après la conférence.</p>
<h3>Intervenant invité : où indiquer mes besoins et mon voyage ?</h3>
<p>« Ma venue », réservée aux intervenants invités : besoins techniques, arrivée, départ,
moyen de transport, besoin d'hébergement ou de transfert, message au comité. Vous y voyez
aussi ce que le comité a organisé pour vous (hôtel, nuits, prise en charge).</p>
```

### Section 5 — « Après la conférence et données personnelles » (`aide-apres`)

```html
<h3>Comment obtenir mon attestation ?</h3>
<p>Le comité émet les attestations après la conférence et vous prévient par e-mail ; elles
se téléchargent dans « Mes documents » › « Attestations ». L'attestation de participation
exige que votre présence ait été enregistrée (badge lu à l'accueil ou à l'entrée d'une
session) ; l'attestation de communication, que votre communication ait été présentée.</p>
<p>[SI ATTESTATIONS D'ÉVALUATION] Les relecteurs reçoivent une attestation d'évaluation, qui
indique seulement le nombre d'évaluations.</p>
<h3>Comment vérifier une attestation ou une lettre ?</h3>
<p>Chaque attestation et chaque lettre porte un code QR qui mène à sa page de vérification.
On peut aussi saisir le code sur la <a href="/verification">page de vérification</a> : c'est
la fin de l'adresse imprimée sous le QR. La page indique si le document est authentique ou
révoqué.</p>
<h3>Le questionnaire de satisfaction est-il anonyme ?</h3>
<p>Oui. Il est proposé aux personnes dont la présence a été enregistrée, par notification et
par e-mail, à son ouverture : « Questionnaires » › « Répondre ». Votre réponse est
enregistrée sans lien avec votre compte, et une seule fois. Les résultats ne sont montrés au
comité qu'à partir de cinq réponses. Les commentaires libres sont lus par le comité : n'y
mettez pas d'information qui vous identifie si vous ne le souhaitez pas.</p>
<h3>Comment ne plus recevoir les annonces ?</h3>
<p>Par le lien de désabonnement présent dans chaque annonce reçue par e-mail, ou dans
« Régime et annonces » (case « Recevoir les annonces de la conférence par e-mail »). Les
e-mails de service (soumission, inscription, documents) et les notifications restent
envoyés.</p>
<h3>Que deviennent mes données personnelles ?</h3>
<ul>
<li>« Mes données » › « Télécharger (JSON) » : votre compte, votre profil, vos adresses, vos
rôles, vos invitations, vos consentements, les e-mails reçus et vos actions des 12 derniers
mois.</li>
<li>« Mes données » › « Anonymiser mon compte » : opération immédiate et définitive ; votre
adresse, votre profil, votre double authentification et vos sessions sont effacés, et vous
ne pouvez plus vous connecter. Le journal des actions et l'historique de vos consentements
sont conservés, sans votre nom ni votre adresse. Si vous avez un rôle actif dans
l'organisation (comité, bénévole…), transmettez-le d'abord.</li>
<li>« Confidentialité » : votre accord pour figurer dans l'annuaire public des comités et
pour la publication de votre photo ; vous pouvez le retirer à tout moment.</li>
<li>Les connexions et actions sensibles sont journalisées pour la sécurité ; l'adresse IP
est effacée au bout de six mois. Le régime alimentaire et le numéro de passeport sont
effacés après la conférence.</li>
<li>Une question sur vos données, ou une question que cette page ne traite pas :
[CONTACT].</li>
</ul>
```

## 3. English text

### Section 1 — “Your account” (`aide-compte`)

```html
<h3>How do I create an account?</h3>
<p>At the top of the page, “Sign in”, then “Create an account”
(<a href="/compte/inscription">account creation</a>). One account lets you submit a paper,
register and find your documents. The password must have at least 12 characters and must
not be a common password.</p>
<h3>I did not receive the verification email.</h3>
<p>Your address must be verified before you first sign in. Emails are sent with a short
delay: allow a few minutes and check your spam folder. Otherwise, try to sign in: a new link
is sent to you (at most one every three minutes).</p>
<h3>I forgot my password.</h3>
<p>On the sign-in page, “Forgot your password?”: enter your account address. You receive a
link, valid for two hours, to choose a new password.</p>
<h3>What should I do when I first sign in?</h3>
<p>Read the privacy notice, then complete your “Profile”: first name, last name, institution
and country are required to submit, and the country sets your registration fee (local or
international). The language chosen at the top of the page is saved in your account; it is
also used for emails.</p>
<h3>Do I need two-factor authentication?</h3>
<p>It is <strong>mandatory for committee members</strong> and the other organising roles of
the conference (chairs, scientific and organising committees, volunteers, signatory): without
it, the management area is refused. It is optional for authors and participants.</p>
<p>To enable it: “Security” › “Enable two-factor authentication”; scan the QR code with an
authenticator app (FreeOTP, Aegis, Google Authenticator…), enter the code it shows, then keep
your recovery codes somewhere safe. The app's six-digit code is then requested at every
sign-in.</p>
<h3>I lost my phone.</h3>
<p>Sign in with one of your recovery codes (each one works only once), then, in “Security”,
disable and enable two-factor authentication again with your new phone. Without a recovery
code, write to the organising committee ([CONTACT]): the platform operator resets it after
checking your identity.</p>
<h3>I was invited to join a committee.</h3>
<p>Open the link in the invitation email (valid for 14 days), sign in, or create your
account, with the address the invitation was sent to, then “Accept the invitation”. The link
alone grants no role. Then enable two-factor authentication (“Security”); the management
area opens from “My account” › “Go to the management area”.</p>
<h3>Where are the platform's messages?</h3>
<p>In your account area, “Notifications” (the bell): acknowledgements, decisions,
announcements, surveys… The matching emails are sent a few minutes later.</p>
```

### Section 2 — “Submitting a paper” (`aide-soumission`)

```html
<h3>How do I submit a paper?</h3>
<p>While the call for papers is open: “My account” › “My submissions” › “New submission”. The
wizard has five steps: Information, Authors, File, Declarations and Summary. The summary
lists what is missing; “Submit” is only possible once everything is complete. You then
receive an acknowledgement by email, with your submission's reference. Formats, deadlines and
templates: <a href="/en/call">Call for papers</a> page.</p>
<h3>Is my draft saved?</h3>
<p>Yes: information and declarations are saved automatically as you type; authors are saved
with “Save authors”. You can leave the page and come back later. If the submission was
changed in another tab or on another device, a message asks you to reload it. A draft is not
a submission: it will not be reviewed. A reminder is sent before the deadline if your draft
has not been submitted.</p>
<h3>How do I add my co-authors?</h3>
<p>At the “Authors” step, list all authors in publication order, including yourself, with
their email address; tick at least one “Corresponding author” and, if you know it, who “Will
present the paper”. “Move up” and “Move down” change the order. Co-authors receive an email
when the submission is sent; only the author who created it can edit and follow it.</p>
<h3>Which file should I upload?</h3>
<p>A PDF, depending on the type of paper: none, optional or required, with the maximum size
shown at the “File” step. The file type is checked from its content.</p>
<p>[SI DOUBLE AVEUGLE] Review is double-blind: remove your names, affiliations and
acknowledgements from your file. PDF metadata (author, software) is removed on upload.</p>
<h3>Which declarations must I accept?</h3>
<p>At the “Declarations” step: originality of the work, compliance with research ethics,
disclosure of conflicts of interest, and consent to publish the abstract in the programme and
proceedings if accepted. If their wording changes, you will be asked to accept them
again.</p>
<h3>Can I edit my submission after sending it?</h3>
<p>Yes, until the call closes (“can be edited until …”); every version saved after sending is
kept in the history. After the deadline, changes are refused, unless the committee grants you
extra time, in which case you are informed by email.</p>
<h3>Can I withdraw my submission?</h3>
<p>Open it in “My submissions” › “Withdraw the submission”, with a reason. Withdrawal is
possible after sending and until the call closes, then, if the paper is accepted, until it is
scheduled (a paper “accepted with minor revisions” can be withdrawn once its final version is
uploaded). It is not offered during the eligibility check and the review: write to the
committee instead ([CONTACT]). A draft is simply deleted (“Delete the draft”).</p>
```

### Section 3 — “Decision, final version and presentation” (`aide-decision`)

```html
<h3>When will I know the decision?</h3>
<p>After the call closes, your submission moves to “Eligibility check”, then “Under review”;
its status is shown in “My submissions”. The decision is visible only once the scientific
committee publishes the results: you are notified by email and by a notification. A
submission found ineligible is not reviewed; you receive the reason.</p>
<h3>What does the decision include?</h3>
<p>The decision (accepted, accepted with minor revisions, waiting list, not accepted), the
assigned format, the committee's message if any, and the reviewers' comments, shown under the
pseudonyms “Reviewer 1”, “Reviewer 2”… You never receive the reviewers' identity, their
scores or their confidential comments to the committee. On the waiting list, an email tells
you if a place becomes available.</p>
<h3>How do I upload the final version?</h3>
<p>If your paper is accepted, open it in “My submissions”: the “Final version” part shows the
deadline. Upload the PDF of the non-anonymous version (authors' names and affiliations); a new
upload replaces the previous one until the deadline. For an acceptance with minor revisions,
the “Response letter to the reviewers” is required: explain how each comment was
addressed.</p>
<h3>How do I confirm my presentation?</h3>
<p>Once the final version is uploaded, in the “Presentation” part: choose which authors will
present the paper, then “Confirm my presentation”. The paper can only be scheduled after this
confirmation. You can change the presenters later (“Update the presenters”).</p>
<p>[SI INSCRIPTION DES PRÉSENTATEURS EXIGÉE] At least one presenter must have a confirmed
registration for the paper to appear in the programme.</p>
<h3>Where is the time of my presentation?</h3>
<p>Once the programme is published, “My schedule” gives, for each presentation, the date, the
time (conference local time), the room, the duration, the other speakers and the session's
instructions. “Add to my calendar (.ics)” downloads a file most calendars can read; download it
again after a change. A co-author who presents also finds their slot there if their account
holds, verified, the address given in the submission. If your slot changes, you receive an
email. The <a href="/en/program">public programme</a> may be updated with a short delay.</p>
```

### Section 4 — “Registration, payment and arrival” (`aide-inscription`)

```html
<h3>How do I register for the conference?</h3>
<p>Categories, fees, options and payment methods are shown on the
<a href="/en/registration">Registration</a> page. You register from your account, “My
registration”: choose the category, any options and, if you have one, a promo code, then
“Calculate the price” and “Confirm the order”. The price depends on the order date (early
bird or regular fee) and on your profile's country (local or international fee); it is
computed by the platform and no longer changes once the order is placed. If your category
requires a proof (student card…), upload it after ordering (“Upload the proof”: PDF, JPEG or
PNG, 5 MB at most).</p>
<h3>How do I pay?</h3>
<ul>
<li><strong>Bank transfer</strong>: a pro forma invoice is issued to you (otherwise, “Get a
pro forma invoice”); quote your registration reference in the transfer. The committee
confirms your registration when the payment arrives.</li>
<li><strong>On site</strong>: payment at the conference desk; your registration remains
awaiting payment until then.</li>
<li>[SI PAIEMENT EN LIGNE] <strong>Online</strong>: “Pay online” takes you to the payment
provider's secure page. No card data is entered on this site. Your registration is confirmed
once the provider has confirmed the payment, which may take a few minutes; you then receive
an email.</li>
</ul>
<p>An order not paid within the time shown in “My registration” expires: the reserved places
are released.</p>
<h3>Where is my invoice?</h3>
<p>In “My registration”, “Documents” part: the invoice is issued when a paid registration is
confirmed, a credit note in case of refund. The pro forma invoice is not an invoice. The
billing name and organisation can be changed in “Billing” › “Edit” until the invoice is
issued.</p>
<h3>Can I cancel my registration?</h3>
<p>“My registration” › “Cancel my registration”, until the cancellation deadline shown; the
refunded share is displayed before you confirm. An order awaiting payment is cancelled free
of charge. After the deadline, write to the committee ([CONTACT]). Refunds are made by the
committee; a credit note is then issued.</p>
<h3>Where is my badge?</h3>
<p>As soon as your registration is confirmed: “My documents” › “Download my badge”; the
access QR code is also shown in “My registration” (“Access code”). Print your badge or keep
it on your phone, and show the QR code at the desk. This QR code is your admission ticket:
do not share it. If you lose it, go to the desk: you receive a new badge and the old one no
longer works. A registration awaiting payment is sent to the desk.</p>
<h3>I need an invitation letter for my visa.</h3>
<p>A current registration is required. “My documents” › “Request an invitation letter”: name
exactly as shown in the passport, nationality, passport number, arrival and departure dates
(stay of 90 days at most), embassy or consulate. The committee reviews the request and
notifies you by email. The signed letter is downloaded from “My documents” and can be
verified with its QR code. It supports your visa application but does not commit the
organisers to covering your costs. Your passport number is shared with the committee only
and erased after the conference. If the request is refused, the reason is shown and you can
make a new request.</p>
<h3>How do I declare a diet or an allergy?</h3>
<p>“Diet and announcements”: for each conference where you are registered or a committee
member, state a diet or an allergy and tick the consent box. The caterer only receives
headcounts, without names. You can withdraw your declaration at any time; it is deleted
30 days after the conference.</p>
<h3>Invited speaker: where do I give my needs and travel details?</h3>
<p>“My visit”, for invited speakers only: technical needs, arrival, departure, means of
transport, accommodation or transfer needed, message to the committee. It also shows what
the committee has arranged for you (hotel, nights, coverage).</p>
```

### Section 5 — “After the conference and personal data” (`aide-apres`)

```html
<h3>How do I get my certificate?</h3>
<p>The committee issues certificates after the conference and notifies you by email; they are
downloaded from “My documents” › “Certificates”. The certificate of attendance requires your
attendance to have been recorded (badge scanned at the desk or at a session entrance); the
certificate of presentation, your paper to have been presented.</p>
<p>[SI ATTESTATIONS D'ÉVALUATION] Reviewers receive a certificate of reviewing, which only
states the number of reviews.</p>
<h3>How can a certificate or a letter be verified?</h3>
<p>Each certificate and each letter carries a QR code leading to its verification page. The
code can also be entered on the <a href="/verification">verification page</a>: it is the end
of the address printed under the QR code. The page shows whether the document is authentic or
revoked.</p>
<h3>Is the satisfaction survey anonymous?</h3>
<p>Yes. It is offered to people whose attendance was recorded, by notification and by email,
when it opens: “Surveys” › “Answer”. Your answer is recorded with no link to your account,
and only once. Results are shown to the committee only from five answers. Free comments are
read by the committee: do not include information that identifies you if you do not wish
to.</p>
<h3>How do I stop receiving announcements?</h3>
<p>With the unsubscribe link in every announcement received by email, or in “Diet and
announcements” (box “Receive the conference announcements by email”). Service emails
(submission, registration, documents) and notifications are still sent.</p>
<h3>What happens to my personal data?</h3>
<ul>
<li>“My data” › “Download (JSON)”: your account, profile, addresses, roles, invitations,
consents, emails received and your actions over the last 12 months.</li>
<li>“My data” › “Anonymize my account”: immediate and permanent; your address, profile,
two-factor authentication and sessions are erased, and you can no longer sign in. The action
log and the history of your consents are kept, without your name or address. If you hold an
active organising role (committee, volunteer…), hand it over first.</li>
<li>“Privacy”: your consent to appear in the public committee directory and to the
publication of your photo; you can withdraw it at any time.</li>
<li>Sign-ins and sensitive actions are logged for security; the IP address is erased after
six months. Dietary information and passport numbers are erased after the conference.</li>
<li>A question about your data, or a question this page does not answer: [CONTACT].</li>
</ul>
```

## 4. Points vérifiés et réserves

- Chaque réponse renvoie à un écran ou à une règle existants : routes du portail
  (`web/projects/portail/src/app/app.routes.ts`, `account/account.routes.ts`), libellés
  (`web/projects/portail/src/i18n/fr.json`, `en.json`) et services du serveur (retraits,
  facturation, échéances, effacements).
- Pas de formulaire de contact, pas de connexion ORCID, pas d'agenda personnel des sessions
  pour les participants : la page n'en parle pas.
- Les durées d'effacement citées (régime et passeport : 30 jours après la conférence ;
  adresse IP : six mois) sont celles du code ; la politique de confidentialité définitive
  (S14) peut les préciser et doit rester cohérente avec cette page.
