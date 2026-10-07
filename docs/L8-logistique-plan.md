# Lot L8 — Logistique, partenaires, communication et reporting : plan d'implémentation

> **Statut : validé le 7 octobre 2026, en cours** (décisions N1 à N19 telles que proposées ;
> les questions du §10 restent sans réponse : les propositions valent hypothèses, §2.1).
> L7 est livré en code et testé en local (bilan : `docs/L7-jour-j.md`). Les décisions de
> ce lot sont numérotées N : les lettres L et M désignent déjà les lots et les modules de
> l'étude.
>
> Sources :
> - étude §4 M10 (intervenants invités et logistique), M11 (espace du comité
>   d'organisation : tâches, budget, documents, journal), M12 (annonces), M13 (sponsors et
>   exposants), M14 (questionnaire de satisfaction, annonces de dernière minute), M16
>   (reporting) ; §7.3 (applications `logistics`, `sponsors`, `reports`) ; §8.2 (`sponsor`,
>   `task`, `budget_line`) ; §9.2 (« logistique, sponsors, rapports ») ; §10.1 (espace
>   intervenant) et §10.2 (rubriques « Logistique », « Sponsors », « Communication ») ;
>   §14 (L8 : 10 à 14 j-h) ; annexe A2 (« Questionnaire de satisfaction ») ;
> - mises à jour §17 à §23 : rôles `SPEAKER` (L5), `VOLUNTEER` (L7) ; options à quota des
>   inscriptions (L6) ; présences et pointages (L7, RG-16) ; questionnaire de satisfaction
>   et annonces de dernière minute reportés en L8 (K16) ; fil d'activité non sensible du CO
>   annoncé en L8 (plan L1) ;
> - CLAUDE.md, règles n° 2 (droits côté serveur), n° 7 et RG-15 (aucune donnée de carte),
>   n° 8 (fichiers privés), n° 9 (tâches par `run_jobs`, pas de WebSocket), n° 10
>   (bibliothèques sans dépendance système), n° 11 (secrets).

## En bref

| | |
|---|---|
| **Objectif** | Le comité d'organisation **pilote** l'édition : tâches en kanban, budget prévisionnel et réalisé, partenaires (niveaux, contreparties, logos sur le portail), intervenants invités (besoins techniques, voyage, hébergement), restauration (effectifs et régimes), planning des bénévoles. Il **communique** : annonces (actualités du portail, bandeau de dernière minute, cloche, e-mail) et envois groupés par segments. Après la conférence, il recueille la **satisfaction** des présents. Il **mesure** : rapports et indicateurs, exports CSV, XLSX et PDF. |
| **Point dur** | **Portail pré-rendu** : le bandeau de dernière minute doit s'afficher sans republication (lecture dans le navigateur, sans alourdir le bundle initial déjà au-dessus de l'avertissement). **Volume d'e-mails** sur un hébergement mutualisé : plafond horaire global (200 par heure par défaut), qui ne doit jamais retarder les e-mails de compte. **Données sensibles** : un régime alimentaire peut révéler la santé ou des convictions. **Anonymat** des réponses au questionnaire, avec de petits effectifs. |
| **Hors périmètre** | Espace partenaire en libre-service (dépôt de documents, plan des stands), factures des partenaires (Q8), réservation de voyages et d'hôtels (suivi seulement), SMS et WhatsApp (P3), suivi des repas réellement servis, inventaire du matériel, comptabilité (TVA, grand livre), indisponibilités des intervenants dans le planificateur, « Mon programme » du participant (J15). |
| **Charge** | **28,5 à 34,5 j-h** (étude : 10 à 14). Détail au §8 ; découpage possible au §10 (question 2). |
| **Démo I** | Le CO crée les tâches de préparation et les répartit ; la logistique renseigne l'hôtel d'un intervenant, qui complète ses besoins techniques et son arrivée dans « Ma venue » ; un participant déclare un régime sans gluten. Le CO « finances » saisit le budget : les recettes d'inscription et de partenariat se calculent seules. Un partenaire « Or » apparaît sur le portail après publication. Le CO « bénévoles » remplit le planning de l'accueil. Le jour J, un bandeau « Salle B fermée : plénière en salle A » s'affiche aussitôt sur le portail et part par e-mail aux inscrits confirmés. Le lendemain, les présents reçoivent le questionnaire ; le rapport montre le taux de réponse, la satisfaction, le taux de présence et l'écart budgétaire, exportés en XLSX. |

## 1. Périmètre

| Fonction (étude) | Priorité | Dans L8 |
|---|---|---|
| Tâches du CO en kanban : responsable, échéance, commentaires, pièces jointes (M11) | P2 | Oui (N3) |
| Budget prévisionnel et réalisé par poste (M11) | P2 | Oui (N4) |
| Sponsors : niveaux, contreparties, logos sur le portail (M13) | P2 | Oui (N5) |
| Sponsors : espace de dépôt, plan des stands, factures, badges exposants (M13) | P2 | **Non**, sauf badges exposants par une catégorie d'inscription (N5) |
| Fiche intervenant, besoins techniques, voyage, hébergement (M10, §10.1) | P2 | Oui (N6) |
| Restauration : effectifs, régimes (M10) | P2 | Oui (N7, N8) |
| Bénévoles : planning et postes (M10) | P2 | Oui (N9) ; le recrutement passe par l'invitation de L7 |
| Annonces sur le portail et par e-mail (M12), bandeau de dernière minute (M14) | P2 | Oui (N10) |
| Messagerie de masse par segments (M11) | P1 de M11 | Oui (N11) |
| Questionnaire de satisfaction, global et par session (M14) | P2 | Oui (N12) |
| Reporting : indicateurs, exports CSV, XLSX, PDF (M16) | P2 | Oui (N13) |
| Tableau de bord et journal d'activité du CO (M11) | P1 | Compléments (N14) |
| Documents partagés du CO (M11) | P1 de M11 | **Partiel** : pièces jointes des tâches (N3) |
| Annuaire des participants (M11) | P1 de M11 | Déjà livré (liste, filtres et export des inscriptions, L6) |
| Cartographie et informations pratiques (M10) | P2 | Déjà possible par les pages du CMS (L2) ; rien à ajouter |

