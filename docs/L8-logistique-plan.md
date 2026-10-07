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

## 13. Bilan de L8.2 (7 octobre 2026)

**Tâches du CO** (N3 ; `apps/logistics`, services `tasks` et `reminders`) :

- `Task` (titre, description, statut, priorité, étiquette, responsable, échéance, position,
  révision, créée par, terminée le, archivée le), `TaskComment`, `TaskAttachment` ;
- **responsable** : membre actif de l'édition dont un rôle donne `tasks.write`
  (administrateur, Chair, CO), rôles **tirés de la table des capacités**, jamais recopiés ;
  un relecteur, un bénévole, un rôle retiré ou une autre édition sont refusés ;
- chaque écriture verrouille la tâche, compare la révision (`If-Match`, 412
  `stale_revision`), l'incrémente et écrit le journal `task.*` (avant et après) ;
- kanban : déplacer une tâche renumérote sa colonne d'arrivée et resserre celle qu'elle
  quitte ; « terminée » date la fin, rouvrir l'efface ;
- archivage et restauration, jamais de suppression ;
- commentaires (2 000 caractères ; le journal ne garde pas leur texte) ;
- pièces jointes : PDF, PNG ou JPEG de 10 Mo au plus, 20 par tâche, type vérifié par
  contenu, stockage privé (règle n° 8), téléchargement authentifié et sans cache ;
  orphelins purgés par `cleanup`, fichiers absents ou modifiés signalés par
  `check_integrity` ;
- **cloche** : `task_assigned` au nouveau responsable (pas à soi-même) ; son libellé dans
  l'espace compte arrive avec les écrans (L8.8, L8.9) ;
- **`remind_tasks`** (cron quotidien, 6 h 53) : un récapitulatif par responsable et par
  édition, une fois par jour, des tâches en retard ou à échéance sous deux jours, la date du
  jour étant lue **dans le fuseau de l'édition** ; idempotent (date du dernier récapitulatif
  sur la tâche, clé d'idempotence de l'e-mail) et verrouillé.

**Budget** (N4 ; service `budget`) :

- `BudgetLine` : nature, poste (catalogue fermé de N4, cohérent avec la nature), libellé,
  prévu, réalisé, origine, note, justificatif, position ;
- montants en `Decimal` **exacts dans la devise de l'édition** (XOF sans décimale), positifs,
  bornés ;
- **réalisé calculé** : la ligne « inscriptions » est créée d'office ; son réalisé est
  l'encaissé net des paiements de L6 (paiements réussis moins remboursements,
  `payments.services.finance.net_collected`, ajoutée) ; ni réalisé, ni nature, ni poste
  n'y sont modifiables, et elle ne se supprime pas ; la source « partenaires » s'inscrit en
  L8.3 (`register_computed_source`) ;
- **précision de N1** : `logistics` lit `payments` (import différé, lecture seule) ;
  `payments` ne dépend pas de `logistics` ;
- synthèse : totaux prévus et réalisés par nature et par poste, soldes ;
- justificatif PDF, PNG ou JPEG de 5 Mo, privé ;
- journal `budget.*` ; **export CSV et XLSX** journalisé, avec réauthentification récente.

