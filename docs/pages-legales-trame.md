# Pages légales — trame proposée (lot L9, décision S14)

> **Statut : proposition de l'équipe, à compléter et à valider par le commanditaire.** Le texte
> définitif des pages appartient au commanditaire, responsable du traitement ; cette trame
> n'est pas un avis juridique et ne le remplace pas. Une relecture par un juriste au fait de
> la loi ivoirienne n° 2013-450 et, le cas échéant, du RGPD est recommandée.
>
> Elle décrit **ce que la plateforme traite réellement** au 12 octobre 2026, d'après le code :
> registre des données personnelles (`backend/apps/core/personal_data.py` et les fichiers
> `personal_data.py` de chaque application), tâches de conservation
> (`backend/apps/core/retention.py` et celles déclarées par les applications), cookies et
> stockage du navigateur (réglages Django, code Angular), sous-traitants techniques. Chaque
> élément à fournir par le commanditaire est marqué **[À COMPLÉTER : …]**. Ce qui n'a pas été
> vérifié est marqué « non vérifié ».

## 0. Mode d'emploi

- **Trois pages** : mentions légales, politique de confidentialité, cookies (cette dernière
  peut être une section de la politique). Les publier dans le CMS du portail comme **pages
  personnalisées** (`/fr/p/<slug>/` et `/en/p/<slug>/`, sections « texte riche »), liées dans
  le **menu de pied de page**, en français et en anglais, puis publier le portail
  (`deploy/deploy.sh --portal-only`). Les pages du CMS sont rattachées à une **édition** : les
  recréer à chaque nouvelle édition (aucune copie automatique n'a été vérifiée).
- **Notice d'information du compte** : l'espace compte affiche déjà une notice provisoire
  (version `2026-10-v0`, `apps/accounts/consents.py` et
  `web/projects/portail/src/app/account/ui/privacy-notice.ts`), dont la prise de connaissance
  est enregistrée. Son texte définitif doit être **cohérent** avec la politique de
  confidentialité et renvoyer vers elle ; une nouvelle version est un changement de code
  (équipe), qui redemande la prise de connaissance à chacun. La version provisoire ne doit
  pas servir à l'ouverture de l'appel.
- **Durées** : les durées de conservation codées sont des **propositions** (décision D15),
  appliquées en **simulation** tant que `GESTCONF_RETENTION_ENFORCED` est faux, sauf les
  purges de sécurité (§2.6). La page publique ne doit annoncer que des durées validées par le
  commanditaire et effectivement appliquées.
- Chaque page porte sa **date de mise à jour** et un numéro de version.

## 1. Mentions légales

1. **Éditeur du site** : [À COMPLÉTER : dénomination de l'organisme organisateur, forme
   juridique, adresse du siège, numéro d'immatriculation ou identifiant (RCCM, autre),
   téléphone, adresse e-mail de contact].
2. **Directeur ou directrice de la publication** : [À COMPLÉTER : nom et fonction].
3. **Hébergeur** : o2switch, hébergement mutualisé (offre souscrite par le commanditaire).
   [À COMPLÉTER : dénomination sociale, adresse et téléphone de l'hébergeur, tels qu'ils
   figurent au contrat ; pays d'hébergement des serveurs (France probable, non vérifié)].
4. **Conception et logiciel** : plateforme GEST-CONF [À COMPLÉTER : mention du prestataire de
   développement et de la licence du logiciel, si le commanditaire le souhaite].
5. **Propriété intellectuelle** : contenus du site (textes, logos, visuels) [À COMPLÉTER :
   titulaire des droits, conditions de réutilisation] ; les communications déposées restent
   la propriété de leurs auteurs [À COMPLÉTER : licence de diffusion des résumés et des
   actes ; question ouverte « actes (DOI, ISBN) » de l'étude §15] ; logos des partenaires
   publiés avec leur accord.
6. **Liens externes** : liens vers des sites tiers (partenaires, prestataire de paiement)
   sous la responsabilité de leurs éditeurs.
7. **Responsabilité** : [À COMPLÉTER : clause usuelle de limitation, disponibilité du
   service].
8. **Droit applicable et juridiction** : [À COMPLÉTER].
9. **Contact** : [À COMPLÉTER : adresse e-mail ou formulaire] ; renvoi vers la politique de
   confidentialité pour les données personnelles.

## 2. Politique de confidentialité

### 2.1 Responsable du traitement et contact

- Responsable du traitement : [À COMPLÉTER : organisme organisateur, adresse, représentant].
- Contact pour les données personnelles : [À COMPLÉTER : adresse e-mail dédiée ; délégué ou
  correspondant à la protection des données s'il en est désigné un].

### 2.2 Cadre légal

- Loi n° 2013-450 relative à la protection des données à caractère personnel (Côte
  d'Ivoire) ; autorité de contrôle : ARTCI. [À COMPLÉTER : intitulé et date exacts de la loi,
  formalités accomplies auprès de l'ARTCI (déclaration ou autorisation) et leurs références ;
  à établir par le commanditaire, non vérifié par l'équipe].
- RGPD (règlement (UE) 2016/679) : [À COMPLÉTER : applicabilité à apprécier par le
  commanditaire, notamment si des participants se trouvent dans l'Union européenne ; le cas
  échéant, base légale de chaque traitement, droits propres au RGPD et autorité compétente].
- Transfert hors de Côte d'Ivoire : les serveurs de l'hébergeur et des sous-traitants (§2.5)
  peuvent être situés à l'étranger [À COMPLÉTER : pays, encadrement du transfert ; non
  vérifié].

### 2.3 Données traitées et finalités

Pour chaque ligne : [À COMPLÉTER : base légale retenue par le commanditaire (exécution de la
participation, intérêt légitime, obligation légale, consentement)].

| Traitement | Personnes | Données | Finalité |
|---|---|---|---|
| Compte et authentification | toute personne qui crée un compte | adresse e-mail, mot de passe haché (jamais en clair), secret de double authentification chiffré (rôles de gestion), sessions | accès sécurisé à l'espace personnel et à la gestion |
| Profil | titulaires d'un compte | titre, prénom, nom, institution, département, pays, ORCID, biographie, site, liens Google Scholar et LinkedIn, photo | identification dans la conférence ; publication sur le portail **seulement** avec consentement (annuaire des comités, photo) |
| Consentements et notice | titulaires d'un compte | prise de connaissance de la notice, consentements « annuaire public » et « publication de la photo » (version du texte, date, adresse IP) | preuve des choix exprimés, retirables à tout moment |
| Rôles et invitations | membres des comités, bénévoles, signataires, intervenants | rôle par édition, invitations (adresse invitée, message) | organisation de la conférence |
| Soumissions | auteurs et co-auteurs (y compris sans compte) | métadonnées de la communication, liste des auteurs (prénom, nom, e-mail, institution, pays, rôles), fichiers PDF, historique | appel à communications ; en double aveugle, l'identité des auteurs n'est jamais servie aux relecteurs et les PDF sont réécrits sans métadonnées |
| Évaluation | relecteurs, auteurs | expertises, affectations, conflits d'intérêts, évaluations et notes, discussions du comité | sélection scientifique ; les auteurs reçoivent les commentaires sous pseudonyme (« Relecteur N »), jamais les notes |
| Programme | intervenants, présidents de séance, auteurs | rôles de séance, créneaux, confirmations de présentation, nom dans le programme publié | établissement et publication du programme [À COMPLÉTER : publication du nom des auteurs, question Q14] |
| Inscriptions | participants | catégorie, options, montants, moyen de paiement, justificatif éventuel (ex. carte d'étudiant), identité et adresse de facturation, jeton du badge | inscription, facturation, contrôle d'accès |
| Paiements et facturation | participants | références de paiement, statuts, factures, avoirs, pro forma, remboursements ; aucune donnée de carte bancaire sur la plateforme | encaissement et obligations comptables |
| Jour J | participants, bénévoles | pointages (lieu, heure), badge, attestations (nom, nature, code de vérification), image et nom du signataire | contrôle d'accès, attestations de présence et de communication |
| Lettres d'invitation (visa) | participants qui en demandent | nom tel qu'au passeport, nationalité, **numéro de passeport**, dates de séjour, ambassade ou consulat | délivrance d'une lettre pour la demande de visa |
| Venue des intervenants | intervenants invités | arrivée et départ (moyens, références de transport), hébergement, besoins techniques, demandes | organisation de la venue |
| Régimes alimentaires | participants qui le déclarent | régimes et allergies, **données sensibles** (elles peuvent révéler l'état de santé ou des convictions), consentement à chaque déclaration | organisation des repas ; le traiteur ne reçoit que des effectifs, sans nom |
| Bénévolat | bénévoles | postes et créneaux affectés | organisation de l'accueil |
| Tâches du comité | membres du CO | tâches, commentaires, pièces jointes | organisation interne |
| Communications | titulaires d'un compte | registre d'envoi des e-mails (destinataire, objet, statut), corps des messages pour une durée limitée, notifications dans l'espace, annonces et désabonnements | information des personnes ; désabonnement des annonces possible à tout moment |
| Questionnaires | participants invités | invitations seulement ; **réponses anonymes**, sans date, résultats affichés à partir de 5 réponses (RG-21) | évaluation de la conférence |
| Partenaires | contacts des organisations partenaires (sans compte) | nom, adresse e-mail, téléphone du contact | relation avec les partenaires ; jamais publiés |
| Journal d'audit | utilisateurs, opérateurs | actions sensibles (connexions, rôles, exports, décisions), adresse IP et navigateur | sécurité, traçabilité ; aucune adresse e-mail en clair dans les clichés |
| Sauvegardes | toutes | copie de la base et des fichiers | continuité du service |

**Ce que la plateforme ne fait pas** : pas de mesure d'audience, pas de publicité, pas de
profilage, pas de décision automatisée, pas de vente ni de cession de données.

### 2.4 Destinataires

- Au sein de l'organisation, **selon le rôle et l'édition** (droits vérifiés par le serveur) :
  présidence, comité scientifique (évaluation, sans l'identité des auteurs en double aveugle),
  comité d'organisation selon sa fonction (finances, programme, logistique, communication,
  relations extérieures, bénévoles, secrétariat), bénévoles de l'accueil, signataire.
- **Publics** : programme publié (noms des intervenants et, selon Q14, des auteurs), annuaire
  des comités (avec consentement), intervenants invités, partenaires publiés ; la page de
  vérification d'une attestation affiche le nom du titulaire (plus après anonymisation du
  compte).
- **Sous-traitants** : §2.5. [À COMPLÉTER : autres destinataires éventuels (traiteur :
  effectifs seulement ; hôtel ; éditeur des actes)].

### 2.5 Sous-traitants techniques

| Sous-traitant | Rôle | Données concernées | À compléter |
|---|---|---|---|
| o2switch | hébergement du site, de la base et des fichiers | toutes | [À COMPLÉTER : pays des serveurs, garanties contractuelles] |
| Fournisseur d'e-mails : Brevo **ou** Mailjet (décision D10) | envoi des e-mails transactionnels et des annonces | adresse e-mail, objet et contenu des messages | [À COMPLÉTER : fournisseur retenu, pays, lien vers sa politique] |
| CinetPay | paiement en ligne, sur sa page hébergée | montant, devise, référence, désignation, adresse e-mail, prénom et nom du payeur ; les moyens de paiement sont saisis chez CinetPay, jamais sur la plateforme | [À COMPLÉTER : si le paiement en ligne est activé ; lien vers sa politique] |
| Service de surveillance de disponibilité | vérifie que le site répond | aucune donnée personnelle (adresses publiques seulement) | [À COMPLÉTER : service retenu, facultatif dans la page] |

L'opérateur du commanditaire conserve des **copies des sauvegardes hors de l'hébergement**
(30 jours) : [À COMPLÉTER : qui, où, mesures de protection].

### 2.6 Durées de conservation

Durées **codées** dans la plateforme. Colonne « Appliquée » : *oui* = purge toujours
appliquée par la commande quotidienne `cleanup` ; *simulation* = durée proposée par D15,
comptée mais non appliquée tant que `GESTCONF_RETENTION_ENFORCED` est faux. [À COMPLÉTER :
durées validées par le commanditaire ; ne publier que celles-là.]

| Donnée | Durée | Appliquée |
|---|---|---|
| Session de connexion | 12 heures au plus (cookie de session supprimé à la fermeture du navigateur) | oui |
| Corps d'un e-mail contenant un lien à usage unique, non envoyé | 24 heures | oui |
| Fichiers orphelins (dépôt interrompu) | 24 heures | oui |
| Numéro de passeport et PDF de la lettre d'invitation | dès l'archivage de l'édition, ou 30 jours après sa fin | oui (K14) |
| Régime alimentaire et allergies | dès l'archivage de l'édition, ou 30 jours après sa fin | oui (RG-23) |
| Fiche de venue d'un intervenant | dès l'archivage de l'édition, ou 30 jours après sa fin | oui |
| Invitation à un rôle non acceptée | expire après 14 jours | oui |
| Corps des autres e-mails | 30 jours | simulation |
| Registre d'envoi des e-mails (métadonnées) | 12 mois | simulation |
| Notifications dans l'espace | 6 mois (lues), 12 mois (non lues) | simulation |
| Adresse et message des invitations refusées, annulées ou expirées | 12 mois | simulation |
| Adresse IP et navigateur du journal d'audit | 6 mois | simulation |
| Lignes du journal d'audit | 3 ans | simulation |
| Adresse IP associée aux consentements | 6 mois | simulation |
| Tâches techniques terminées | 30 jours | simulation |
| Compte et profil | jusqu'à l'anonymisation demandée par la personne ; aucune purge automatique des comptes inactifs n'est codée | [À COMPLÉTER : durée d'inactivité éventuelle] |
| Soumissions, évaluations, inscriptions, programme | aucune durée codée | [À COMPLÉTER : conservation au-delà de l'édition (archives, actes)] |
| Factures et avoirs | conservés, y compris après anonymisation du compte (identité figée à l'émission) | [À COMPLÉTER : durée légale de conservation des pièces comptables] |
| Attestations émises | conservées (preuve délivrée à la personne) | [À COMPLÉTER] |
| Sauvegardes | rotation : 7 quotidiennes, 4 hebdomadaires, 3 mensuelles (environ 3 mois) ; copies hors hébergement : 30 jours | oui |

### 2.7 Droits des personnes

- Droits : accès, rectification, effacement (anonymisation du compte), retrait du
  consentement, opposition aux annonces [À COMPLÉTER : portabilité, limitation et opposition
  au sens du RGPD si applicable ; droits prévus par la loi n° 2013-450].
- **Exercice en libre-service** (espace compte du portail) : export de ses données au format
  JSON et anonymisation du compte (`/compte/mes-donnees`), consentements
  (`/compte/confidentialite`), profil (`/compte/profil`), adresses e-mail et sécurité
  (`/compte/securite`), préférences d'annonces (`/compte/preferences`) ; lien de
  désabonnement dans chaque annonce.
- **Par demande écrite** : [À COMPLÉTER : adresse de contact, pièces demandées pour vérifier
  l'identité, délai de réponse].
- **Limites** à indiquer : l'anonymisation est refusée tant que la personne a une
  responsabilité en cours dans une édition non archivée (rôle de gestion, soumission ou
  évaluation en cours, rôle de séance, inscription en attente ou confirmée) ; sont conservés
  après anonymisation, sans adresse en clair, le journal d'audit et les consentements
  (preuves), les factures et avoirs (obligation comptable), les attestations émises, les
  évaluations (sans nom).
- **Réclamation** auprès de l'ARTCI [À COMPLÉTER : coordonnées] et, si le RGPD s'applique,
  auprès de l'autorité compétente.

### 2.8 Sécurité

Résumé à publier (sans détail exploitable) : connexions chiffrées (HTTPS), mots de passe
hachés, double authentification proposée à tous et recommandée pour les rôles de gestion
(obligatoire si l'exploitant l'impose : adapter le texte au réglage retenu), secrets de double
authentification chiffrés, droits vérifiés par le serveur pour chaque rôle et chaque édition,
évaluation en double aveugle garantie par le serveur, fichiers stockés hors de l'espace
public et servis après contrôle d'accès, journal des actions sensibles, sauvegardes
quotidiennes avec copie hors de l'hébergement. [À COMPLÉTER : procédure en cas de violation
de données (notification à l'ARTCI et aux personnes), délais à établir par le commanditaire].

### 2.9 Divers

- Mineurs : [À COMPLÉTER : âge minimal pour créer un compte, le cas échéant].
- Modifications de la politique : date, version, information des personnes (la notice du
  compte redemande la prise de connaissance à chaque nouvelle version).

## 3. Cookies et stockage dans le navigateur

**Aucun cookie de mesure d'audience, de publicité ou de réseau social ; aucun script ni
contenu tiers** (la politique de sécurité des contenus du site n'autorise que le domaine
lui-même). Les seuls éléments déposés sont nécessaires au fonctionnement du service.
[À COMPLÉTER : confirmer, au regard du droit applicable, qu'aucun bandeau de consentement
n'est requis pour ces seuls éléments strictement nécessaires.]

| Nom | Type | Rôle | Durée |
|---|---|---|---|
| `sessionid` | cookie (HttpOnly, Secure, SameSite=Lax) | maintient la connexion à l'espace personnel ou à la gestion | session du navigateur ; 12 heures au plus côté serveur |
| `csrftoken` | cookie (Secure, SameSite=Lax, lisible par l'application) | protection contre la falsification de requêtes | durée par défaut de Django (52 semaines) |
| `gestconf.lang` | stockage local | langue d'affichage choisie | jusqu'à effacement par l'utilisateur |
| `gc-banner-dismissed` | stockage de session | mémorise le bandeau d'information fermé | jusqu'à la fermeture de l'onglet |
| `gc.gestion.edition`, `gc.gestion.role.<n>` | stockage local (gestion seulement) | édition et rôle actifs dans l'espace de gestion | jusqu'à effacement |
| `gc.gestion.checkin.*` | stockage local (gestion seulement) | réglages du poste d'accueil (nom du poste, session) | jusqu'à effacement |
| base `gestconf-checkin` | IndexedDB (gestion, accueil seulement) | accueil hors ligne : liste d'empreintes des badges (valable 48 heures) et pointages en attente | effacée à la déconnexion |
| cache de l'application d'accueil | stockage du service worker (`/gestion/` seulement) | fonctionnement de l'accueil sans réseau | jusqu'à mise à jour ou effacement |

Paiement en ligne : la page de paiement est hébergée par CinetPay, sur son propre domaine ;
les cookies qu'elle dépose relèvent de sa politique [À COMPLÉTER : lien].