**Écarts avec l'étude, à valider** :

- `sponsor` et `task` suivent le §8.2, enrichis (statut, contreparties, version) ; `budget_line`
  distingue dépenses et recettes, et les recettes d'inscription et de partenariat sont
  **calculées** et non saisies (N4) ;
- documents partagés réduits aux pièces jointes des tâches, en PDF, PNG ou JPEG seulement
  (règle n° 8 : type vérifié par contenu ; un document bureautique se joint en PDF) ;
- trois règles de gestion proposées : **RG-21** (anonymat du questionnaire), **RG-22**
  (envois groupés), **RG-23** (régimes alimentaires) ; voir N7, N11 et N12 ;
- une nouvelle commande cron quotidienne, `remind_tasks` (N3).

## 2. Décisions (validées)

| # | Sujet | Proposition |
|---|---|---|
| N1 | Applications | **`logistics`** (tâches, budget, intervenants, régimes, repas, bénévoles), **`sponsors`**, **`surveys`** (questionnaires) et **`reports`** (lecture seule ; il dépend des autres, aucune ne dépend de lui). Annonces et envois groupés dans **`communications`**. Les segments de destinataires sont **déclarés** par chaque application (`register_segment`, sur le modèle de `register_guard`) : `communications` ne dépend d'aucune application métier. `registrations` ne dépend pas de `logistics` : le régime se déclare par son propre endpoint. |
| N2 | Droits | Capacités nouvelles.<br>— **`tasks.read`**, **`tasks.write`** : `ADMIN`, `CHAIR`, CO de toutes fonctions.<br>— **`budget.read`** : `ADMIN`, `CHAIR`, CO « finances ». **`budget.write`** : `ADMIN`, CO « finances ».<br>— **`sponsors.read`** : `ADMIN`, `CHAIR`, CO « finances », « relations extérieures », « communication ». **`sponsors.write`** : `ADMIN`, CO « relations extérieures ».<br>— **`logistics.read`** : `ADMIN`, `CHAIR`, CO « logistique », « secrétariat ». **`logistics.write`** : `ADMIN`, CO « logistique ». Les noms liés à un régime ou à une allergie : `logistics.read` seulement (N7).<br>— **`volunteers.plan`** : `ADMIN`, CO « bénévoles », « logistique ». Le bénévole lit **son** planning (`shifts.own`, rôle `VOLUNTEER`).<br>— **`communications.send`** : `ADMIN`, `CHAIR`, CO « communication » ; réauthentification récente pour un envoi.<br>— **`surveys.manage`** : `ADMIN`, `CHAIR`, CO « communication », « secrétariat ».<br>— **Rapports** : pas de capacité propre ; chaque section s'ouvre à la capacité qui protège déjà ses données (N13).<br>L'intervenant invité (`SPEAKER`) renseigne **sa** venue dans le portail, sans capacité de gestion. `SPONSOR` reste non invitable (pas d'espace partenaire en L8). |
| N3 | Tâches (M11) | Kanban à trois colonnes (à faire, en cours, terminé). Une tâche : titre, description, **responsable** (membre de l'édition ayant un rôle de gestion), échéance (date), priorité (basse, normale, haute), étiquette libre, ordre dans la colonne. Commentaires ; **pièces jointes** privées (PDF, PNG, JPEG ; 10 Mo ; règle n° 8). Révision en `If-Match` (412 si la tâche a changé entre-temps, comme le programme de L5). Archivage au lieu de suppression ; journal `tasks.*`. Cloche à l'affectation ; **`remind_tasks`** (cron quotidien, idempotent et verrouillé) : un récapitulatif par responsable des tâches en retard ou à échéance sous 2 jours. Déplacement au clavier (« Déplacer vers… », flèches, `aria-live`), le CDK n'ayant ni clavier ni ARIA (même approche que le planificateur de L5). |
| N4 | Budget (M11) | Lignes de **dépense** ou de **recette**, par poste d'un catalogue fermé (dépenses : lieu, restauration, voyages, hébergement, communication, impression, matériel, personnel, divers ; recettes : inscriptions, partenariats, subventions, divers), libellé, **prévu** et **réalisé** en `Decimal` exact dans la devise de l'édition (`apps/core/money.py`), note, justificatif privé facultatif. Réalisé **calculé**, en lecture seule : « inscriptions » = encaissé net des paiements (L6) ; « partenariats » = contributions reçues (N5). Écarts par poste et total ; export CSV et XLSX ; journal `budget.*`. Ce n'est pas une comptabilité : ni TVA, ni écriture, ni rapprochement bancaire. |
| N5 | Partenaires (M13) | **Niveaux** par édition : nom FR et EN, montant indicatif, contreparties FR et EN, taille du logo sur le portail, ordre. **Partenaire** : nom, niveau, logo (`PublicFile` image), site, présentation FR et EN, contact (nom, adresse, téléphone : jamais publiés), contribution convenue, montant reçu et date, statut (`prospect`, `agreed`, `received`, `declined`), publié ou non. **Contreparties** cochées une à une (livrée, date). Page publique **« Partenaires »** pré-rendue par niveau (partenaires publiés seulement), visible après `deploy.sh --portal-only` et comptée dans les modifications non publiées (L2). **Badges exposants** : une catégorie d'inscription « Exposant » (L6) et le comptoir (L7) suffisent ; aucun code. **Factures** : hors plateforme tant que Q8 n'est pas tranchée (question 3). |
| N6 | Intervenants invités (M10) | **Fiche de venue** par intervenant invité de l'édition (rôle `SPEAKER`) : besoins techniques (catalogue fermé des équipements de salle de L5, plus note), arrivée et départ (date et heure **saisies en heure locale de l'édition**, D13 ; moyen ; référence de vol ou de train), hébergement (pris en charge ou non, hôtel, nuits), transferts, statut de la prise en charge (`to_arrange`, `booked`, `confirmed`), **note interne** du CO (jamais montrée à l'intervenant). L'intervenant remplit sa part dans le portail (**« Ma venue »**, `/compte/ma-venue`) et lit ce que le CO a réservé. Signal dans la liste : besoin technique absent de l'équipement de la salle de sa session (programme **publié**). Page publique **« Intervenants »** réelle : construite depuis l'**instantané publié** du programme (intervenants des créneaux libres et des sessions plénières), consentements de L2 respectés ; elle quitte l'état « à venir ». |
| N7 | Régimes alimentaires (M10, RG-23) | Déclaration **facultative**, par personne et par édition : participants (depuis « Mon inscription »), intervenants (« Ma venue »), membres des comités et bénévoles (même carte, dans le compte). Catalogue fermé (végétarien, végétalien, sans porc, sans gluten, sans lactose, autre) et allergies en texte libre (200 caractères). **Consentement explicite** : la donnée peut révéler la santé ou des convictions ; retrait possible à tout moment. Visibilité : effectifs agrégés pour la restauration ; noms et allergies pour `logistics.read` seulement, export journalisé avec réauthentification. **Effacée 30 jours après la fin de l'édition** ou à son archivage (`cleanup`, comme le numéro de passeport en L7). |
| N8 | Restauration (M10) | **Repas** paramétrés : jour, type (pause café, déjeuner, dîner, cocktail), libellé FR et EN, public (inscrits confirmés, ou titulaires d'une **option** de L6 comme le dîner de gala ; intervenants, comités et bénévoles à cocher), marge en pourcentage. **Estimation** calculée : effectif, répartition par régime, marge ; export pour le traiteur (CSV, XLSX, PDF) **sans nom** ; liste nominative des allergies à part (N7). Les repas réellement servis ne sont pas suivis. |
| N9 | Bénévoles (M10) | **Postes** : intitulé FR et EN, lieu, début et fin (heure locale de l'édition), nombre de bénévoles nécessaires, consignes. **Affectation** de membres `VOLUNTEER` de l'édition ; deux postes qui se chevauchent pour la même personne : refus. Postes non pourvus signalés. Le bénévole voit **« Mon planning »** dans la gestion (rubrique « Jour J »), avec un fichier iCal (générateur de L5). Cloche à chaque affectation ou retrait. |
| N10 | Annonces (M12, M14) | Une annonce : titre et texte FR et EN (HTML en liste blanche, assaini au serveur **et** au rendu, assainisseur de L2), canaux cochés :<br>— **actualités** du portail : page pré-rendue `/fr/actualites/` et `/en/news/`, visible après `deploy.sh --portal-only` ;<br>— **bandeau de dernière minute** : visible **aussitôt**, entre un début et une fin, une seule annonce active à la fois. Le portail le lit dans le navigateur (`GET /v1/public/editions/{code}/banner`, réponse minimale, cache de 60 s), par un composant chargé **à la demande** après le premier rendu : le bundle initial ne grossit pas, le pré-rendu ne change pas ;<br>— **cloche** et **e-mail** : aux destinataires d'un segment (N11).<br>Brouillon, publication, retrait ; journal `announcements.*`. |
| N11 | Envois groupés (M11, RG-22) | **Segments** en catalogue fermé, déclarés par les applications : auteurs (soumission envoyée, acceptés, présentateurs au programme), relecteurs (tous ; en retard, réservé à `reviews.manage`), inscrits (confirmés, en attente de paiement), présents (L7), intervenants invités, présidents de séance, comité scientifique, comité d'organisation, bénévoles. Le CO voit le **nombre** de destinataires et un aperçu ; il s'envoie un essai ; il confirme après réauthentification. **Un e-mail par personne**, jamais de liste en copie ; langue du compte ; pied de page qui dit pourquoi la personne reçoit l'e-mail et propose un **lien de désabonnement** des annonces (jeton signé ; les e-mails de service, eux, restent envoyés). File `BULK` de `run_jobs` : les envois groupés n'utilisent que **la moitié** du plafond horaire, l'autre restant aux e-mails de compte et de service ; durée estimée affichée ; annulation de ce qui n'est pas encore parti. Journal (RG-17 : action de masse). |
| N12 | Questionnaire de satisfaction (M14, RG-21) | Questionnaire **global** et, si l'édition le veut, **par session**. Questions de types fermés (note de 1 à 5, choix unique, choix multiples, texte libre de 1 000 caractères au plus), FR et EN ; modèle par défaut proposé (organisation, programme, lieu, accueil, recommandation, commentaire). Ouverture après la conférence (ou après la session), clôture datée. **Invités** : les personnes dont la présence est enregistrée (L7 ; pour une session, celles pointées à son entrée) ; e-mail et cloche, **une** relance. Réponse dans le portail (`/compte/questionnaires/{id}`), une seule par personne. **Anonymat** : la réponse est stockée **sans lien** avec son auteur ; l'invitation est marquée « répondu » dans la même transaction ; dates arrondies au jour ; ordre des réponses non conservé. Résultats agrégés affichés **à partir de 5 réponses** ; textes libres exportés dans un ordre aléatoire, et la personne est prévenue que le comité les lira. Questions verrouillées dès la première réponse (on duplique, comme une grille en RG-05). |
| N13 | Rapports (M16) | Écran **« Rapports »**, sections ouvertes selon les capacités existantes :<br>— soumissions par thématique, type, pays et statut, taux d'acceptation par thématique et par pays (`submissions.read`) ; délais de relecture et retards (`reviews.manage`) ;<br>— inscriptions par semaine, catégorie, zone, pays (`registrations.read`) ; recettes (`finance.read`) ;<br>— taux de présence par jour et par session (`checkin.manage` ou `registrations.read`) ;<br>— satisfaction (`surveys.manage`) ; budget (`budget.read`) ; partenaires (`sponsors.read`).<br>Graphiques en barres CSS ou SVG **sans bibliothèque**, chacun doublé de son tableau (accessibilité). Exports : **CSV** (assistant existant), **XLSX** (`openpyxl`, Python pur, à vérifier en L8.0 ; même protection contre l'injection de formules), **PDF** de synthèse (`fpdf2`). Exports journalisés. Aucune donnée nominative dans un rapport. |
| N14 | Tableau de bord et activité (M11) | Cartes nouvelles, chacune sous sa capacité : mes tâches (en retard, à échéance sous 7 jours), budget (écart), partenaires (convenu et reçu), logistique (intervenants à organiser), bénévoles (postes non pourvus), annonces (bandeau actif), questionnaire (taux de réponse). **Fil d'activité du CO** : les 50 dernières entrées du journal, restreintes à une **liste blanche** d'actions non sensibles (ni décision, ni identité d'auteur, ni montant individuel), pour `tasks.read`. |
| N15 | Données personnelles | Registre (export) : fiches de venue, régimes, affectations de bénévolat, invitations aux questionnaires, préférences de désabonnement. Les réponses anonymes ne sont pas des données personnelles (N12). **Anonymisation** : fiche de venue et régime effacés ; commentaires et tâches gardés, auteur anonymisé ; affectations de bénévolat anonymisées. **Conservation** : fiches de venue et régimes effacés 30 jours après la fin de l'édition (`cleanup`). |
| N16 | Écrans | **Gestion**, rubriques nouvelles : « Organisation » (tâches, budget, activité), « Logistique » (intervenants, restauration, bénévoles), « Partenaires » (partenaires, niveaux), « Communication » (annonces, envois groupés, questionnaires), « Rapports » ; « Mon planning » dans « Jour J » pour le bénévole ; cartes du tableau de bord ; chaque écran inscrit dans `core/navigation.ts` avec sa fiche d'aide ; `ROLE_GROUPS` mis à jour. **Portail** : pages pré-rendues « Partenaires », « Intervenants » (réelle) et « Actualités » ; bandeau de dernière minute ; dans le compte, « Ma venue » (intervenant), carte « Régime alimentaire », « Questionnaires », désabonnement des annonces. |
| N17 | Exploitation | Cron : **`remind_tasks`** quotidienne (seule ligne nouvelle) ; les envois groupés, les invitations et la relance du questionnaire passent par `run_jobs` (tâches datées). Aucune variable d'environnement obligatoire nouvelle ; `GESTCONF_EMAIL_MAX_PER_HOUR` borne toujours le total. `check_integrity` : contributions reçues ⇔ statut du partenaire, affectations de bénévoles qui se chevauchent, réponses rattachées à un questionnaire fermé. |
| N18 | Reporté | Espace partenaire en libre-service et factures des partenaires (Q8), réservation de voyages et d'hôtels, indisponibilités des intervenants dans le planificateur (M7, P2), suivi des repas servis, inventaire du matériel, SMS et WhatsApp (P3), « Mon programme » (J15). |
| N19 | Ordre | L8.0 vérifications ; L8.1 modèle, droits, matrice, registre ; L8.2 tâches et budget ; L8.3 partenaires ; L8.4 logistique (intervenants, régimes, repas, bénévoles) ; L8.5 annonces, bandeau et envois groupés ; L8.6 questionnaire ; L8.7 rapports et exports ; L8.8 écrans de la gestion ; L8.9 portail ; L8.10 E2E, recette, documentation |

### 2.1 Validation (7 octobre 2026) et hypothèses retenues

Le commanditaire a validé le plan sans répondre aux questions du §10. Les propositions
s'appliquent donc, comme hypothèses révisables :

| Question (§10) | Hypothèse retenue |
|---|---|
| 1. Ordre des lots | L8 puis L9, comme l'étude |
| 2. Périmètre | Tout le lot, sans bloc différé |
| 3. Partenaires | Niveaux et montants saisis par le CO ; pas d'espace en libre-service ; factures hors plateforme |
| 4. Régimes | Recueillis pour tous (inscrits, intervenants, comités, bénévoles), avec consentement ; catalogue de N7 |
| 5. Intervenants | La plateforme suit les réservations faites par l'organisation |
| 6. Questionnaire | Anonyme ; global, et par session si l'édition l'active ; modèle par défaut modifiable |
| 7. Envois groupés | Moitié du plafond horaire ; lien de désabonnement des annonces ; fournisseur de production toujours en attente (D10) |
| 8. Budget | Catalogue de postes de N4 ; visible du Chair et du CO « finances » |
| 9. Rapports | Indicateurs de N13 ; PDF de synthèse conservé |

## 3. Modèle de données (additif)

**`logistics`** :

- `task` : édition, titre, description, statut (`todo`, `doing`, `done`), priorité,
  étiquette, responsable (nullable), échéance, position, révision, créée par, terminée le,
  archivée le ; `task_comment` (tâche, auteur, texte, date) ; `task_attachment` (tâche,
  fichier privé, nom, type vérifié, taille, déposé par).
- `budget_line` : édition, nature (`expense`, `income`), poste (catalogue), libellé, prévu,
  réalisé (nul pour une ligne calculée), source (`manual`, `registrations`, `sponsors`),
  note, justificatif privé, position.
- `speaker_visit` : édition, compte (rôle `SPEAKER`), besoins (liste fermée et note),
  arrivée et départ (instant, moyen, référence), hébergement (pris en charge, hôtel, entrée,
  sortie), transferts, statut, note interne, mis à jour par et le ; unique par (édition,
  compte).
- `dietary_declaration` : édition, compte, régimes (liste fermée), allergies, consentement
  (date) ; unique par (édition, compte) ; effacée selon N15.
- `meal` : édition, jour, type, libellés, public (inscrits confirmés ou option de L6 ;
  intervenants, comités, bénévoles), marge.
- `volunteer_shift` (édition, intitulés, lieu, début, fin, besoin, consignes) et
  `shift_assignment` (poste, bénévole, affecté par ; unique).

**`sponsors`** : `sponsor_level` (édition, noms, montant indicatif, contreparties, taille du
logo, position) ; `sponsor` (édition, nom, niveau, logo, site, présentations, contact,
contribution convenue, reçu et date, statut, publié, position) ; `sponsor_benefit`
(partenaire, libellé, livrée le).

**`communications`** : `announcement` (édition, titres et textes, canaux, segment, début et
fin du bandeau, statut, publiée le, envoyée le, nombre de destinataires, auteur) ;
`announcement_delivery` (annonce, compte, e-mail de la file : traçabilité sans liste en
copie) ; `announcement_opt_out` (compte, édition, date). `NotificationKind` gagne
`announcement`, `task_assigned`, `shift_assigned`, `survey_invitation`.

**`surveys`** : `survey` (édition, portée globale ou session, titres, introduction, ouverture,
clôture, statut, verrouillé) ; `survey_question` (questionnaire, position, type, libellés,
choix, obligatoire) ; `survey_invitation` (questionnaire, compte, invitée le, relancée le,
répondu le — **arrondi au jour**) ; `survey_response` (questionnaire, réponses en JSON,
jour de réponse ; **aucune clé vers un compte ni vers l'invitation**).

**`reports`** : aucun modèle ; services de calcul en lecture seule.

## 4. API

**Public** : `GET /v1/public/editions/{code}/banner` (bandeau actif, réponse minimale, cache
de 60 s, limité en débit) ; partenaires, intervenants et actualités dans les données du
pré-rendu (`site` de L2).

**Compte** : `GET/PUT /v1/me/editions/{id}/visit` (« Ma venue ») ;
`GET/PUT/DELETE /v1/me/editions/{id}/dietary` ; `GET /v1/me/surveys`,
`GET/POST /v1/me/surveys/{id}` ; `POST /v1/public/announcements/unsubscribe` (jeton signé).

**Gestion** (`…/manage/editions/{id}/…`, 2FA des rôles de gestion) : `tasks` (liste filtrée,
création, mise à jour en `If-Match`, déplacement, archivage, commentaires, pièces jointes) ;
`budget` (lignes, synthèse, export) ; `sponsors` et `sponsor-levels` (contreparties,
export) ; `logistics/visits`, `logistics/dietary` (agrégats ; liste nominative avec
réauthentification), `logistics/meals` (estimation, export), `logistics/shifts`
(affectations) ; `me/shifts` (planning du bénévole, iCal) ; `announcements` (brouillon,
aperçu, essai, publication, retrait) ; `segments` (catalogue autorisé, comptage) ;
`surveys` (questions, ouverture, relance, résultats, export) ; `reports/{section}`
(indicateurs, exports CSV, XLSX, PDF) ; `activity` (fil du CO).

## 5. Frontend

- **Gestion** : rubriques « Organisation », « Logistique », « Partenaires »,
  « Communication » et « Rapports » ; kanban accessible au clavier ; « Mon planning » du
  bénévole ; cartes du tableau de bord ; fiches d'aide ; graphiques sans bibliothèque,
  doublés de tableaux.
- **Portail** : « Partenaires », « Intervenants », « Actualités » pré-rendues (FR et EN,
  fournisseurs d'adresses de L5) ; bandeau de dernière minute chargé à la demande, annoncé
  aux lecteurs d'écran (`role="status"`), refermable pour la visite ; « Ma venue »,
  régime, questionnaires et désabonnement dans le compte.

## 6. Sécurité

- **Droits** au serveur pour chaque section (règle n° 2) ; matrice étendue, un test par
  case sensible.
- **Régimes** : consentement explicite, finalité limitée à la restauration, noms réservés à
  `logistics.read`, export nominatif journalisé avec réauthentification, effacement à 30
  jours (RG-23).
- **Envois groupés** : réauthentification, comptage avant envoi, un e-mail par personne,
  désabonnement des annonces respecté, journal ; segment « relecteurs en retard » réservé à
  `reviews.manage` ; aucun e-mail ne révèle d'autres destinataires (RG-22).
- **Questionnaire** : aucune jointure possible entre une réponse et une personne ; seuil de
  5 réponses ; dates arrondies (RG-21).
- **Bandeau public** : contenu assaini, réponse minimale, limité en débit, aucune donnée
  non publiée.
- **Fichiers** : pièces jointes et justificatifs privés, type vérifié par contenu,
  téléchargement authentifié (règle n° 8).
- **Exports** : CSV et XLSX protégés contre l'injection de formules ; journalisés.
- **Note interne** des fiches de venue jamais servie à l'intervenant (sérialiseurs par
  rôle).

## 7. Tests

- **Unitaires** : budget (calculs en `Decimal`, réalisé calculé), estimation des repas,
  chevauchement des postes de bénévoles, révision des tâches (412), segments (comptage,
  désabonnement), plafond horaire partagé, seuil et anonymat du questionnaire.
- **Règles** : RG-21, RG-22 et RG-23, un test qui les cite chacune.
- **API** : matrice des droits (fonctions du CO, bénévole, intervenant, participant) ; note
  interne absente côté intervenant ; régimes nominatifs refusés hors `logistics.read` ;
  bandeau public sans brouillon ; traceurs de fuite dans les rapports (aucun nom).
- **Exports** : CSV, XLSX (formules neutralisées, ouverture par `openpyxl`), PDF.
- **Front** : kanban au clavier, budget, questionnaire, bandeau chargé à la demande
  (bundle initial du portail inchangé), écrans.
- **E2E** (L8.10) : tâche créée et terminée ; budget avec recettes calculées ; partenaire
  publié ; « Ma venue » d'un intervenant ; régime déclaré et compté au repas ; poste de
  bénévole ; bandeau publié puis visible sur le portail ; envoi groupé reçu ;
  questionnaire répondu et résultats sous le seuil puis au-dessus ; rapport exporté.

## 8. Étapes

| Étape | Contenu | Critère de fin | Charge |
|---|---|---|---|
| L8.0 | Vérifications : `openpyxl` (licence, Python pur, ouverture par Excel et LibreOffice, injection de formules), bandeau dans le portail pré-rendu (chargement à la demande, CSP, bundle initial), partage du plafond horaire entre `BULK` et le reste, segments sur MariaDB (coût des requêtes pour 2 000 personnes), assainisseur de L2 pour les annonces | Choix consignés | 1 – 1,5 |
| L8.1 | Applications `logistics`, `sponsors`, `surveys`, `reports` ; capacités ; matrice ; registre ; `register_segment` | Matrice au vert | 2 – 2,5 |
| L8.2 | Tâches (révision, commentaires, pièces jointes, cloche, `remind_tasks`) ; budget (lignes, réalisé calculé, export) | Tests au vert | 2,5 – 3 |
| L8.3 | Partenaires : niveaux, fiches, contreparties, contributions, page publique pré-rendue | Tests au vert | 2 – 2,5 |
| L8.4 | Logistique : fiches de venue, régimes (RG-23), repas et estimation, postes et affectations de bénévoles, « Mon planning » | Tests au vert | 3 – 3,5 |
| L8.5 | Annonces (actualités, bandeau, cloche), envois groupés par segments (RG-22), désabonnement, partage du plafond | Tests au vert | 3 – 3,5 |
| L8.6 | Questionnaire : modèle, invitations, relance, réponse anonyme (RG-21), résultats, export | Tests au vert | 2,5 – 3 |
| L8.7 | Rapports : indicateurs par section, exports CSV, XLSX et PDF, fil d'activité | Tests au vert | 2,5 – 3 |
| L8.8 | Gestion : organisation (kanban, budget, activité), logistique, partenaires, communication, rapports, « Mon planning », tableau de bord, aide | Démo I côté gestion | 6 – 7 |
| L8.9 | Portail : partenaires, intervenants, actualités, bandeau, « Ma venue », régime, questionnaires, désabonnement | Démo I côté portail | 2,5 – 3 |
| L8.10 | E2E, recette, documentation, étude (§24), `CLAUDE.md` | Démo I sur o2switch | 1,5 – 2 |
| **Total L8** | | | **28,5 – 34,5** |

## 9. Risques et hypothèses non vérifiées

- **Plafond d'e-mails** : 200 par heure par défaut ; un envoi à 1 000 inscrits prend au
  moins 10 heures avec la moitié du plafond. Limites réelles d'o2switch et du fournisseur
  de production (D10) **non vérifiées** : à confirmer avant d'annoncer un délai.
- **Bundle initial du portail** : déjà au-dessus de l'avertissement (368,9 ko pour
  365 ko) ; le bandeau doit se charger à la demande, à vérifier en L8.0.
- **`openpyxl`** : supposé en Python pur et sans dépendance système (règle n° 10) ; à
  confirmer en L8.0, sinon XLSX abandonné au profit du CSV.
- **Anonymat du questionnaire** : avec quelques dizaines de répondants, un texte libre peut
  trahir son auteur ; le seuil et l'arrondi des dates limitent le reste, pas cela.
- **Régimes** : catégorie de donnée sensible selon la loi applicable (Côte d'Ivoire,
  loi 2013-450, et RGPD pour des participants européens) ; le consentement et
  l'effacement proposés sont à confirmer par le commanditaire.
- **Périmètre** : le lot est trois fois plus lourd que l'estimation de l'étude ; les
  sous-ensembles différables sont au §10, question 2.
- **o2switch** : aucune démo encore faite ; le lot L9 (P1) la prévoit.

## 10. Questions au commanditaire

1. **Ordre des lots** : L8 (P2) puis L9 (P1 : recette, sécurité, charge, restauration
   testée, première démo sur o2switch), comme l'étude ; ou L9 d'abord, aucune démo n'ayant
   encore été faite sur l'hébergement ?
2. **Périmètre de L8** : tout le lot (28,5 à 34,5 j-h), ou un sous-ensemble ? Blocs
   différables, avec leur économie : questionnaire par session (0,5 j-h), rapport PDF
   (0,5), envois groupés (2), questionnaire entier (4 à 5), restauration (1,5).
3. **Partenaires** : niveaux et montants ? Faut-il un espace partenaire en libre-service
   (hors L8 proposé) ? Les factures des partenaires sont-elles émises par la plateforme
   (dépend de Q8) ou hors plateforme (proposé) ?
4. **Régimes alimentaires** : à recueillir pour tous les inscrits (proposé) ou pour les
   intervenants seulement ? Liste des régimes à proposer ?
5. **Intervenants invités** : l'organisation réserve-t-elle voyages et hôtels (la plateforme
   suit les réservations, proposé) ? Combien d'intervenants ?
6. **Questionnaire** : anonyme (proposé) ou nominatif ? Global seul ou aussi par session ?
   Le commanditaire fournit-il les questions ?
7. **Envois groupés** : fournisseur d'e-mails de production (D10) et volume horaire
   autorisé ? Lien de désabonnement des annonces (proposé) ?
8. **Budget** : postes souhaités ? Visible du Chair et du CO « finances » seulement
   (proposé) ?
9. **Rapports** : indicateurs prioritaires ? Le PDF de synthèse est-il utile, ou le XLSX
   suffit-il ?

## 11. Bilan de L8.0 (7 octobre 2026)

**XLSX (`openpyxl`)** :

- `openpyxl` 3.1.5 et sa seule dépendance `et_xmlfile` 2.0.0 : licence MIT, **Python pur**
  (aucune extension compilée), donc compatible avec la règle n° 10 ;
- **piège vérifié** : une chaîne affectée telle quelle à une cellule et commençant par `=`
  devient une **formule** (`data_type` `f`, élément `<f>` dans le XML). En forçant le type
  texte (`data_type = "s"`), la chaîne est écrite en texte littéral (`inlineStr`), sans
  aucun élément `<f>` ; l'apostrophe des exports CSV est donc inutile en XLSX, où elle
  apparaîtrait telle quelle ;
- **précision de N13** : un module `apps/core/spreadsheet.py` étendu écrit les XLSX en mode
  « écriture seule », chaque chaîne typée texte, chaque montant en nombre (`Decimal` reconnu
  comme numérique) ; un test ouvre le fichier et vérifie l'absence d'élément `<f>` ;
- 2 000 lignes × 10 colonnes : 0,28 s, 79 ko ;
- **non vérifié ici** : l'ouverture par Excel et LibreOffice Calc (LibreOffice est installé
  sans son tableur) ; à contrôler à la recette.

**Bandeau de dernière minute dans le portail pré-rendu** (trois prototypes, build du
portail, bundle initial de référence : 368,86 ko) :

| Variante | Bundle initial | Écart |
|---|---|---|
| `@defer (on idle)` | 373,31 ko | +4,45 ko (mécanique de `@defer`) |
| `import()` dynamique et `createComponent` | 370,12 ko | +1,26 ko (code partagé redécoupé) |
| Composant chargé avec la coquille | 369,41 ko | **+0,55 ko** (+0,14 ko transférés) |

- **précision de N10** : le bandeau est un petit composant **chargé avec la coquille**
  (moins coûteux que le chargement à la demande), qui ne lit l'API que dans le navigateur
  (`afterNextRender`) : rien n'est pré-rendu, une page publiée ne fige donc jamais un
  bandeau périmé ;
- adresse : `GET /v1/public/portal/banner`, édition publique courante
  (`current_public_edition()`, comme les autres données du portail), et non un code
  d'édition dans l'adresse ;
- la CSP du portail permet déjà la lecture (`connect-src 'self'`) : aucun en-tête à
  changer ;
- **précision de N10** : le bandeau ne contient que du **texte** (titre, message de
  280 caractères au plus, lien facultatif vers l'actualité) ; il n'y a donc pas de HTML à
  assainir dans la coquille.

**Plafond horaire des e-mails** :

- l'état actuel : `GESTCONF_EMAIL_MAX_PER_HOUR` (200 par défaut) est vérifié à chaque envoi
  ; plafond atteint, le job est reporté (`RetryLater`) sans consommer de tentative ; la file
  traite les jobs par priorité (`URGENT`, `NORMAL`, puis `BULK`) ;
- **précision de N11** : les e-mails d'un envoi groupé portent la marque `bulk` ; leur
  envoi est reporté dès que les e-mails `bulk` de l'heure écoulée atteignent la moitié du
  plafond. Le plafond global reste appliqué à tous. Les e-mails de compte et de service
  gardent donc au moins la moitié du plafond ;
- **précision de N11** : les jobs d'un envoi groupé sont **étalés** dès leur création (un
  lot égal à la moitié du plafond par heure), ce qui donne la durée estimée et évite que des
  centaines de jobs ne soient réveillés pour rien.

**Segments et mise en file** (2 000 inscrits confirmés, sonde temporaire, non committée) :

| Base | Segment (une requête) | Mise en file de 500 e-mails | Pour 2 000 |
|---|---|---|---|
| SQLite | 6 ms | 0,82 s | ≈ 3,3 s |
| MariaDB 10.11 | 24 ms | 1,88 s | ≈ 7,5 s |

- le calcul d'un segment est négligeable ;
- la mise en file (rendu du gabarit, e-mail et job) est trop longue pour une requête HTTP
  sur un hébergement mutualisé : **précision de N11**, la confirmation d'un envoi crée un
  job `communications.fan_out` qui met en file **par lots de 200**, chaque lot
  idempotent (clé `announcement:<id>:<compte>`), puis se relance jusqu'à épuisement du
  segment.

**Assainisseur de L2** (`apps/portal/sanitizer.py`) :

- liste blanche adaptée aux annonces : `p`, `br`, `strong`, `em`, `ul`, `ol`, `li`, `a`
  (`http(s):`, `mailto:`, `tel:`), `h3`, `h4`, `blockquote` ; `script` et `img` retirés,
  vérifié sur un exemple ;
- **précision de N11** : la version texte de l'e-mail ne peut pas venir de `strip_tags`,
  qui perd la cible des liens et colle les éléments de liste ; un petit convertisseur sur
  la même liste blanche (paragraphes, puces « - », liens « texte (adresse) ») est ajouté à
  `communications`.

**Critère de fin** : choix consignés. Aucune dépendance n'est ajoutée à cette étape :
`openpyxl` entre dans `requirements/base.in` avec son premier usage (L8.2, export du
budget).

## 12. Bilan de L8.1 (7 octobre 2026)

**Capacités** (N2 ; `apps/accounts/roles.py`) :

- **`tasks.read`** et **`tasks.write`** : administrateur, Chair, tout le CO ;
- **`budget.read`** : administrateur, Chair, CO « finances » ; **`budget.write`** :
  administrateur, CO « finances » ;
- **`sponsors.read`** : administrateur, Chair, CO « finances », « communication »,
  « relations extérieures » ; **`sponsors.write`** : administrateur, CO « relations
  extérieures » ;
- **`logistics.read`** : administrateur, Chair, CO « logistique », « secrétariat » ;
  **`logistics.write`** : administrateur, CO « logistique » ;
- **`volunteers.plan`** : administrateur, CO « bénévoles », « logistique » ;
- **`shifts.own`** : le bénévole **seul**, l'administrateur exclu (le planning personnel est
  celui d'un bénévole, comme `sessions.chair` est celui d'un président de séance) ;
- **`communications.send`** : administrateur, Chair, CO « communication » ;
- **`surveys.manage`** : administrateur, Chair, CO « communication », « secrétariat ».

Aucun rôle nouveau, aucune 2FA nouvelle ; `SPONSOR` reste non invitable.

**Applications** : `logistics`, `sponsors`, `surveys` et `reports` créées et déclarées
(`INSTALLED_APPS`).

- **Écart avec le §3 du plan, comme en L7.1** : les modèles arrivent avec leurs services
  (L8.2 à L8.6), par migrations additives, plutôt que vides dès L8.1 ; le registre des
  données personnelles de chaque modèle arrive avec lui.

**Registre des segments** (N1, N11 ; `apps/communications/segments.py`) :

- `register_segment(Segment(code, libellé, requête, position, capacité))`, déclaré par les
  applications métier dans leur `ready()` : `communications` ne dépend d'aucune d'elles ;
- un segment peut exiger une capacité en plus de `communications.send` (« relecteurs en
  retard » : `reviews.manage`) ;
- `recipients()` ne garde que les comptes actifs et non anonymisés, chacun une fois ;
- les segments eux-mêmes sont déclarés en L8.5, avec les annonces.

**Matrice des droits** : la spécification recopiée à la main (`tests/test_matrix.py`) reçoit
les capacités de L8 pour chaque profil ; le test qui compare les capacités lues par `/v1/me`
à la spécification passe.

**Tests** :

- `tests`, `accounts` et `communications` : **4 020 réussis**, 1 ignoré (SQLite) ; dont
  3 tests du registre des segments ;
- front : 456 tests (shared 79, portail 158, gestion 219) ; vérification des types des trois
  projets après régénération du client ;
- `ruff`, `format:check`, `locale/check.sh` ; schéma validé sous MariaDB (énumération
  `Capability` étendue) ; client TypeScript régénéré.

**Critère de fin** (« Matrice au vert ») : atteint.