**XLSX** : `openpyxl` 3.1.5 ajouté à `requirements/base.in` (fichiers verrouillés
recompilés, seules ses deux entrées s'ajoutent) ; `xlsx_bytes` et `xlsx_response` dans
`apps/core/spreadsheet.py`, chaînes typées texte (test : aucun élément `<f>`, même pour
`=SOMME(A1)`).

**API** (gestion, 2FA) :

- `…/tasks` (liste filtrée : statut, responsable, « mes tâches », archivées ; création),
  `…/tasks/members`, `…/tasks/{id}` (lecture, mise à jour en `If-Match`), `…/archive`,
  `…/restore`, `…/comments`, `…/attachments` (dépôt), `…/attachments/{id}` (lecture,
  retrait) ;
- `…/budget` (synthèse et lignes), `…/budget/lines` et `…/budget/lines/{id}`,
  `…/budget/lines/{id}/proof`, `…/budget/export?file_format=csv|xlsx`.

**Défauts trouvés en écrivant les tests** :

- le paramètre `format` de l'export était capté par la négociation de contenu de DRF
  (réponse 404) : il s'appelle `file_format` ;
- une méthode `detail` des vues masquait l'attribut du même nom des viewsets de DRF :
  renommée.

**Données personnelles** : tâches confiées ou créées, commentaires et pièces jointes de la
personne à l'export ; à l'anonymisation, rien n'est effacé (documents de travail du comité,
le compte anonymisé n'affichant plus de nom).

**Exploitation** : `remind_tasks` ajoutée à `deploy/cron.sh` (liste fermée) et à
`deploy/README.md`.

**Défaut trouvé par la suite complète** : l'objet du récapitulatif affichait le titre de
l'édition ; or l'objet d'un e-mail est conservé après la purge des corps et n'affiche que le
nom du site (test de plateforme). Corrigé.

**Tests** :

- backend : **5 360 réussis**, 10 ignorés (SQLite) ; sous MariaDB, `logistics`, l'export
  XLSX, le registre, les règles de plateforme, la file d'e-mails et la matrice des tâches et
  du budget réussissent (480) ;
- `logistics` et XLSX : 23 tests (tâches : responsable, validation, révision, kanban,
  archivage, commentaires, pièces jointes et leurs limites, intégrité ; récapitulatif :
  regroupement, fuseau de l'édition, idempotence, commande ; budget : validation dans la
  devise, ligne calculée, synthèse, journal, justificatif, API et export) ;
- matrice des droits : **4 108 cas** (3 746 à la fin de L8.1), dont l'édition archivée en
  lecture seule et la réauthentification de l'export ;
- `ruff`, `locale/check.sh`, schéma validé sous MariaDB, client TypeScript régénéré,
  vérification des types des trois projets du front.

**Critère de fin** (« Tests au vert ») : atteint.

## 14. Bilan de L8.3 (7 octobre 2026)

**Partenaires** (N5 ; `apps/sponsors`) :

- `SponsorLevel` (public) : noms FR et EN, montant indicatif, contreparties FR et EN, taille
  du logo, ordre ; supprimé seulement s'il n'est attribué à personne ;
- `Sponsor` : partie publique (nom, niveau, logo, site, présentations FR et EN, publié,
  ordre) et partie privée (contact, statut, contribution convenue, montant reçu et date,
  note interne) ;
- `SponsorBenefit` : contreparties, recopiées du niveau à l'attribution (une par ligne),
  cochées à leur livraison, ajoutées ou retirées une à une ;
- montants en `Decimal` exacts dans la devise de l'édition ; « contribution reçue » exige un
  montant et une date (`check_integrity` le revérifie) ;
- **budget** : la ligne « partenariats » est calculée, total reçu hors refus
  (`register_computed_source`, déclarée par `sponsors`).

**Logo** :

- nouvelle nature de fichier public **`logo`** (migration `core/0005`) : réencodé sans
  métadonnées, 600 px au plus, servi par l'adresse publique des fichiers (L2) **une fois le
  partenaire publié**, sa publication suivant celle du partenaire ;
- **précision de N5** : absent de l'écran des fichiers du portail (qui ne liste que ses
  natures), donc ni modifiable ni supprimable par là ; remplacé ou supprimé avec le
  partenaire.

**Page publique** : `GET /v1/public/sponsors` (édition publique courante, cache de 5 min)
renvoie les niveaux dans l'ordre et leurs partenaires publiés, plus ceux sans niveau, par
**liste blanche** : nom, site, présentations, logo ; ni contact, ni montant, ni statut, ni
note (test). La page du portail arrive en L8.9.

**Modifications non publiées du portail** (L2) :

- les actions `sponsor_level.*` comptent ;
- une action `sponsor.*` compte quand elle porte `public: true` : partie publique d'un
  partenaire publié, publication ou retrait, logo, suppression d'un partenaire publié ;
- un montant, un contact, une note ou un partenaire non publié ne comptent pas (test).

**Défaut évité, précision de N3 à N5** : le journal refuse toute adresse e-mail en clair. Les
textes libres journalisés (titre et description de tâche, nom de pièce jointe, libellé et
note de budget, présentation d'un partenaire, contreparties) passent par `mask_emails`
(nouvelle fonction de `apps/core/audit.py`, `j***@univ.ci`) ; sans cela, une description
contenant une adresse aurait fait échouer l'écriture. Le **contact** d'un partenaire n'est
jamais journalisé : seul `contact_changed` figure au journal (test).

**API** (gestion, 2FA) : `…/sponsors` (liste et totaux par statut, création),
`…/sponsors/export?file_format=csv|xlsx` (contacts compris : réauthentification, journal),
`…/sponsors/{id}` (lecture, modification, suppression), `…/sponsors/{id}/logo` (dépôt,
retrait), `…/sponsors/{id}/benefits` et `…/benefits/{id}`, `…/sponsor-levels` et
`…/sponsor-levels/{id}`.

**Données personnelles** : le contact d'un partenaire n'est pas un compte de la plateforme ;
il est corrigé ou effacé avec la fiche. Son adresse étant un `EmailField`, le modèle est
**exempté** du registre avec cette justification (le test d'introspection l'exige).

**Défauts trouvés par la suite complète** : l'exemption ci-dessus manquait ; le test de
synthèse du budget ignorait la nouvelle ligne calculée « partenariats ». Corrigés.

**Tests** :

- backend : **5 654 réussis**, 10 ignorés (SQLite) ; sous MariaDB, `logistics`, `sponsors`,
  `portal`, `core`, le registre, les règles de plateforme et la matrice des tâches, du
  budget et des partenaires réussissent (1 122) ;
- `sponsors` : 7 tests (niveaux et contreparties, contact absent du journal, contribution
  reçue et budget, page publique en liste blanche, logo et publication, modifications non
  publiées du portail, API et export) ;
- `logistics` : test du masquage des adresses au journal ;
- matrice des droits : **4 394 cas** ;
- `ruff`, `locale/check.sh`, schéma validé sous MariaDB, client TypeScript régénéré,
  vérification des types des trois projets du front.

**Critère de fin** (« Tests au vert ») : atteint.

## 15. Bilan de L8.4 (7 octobre 2026)

**Fiches de venue des intervenants invités** (N6 ; `SpeakerVisit`, `apps/logistics/services/visits.py`) :

- une fiche par intervenant invité (rôle `SPEAKER` actif) et par édition, créée à sa
  première écriture ;
- **part de l'intervenant** (`SPEAKER_FIELDS`) : besoins techniques (catalogue fermé des
  équipements de salle de L5) et précisions, arrivée et départ (moyen, vol ou train),
  hébergement et transfert demandés, demandes ;
- **part du CO** (`STAFF_FIELDS`) : hôtel, nuits (arrivée et départ de l'hôtel), statut de
  la prise en charge (`to_arrange`, `booked`, `confirmed`), note interne ;
- arrivée et départ **saisis en heure locale de l'édition** (`arrival_local`,
  `departure_local`, D13), stockés en UTC ; départ après l'arrivée, sortie de l'hôtel après
  l'entrée ;
- l'intervenant n'écrit que sa part : un champ du CO envoyé par lui est ignoré par l'API
  (son sérialiseur ne le connaît pas) et refusé par le service (« champ non modifiable »),
  et la note interne n'est **jamais** servie par `GET /v1/me/editions/{id}/visit` (test) ;
  il lit l'hôtel et le statut réservés pour lui ;
- **signal** : besoin technique absent de l'équipement d'une salle où l'intervenant passe,
  lu dans le **dernier programme publié** (instantané de L5), jamais dans le brouillon ;
- journal `visit.updated` : la liste des champs changés, **sans valeur** (références de vol
  et notes restent hors du journal).

**Régimes alimentaires** (N7, **RG-23** ; `DietaryDeclaration`, `services/dietary.py`) :

- peuvent déclarer : les personnes qui ont un rôle actif dans l'édition ou une inscription en
  attente ou confirmée ;
- **consentement explicite exigé à chaque écriture** (horodaté), retrait à tout moment par
  `DELETE` (la déclaration est effacée) ;
- catalogue fermé (végétarien, végétalien, sans porc, sans gluten, sans lactose, autre) et
  allergies en texte libre (200 caractères) ;
- le journal garde l'acte (`dietary.declared`, `dietary.withdrawn`), **jamais le contenu** ;
- gestion : effectifs **agrégés** (`…/logistics/dietary`) ; liste nominative par
  `…/logistics/dietary/export` seulement (`logistics.read`, **réauthentification**, journal
  `dietary.exported`) ;
- **effacement** 30 jours après la fin de l'édition ou à son archivage : tâche de
  conservation `logistics.dietary` de `cleanup` (même règle que les numéros de passeport de
  L7), et `logistics.visits` pour les fiches de venue.

**Restauration** (N8 ; `Meal`, `services/meals.py`) :

- repas : jour (dans les dates de l'édition), type (pause café, déjeuner, dîner, cocktail),
  libellés FR et EN, public (inscrits confirmés, ou seulement les titulaires d'une **option**
  de L6 ; intervenants, comités, bénévoles à cocher), marge de 0 à 50 % ;
- **estimation calculée** : personnes du public **comptées une fois** (une même personne
  inscrite et membre d'un comité ne compte qu'une fois), marge arrondie au supérieur,
  total à commander, répartition par régime et nombre d'allergies, **sans nom** ;
- export pour le traiteur en CSV et XLSX (`…/logistics/meals/export`), agrégé ;
- **écart** : l'export **PDF** de N8 rejoint les rapports PDF de L8.7 (même générateur
  `fpdf2`), pour ne pas écrire deux mises en page.

**Bénévoles** (N9 ; `VolunteerShift`, `ShiftAssignment`, `services/shifts.py`) :

- postes : intitulés FR et EN, lieu, début et fin **en heure locale de l'édition**, nombre de
  bénévoles nécessaires (1 à 100), consignes ;
- affectation des seuls bénévoles (`VOLUNTEER` actif) de l'édition, ré-affectation sans
  effet ;
- **chevauchement refusé** pour une même personne, à l'affectation comme au déplacement d'un
  poste déjà pourvu (nouveau code d'erreur `shift_overlap`, 409) ; le compte du bénévole est
  verrouillé le temps de la vérification, de sorte que deux affectations simultanées ne
  passent pas toutes les deux ;
- tableau du coordinateur : postes, bénévoles affectés et **places manquantes** ;
- **cloche** à chaque affectation (`shift_assigned`) et à chaque retrait (`shift_removed`),
  y compris par la suppression d'un poste pourvu (migration `communications/0007`) ;
- **« Mon planning »** (`shifts.own`) : `…/me/shifts` et son fichier iCal
  `…/me/shifts/calendar` (générateur de L5).

**API** :

- gestion (2FA) : `…/logistics/visits` et `…/visits/{user_id}`, `…/logistics/dietary` et
  `…/dietary/export`, `…/logistics/meals`, `…/meals/export` et `…/meals/{id}`,
  `…/logistics/shifts`, `…/shifts/{id}`, `…/shifts/{id}/assignments` et
  `…/assignments/{volunteer_id}`, `…/me/shifts` et `…/me/shifts/calendar` ;
- compte (portail) : `/v1/me/editions/{id}/visit` (lecture, modification) et
  `/v1/me/editions/{id}/dietary` (lecture, déclaration, retrait).

**Données personnelles** : les fiches de venue, les déclarations de régime et les postes
d'un bénévole entrent dans l'export « Mes données » ; l'anonymisation d'un compte efface ses
fiches de venue et ses déclarations ; registre à jour.

**Reporté** :

- la page publique **« Intervenants »** de N6, construite depuis l'instantané publié du
  programme, rejoint L8.9 avec les autres pages du portail (son API comprise) ;
- les écrans (gestion et « Ma venue » du portail) arrivent en L8.8 et L8.9, avec les textes
  de la cloche pour `task_assigned`, `shift_assigned` et `shift_removed`.

**Tests** :

- `logistics` : 34 tests, dont RG-23 (consentement et éligibilité, journal sans contenu,
  retrait, agrégats, export nominatif réauthentifié, effacement à 30 jours, API du compte),
  N6 (part de l'intervenant en heure locale, note interne jamais servie, seuls les
  intervenants, équipement manquant d'après le programme publié), N8 (personnes comptées
  une fois, marge, régimes, option, export sans nom) et N9 (chevauchement, retraits et
  cloche, « Mon planning » et iCal, édition archivée) ;
- matrice des droits : 18 cas de logistique ;
- `ruff`, `locale/check.sh`, schéma validé sous MariaDB (énumérations `TravelMeans`,
  `VisitStatus`, `Diet`, `MealKind` nommées), client TypeScript régénéré, vérification des
  types des trois projets du front.

## 16. Bilan de L8.5 (7 octobre 2026)

**Annonces** (N10 ; `communications.Announcement`, `apps/communications/announcements.py`) :

- titre et texte FR et EN, texte en HTML **assaini** par la liste blanche de L2 ; l'anglais
  vide retombe sur le français ;
- canaux cochés : actualités, bandeau, cloche, e-mail ; la cloche et l'e-mail exigent un
  **segment**, les actualités et l'e-mail un texte ;
- brouillon, publication, retrait ; seul un brouillon se supprime ; une fois publiée, la
  cloche, l'e-mail et le segment ne changent plus (l'envoi est parti), le reste se corrige ;
- journal `announcement.*` (création, modification, publication, envoi, essai, retrait,
  annulation, désabonnement), textes libres masqués (`mask_emails`).

**Bandeau de dernière minute** :

- texte seul (titre, message de 280 caractères, lien vers l'actualité quand l'annonce en
  est une), entre un début et une fin **saisis en heure locale de l'édition** (D13) ;
- **une seule annonce au bandeau à la fois** : deux fenêtres qui se chevauchent sont
  refusées à la publication (nouveau code `banner_overlap`, 409) ;
- `GET /v1/public/portal/banner` (édition publique courante, bilan de L8.0) : réponse par
  liste blanche, `{"banner": null}` sinon, cache de 60 s, limité à 60 lectures par minute et
  par adresse IP ; visible **aussitôt**, sans publication du portail.

**Actualités** : `GET /v1/public/news` (cache de 5 min), lu au build du portail ; une
actualité publiée, modifiée ou retirée compte dans les **modifications non publiées** du
portail (`announcement.*` portant `public: true`) ; une annonce sans actualité ne compte pas
(test).

**Envois groupés** (N11, **RG-22**) :

- **segments** déclarés par les applications (`register_segment` dans leur `ready()`) :
  auteurs (soumission envoyée, acceptés), présentateurs et présidents de séance (lus dans le
  **programme publié**, jamais dans le brouillon), relecteurs (affectation active) et
  relecteurs en retard (**réservé à `reviews.manage`**), inscrits (confirmés, en attente de
  paiement), présents (pointage non annulé), intervenants invités, comité scientifique,
  comité d'organisation, bénévoles ;
- « acceptés » ne lit que des statuts posés à la **publication** des décisions (RG-09) ;
- avant l'envoi : `…/segments` (catalogue autorisé et nombre de destinataires) ;
  `…/announcements/{id}/preview` (e-mail rendu, destinataires, désabonnés, e-mails, durée
  estimée) ; `…/announcements/{id}/test` (le message, marqué « Essai », à la seule personne
  qui le demande) ;
- **publication** : réauthentification récente exigée ; destinataires comptés ; journal
  `announcement.sent` (segment, nombre : action de masse, RG-17) ; job
  `communications.fan_out` ;
- **mise en file par lots de 200** (bilan de L8.0) : une ligne `AnnouncementDelivery` par
  destinataire (unique), une cloche, un e-mail de clé `announcement:<id>:<compte>` ; un lot
  rejoué ne renotifie ni ne réenvoie (test) ; le lot suivant est remis en file tant qu'il
  reste des destinataires ;
- **un e-mail par personne**, jamais de copie, dans la langue du compte, avec la raison de
  l'envoi (« au titre de … pour … ») et le lien de désabonnement ; les liens internes du
  texte sont rendus absolus ; version texte par le convertisseur
  (`apps/communications/text.py`) qui garde les liens, les puces, les numéros et les
  citations ;
- **plafond** : marque `is_bulk` sur l'e-mail (`OutboxEmail`, champ ajouté), file `BULK` ;
  un e-mail groupé attend dès que les e-mails groupés de l'heure écoulée atteignent **la
  moitié** de `GESTCONF_EMAIL_MAX_PER_HOUR` ; le plafond global reste appliqué à tous ;
  les e-mails d'un envoi sont **étalés** dès leur création (un lot égal à la moitié du
  plafond par heure), d'où la durée estimée ;
- **annulation** de ce qui n'est pas encore parti (`…/cancel`, et au retrait de
  l'annonce) : mise en file arrêtée, e-mails en file annulés, ceux partis restent comptés ;
- avancement : destinataires, traités, e-mails mis en file, partis, en file, en échec,
  annulés, heures restantes.

**Précisions de N11** :

- l'**objet** de l'e-mail est générique (« [site] Annonce de la conférence ») : la règle de
  L1 (§8.3, testée) n'admet dans un objet que le nom du site, l'objet survivant à la purge
  des corps ; le titre ouvre le corps du message ;
- **toute** publication exige une réauthentification, et pas seulement celle qui envoie :
  le bandeau s'affiche aussitôt, et la vérification ne dépend plus des canaux cochés ;
- pas d'en-tête `List-Unsubscribe` : le registre d'envoi ne stocke pas d'en-têtes ; à
  envisager si le volume dépasse les seuils des messageries (**non vérifié**).

**Désabonnement** :

- jeton **signé** (`django.core.signing`, sel propre) portant le compte et l'édition, sans
  expiration ; lien `/desabonnement/<jeton>` du portail (page en L8.9) ;
- `POST /v1/public/announcements/unsubscribe` : public, **CSRF imposé**, limité à 30
  par heure et par adresse IP ; rejouer le lien est sans effet ; jeton altéré : 400
  `unsubscribe_link_invalid` ;
- dans le compte : `GET/PUT /v1/me/editions/{id}/announcements` (abonné ou non) ;
- un désabonné reçoit encore la cloche de l'annonce, plus son e-mail ; les e-mails de
  service restent envoyés.

**Données personnelles** : export « annonces reçues » et « désabonnements » ;
l'anonymisation efface les désabonnements, les livraisons restent rattachées au compte
anonymisé ; registre à jour (`communications.announcements`).

**Tests** :

- `communications` : 17 tests d'annonces (assainissement et canaux, version texte, RG-22 :
  un e-mail par personne dans sa langue avec raison et lien, désabonné sans e-mail, journal
  de masse ; lots idempotents et étalement ; moitié du plafond ; annulation et retrait ;
  segment réservé ; réauthentification, aperçu et essai ; bandeau minimal et unique ;
  actualités et portail ; désabonnement ; segments déclarés ; auteurs ; inscrits ;
  relecteurs en retard et présents ; programme publié ; export des données) ;
- matrice des droits : 11 cas d'annonces et de segments (édition archivée et
  réauthentification comprises) ; liste blanche des vues anonymes et CSRF des vues
  publiques à jour ;
- `ruff`, `locale/check.sh`, schéma validé sous MariaDB, client TypeScript régénéré,
  vérification des types des trois projets du front.

## 17. Bilan de L8.6 (7 octobre 2026)

**Questionnaires** (N12 ; `apps/surveys`) :

- questionnaire **global** de l'édition ou d'une **session** (la portée et la session sont
  vérifiées par contrainte) ; titres et introduction FR et EN ;
- questions : note de 1 à 5, choix unique, choix multiples (2 à 12 choix numérotés par le
  serveur), texte libre de 1 000 caractères au plus ; obligatoires ou non ;
- **modèle par défaut** proposé à la création : organisation, programme, lieu, accueil,
  recommandation (notes) et commentaire (texte) ;
- ouverture et clôture **saisies en heure locale de l'édition** (D13) ; publication sous
  **réauthentification** (elle programme les invitations de toutes les personnes
  présentes) ; une fois publié, seuls les titres, l'introduction et la clôture changent ;
- questions **verrouillées** dès la première réponse (`survey_locked`) : on **duplique** le
  questionnaire, comme une grille (RG-05).

**Invitations et relance** (N12, N17) :

- invités : les personnes **présentes** (pointage non annulé de L7, n'importe où pour un
  questionnaire global, à l'entrée de la session pour un questionnaire de session) ;
- deux tâches datées de `run_jobs`, sans ligne de cron nouvelle : `surveys.invite` à
  l'**ouverture** (cloche `survey_invitation` et e-mail), puis `surveys.remind` ;
- **précision de N12** : l'**unique relance** part **à mi-chemin** de l'ouverture et de la
  clôture, par e-mail, aux seules personnes qui n'ont pas répondu ;
- par lots de 200, idempotents (une invitation par personne ; clés d'e-mail
  `survey:<id>:invite:<compte>` et `survey:<id>:remind:<compte>`) ;
- e-mails **groupés** (marque `bulk` de L8.5 : moitié du plafond horaire, étalés) ; ce sont
  des e-mails de service, liés à la présence de la personne : le désabonnement des
  annonces ne les arrête pas ;
- l'e-mail annonce l'anonymat et prévient que les commentaires libres seront lus par le
  comité.

**Anonymat (RG-21)** :

- la réponse (`SurveyResponse`) n'a **aucune clé** vers un compte ni vers l'invitation ;
  sa clé primaire est un **UUID aléatoire**, de sorte que l'ordre d'insertion ne se lit
  pas dans la table ;
- **précision de N12, plus stricte que le plan** : la réponse ne porte **aucune date**. Le
  plan prévoyait un jour de réponse sur la réponse comme sur l'invitation ; or la seule
  personne qui a répondu un jour donné aurait été retrouvée en rapprochant les deux jours.
  Seule l'invitation garde le **jour** de la réponse, sans horodatage précis (le modèle
  n'hérite pas de `TimeStampedModel`) ;
- l'invitation est marquée « répondu » dans la **même transaction** que l'enregistrement
  de la réponse ; verrouillage dans le même ordre que la relance (questionnaire, puis
  invitation), sans interblocage ;
- **rien au journal** ne relie une personne à une réponse (test : aucune entrée
  `survey.answer…`, aucun identifiant de réponse) ; une réponse par personne
  (`survey_answered`) ; hors fenêtre ou sans invitation : `survey_not_open` ;
- résultats agrégés **à partir de 5 réponses** (`survey_threshold` en dessous, à
  l'export) : moyenne en `Decimal` et répartition des notes, décompte par choix, nombre
  de textes ;
- export CSV ou XLSX journalisé : agrégats, puis textes libres dans un **ordre
  aléatoire** (`random.SystemRandom`).

**Intégrité** : `check_integrity` vérifie qu'un questionnaire a autant de réponses que
d'invitations marquées « répondu », et qu'un brouillon n'en a aucune (N17).

**Données personnelles** : les invitations entrent dans l'export « Mes données » (jour
d'invitation, de relance, de réponse) ; les réponses, liées à personne, n'y figurent pas
(test) ; l'anonymisation laisse les invitations rattachées au compte anonymisé.

**API** :

- gestion (`surveys.manage`, 2FA) : `…/surveys` (liste avec invités, réponses et seuil,
  création), `…/surveys/{id}` (lecture, modification, suppression d'un brouillon),
  `…/publish`, `…/duplicate`, `…/questions` et `…/questions/{id}`, `…/results`,
  `…/export?file_format=csv|xlsx` ;
- compte : `GET /v1/me/surveys`, `GET` et `POST /v1/me/surveys/{id}` (404 pour qui n'est
  pas invité). Les écrans (gestion, `/compte/questionnaires/{id}` du portail) arrivent en
  L8.8 et L8.9.

**Défauts trouvés et corrigés pendant l'étape** :

- la CI de L8.4 a échoué sur le test des traductions communes du front, qui exige un
  libellé FR et EN pour chaque code d'erreur de l'API (`shift_overlap`) : correctif poussé
  à part, et les tests des trois projets du front sont désormais lancés avant chaque
  envoi ; les codes de L8.5 et de L8.6 sont traduits ;
- le test qui fige les limites de débit ignorait les deux portées de L8.5 : mis à jour.

**Tests** :

- `surveys` : 9 tests (modèle par défaut et tâches programmées ; invitations par cloche et
  e-mail, une seule relance ; questionnaire de session ; **RG-21** : colonnes de la table
  des réponses, UUID, journal, réponse unique ; validation et verrouillage, duplication ;
  questionnaire fermé ; seuil de 5 et textes mélangés ; API de la personne et du comité ;
  export des données) ;
- matrice des droits : 12 cas de questionnaires ; sous MariaDB, `surveys`,
  `communications`, le registre et les cas de la matrice réussissent ;
- `ruff`, `locale/check.sh`, schéma validé sous MariaDB, client TypeScript régénéré,
  vérification des types et tests des trois projets du front.

## 18. Bilan de L8.7 (7 octobre 2026)

**Rapports** (N13 ; `apps/reports`, sans modèle, en lecture seule) :

| Section | Capacité exigée | Tableaux |
|---|---|---|
| Soumissions | `submissions.read` | par statut ; envoyées, acceptées et taux par thématique, par type, par pays du premier auteur |
| Relecture | `reviews.manage` | affectations, évaluations envoyées, retards, délai moyen (jours), en tout et par thématique |
| Inscriptions | `registrations.read` | par statut ; confirmées par semaine (ISO, fuseau de l'édition), par catégorie, par zone, par pays |
| Recettes | `finance.read` | encaissé, remboursé, net, en attente ; par moyen ; par catégorie |
| Présence | `registrations.read` | présents par jour et taux ; entrées par session et remplissage de la salle |
| Satisfaction | `surveys.manage` | taux de réponse ; notes moyennes, seulement à partir de 5 réponses (RG-21) |
| Budget | `budget.read` | prévu, réalisé et écart par nature et par poste ; solde |
| Partenaires | `sponsors.read` | par statut ; par niveau (hors refus) : nombre, convenu, reçu |

- **aucune donnée nominative** : décomptes, taux, moyennes et montants agrégés seulement
  (tests : ni nom ni adresse dans les tableaux) ; « acceptées » ne lit que les statuts posés
  à la publication des décisions (RG-09) ;
- taux et moyennes en `Decimal` arrondis au dixième (ou au centième pour les notes),
  servis en chaînes par l'API, jamais en flottant ;
- **droits** : la lecture de l'édition ouvre l'écran ; chaque section est vérifiée côté
  serveur contre sa capacité (403 sinon, 404 pour une section inconnue) ;
- **précision de N13** : la présence est réservée à `registrations.read` ; le plan disait
  « `checkin.manage` ou `registrations.read` », mais tous les détenteurs de
  `checkin.manage` ont aussi `registrations.read` (matrice), et une capacité unique par
  section garde le contrôle simple.

**Exports** (`…/reports/{section}/export?file_format=csv|xlsx|pdf`, journalisés
`report.exported`) :

- CSV : les tableaux à la suite, chacun précédé de son titre ; cellules neutralisées contre
  l'injection de formules ;
- XLSX : **une feuille par tableau** (`xlsx_workbook`, nouveau dans
  `apps/core/spreadsheet.py` : titres de feuilles rendus valides et uniques ; chaînes
  typées texte, nombres en nombres, comme en L8.0) ;
- PDF de synthèse `fpdf2` (`apps/reports/pdf.py`, police DejaVu embarquée) ; il sert aussi
  la **commande au traiteur** en PDF (`…/logistics/meals/export?file_format=pdf`), reportée
  de L8.4.

**Fil d'activité du CO** (N14 ; `…/activity`, `tasks.read`) : les 50 dernières entrées du
journal de l'édition, restreintes à une **liste blanche** (tâches, postes de bénévolat,
repas, publication et retrait d'annonces, publication d'un questionnaire, du programme, du
portail, changement de statut de l'édition) ; chaque entrée ne donne que l'action, sa date,
le nom de qui l'a faite et l'objet visé, **jamais les valeurs avant et après** ; ni
décision, ni identité d'auteur, ni montant (test : un export de régimes ou une ligne de
budget n'y figurent pas).

**API** (gestion, 2FA) : `…/reports` (sections ouvertes au compte), `…/reports/{section}`
(tableaux : titre, colonnes, lignes en chaînes), `…/reports/{section}/export`,
`…/activity`. Les écrans (barres CSS ou SVG doublées de leur tableau) arrivent en L8.8.

**Défaut évité pendant l'étape** : dans le corps de la vue, `list(FORMATS)` désignait la
méthode `list` de la classe et non la fonction native ; l'énumération du schéma passe par
une constante de module.

**Tests** :

- `reports` : 6 tests (soumissions par pays et taux sans nom ; inscriptions, recettes et
  présence ; satisfaction sous et au-dessus du seuil de 5 réponses ; sections selon les
  capacités, 403 et 404, exports CSV, XLSX à une feuille par tableau et PDF, journal ;
  fil d'activité en liste blanche sans valeurs ; commande au traiteur en PDF) ;
- matrice des droits : 10 cas (liste, une section par capacité, export PDF, fil
  d'activité) ;
- `ruff`, `locale/check.sh`, schéma validé sous MariaDB, client TypeScript régénéré,
  vérification des types et tests du front.
