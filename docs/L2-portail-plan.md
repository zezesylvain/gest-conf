# Lot L2 — Portail public : plan d'implémentation

> **Statut : proposition v1 (5 octobre 2026), à valider.** Rien n'est implémenté avant la
> validation des décisions E1 à E12 (`CLAUDE.md` : plan d'abord pour toute modification large
> du modèle de données ou des permissions).
>
> Sources : étude §4 (M1, M2), §10.1, §10.4, §14 (L2 : « Pages, appel à communications, dates,
> comités, programme public (lecture), pré-rendu », 10 à 14 j-h) ; plan L1 §1.3 (reports vers
> L2) et §1.4 (prérequis) ; décisions D1 à D18, D16 (anti-robots), D18 (déploiement continu).

## En bref

| | |
|---|---|
| **Objectif** | Un site vitrine bilingue, pré-rendu, à jour et bien référencé pour l'édition courante : accueil, présentation et thématiques, appel à communications (règles, formats, modèles de documents, dates), dates clés, comités, informations pratiques ; plus, dans la gestion, l'édition de ces contenus. |
| **Point dur** | Le portail est **pré-rendu au build** (SSG, pas de serveur Node), alors que ses contenus vivent en base et changent souvent. Recommandation : instantané des données pris au build depuis l'API publique de production, puis rafraîchissement dans le navigateur (E1). |
| **Hors périmètre** | Programme, intervenants, inscriptions et tarifs : leurs données n'existent qu'en L5 et L6 ; le portail leur réserve une page « à venir » éditable (E6). Contact, FAQ, actualités, sponsors (P2). Archives des éditions (P3). |
| **Charge** | **12,5 à 16 j-h** (étude : 10 à 14). L'écart vient des fichiers publics (classe nouvelle, règle n° 8) et des deux langues pré-rendues. |
| **Démo C** | Le président publie le portail (FR et EN) : textes de présentation et de l'appel, deux modèles de documents, dates, comités ; un visiteur anonyme le consulte, le télécharge, le partage (aperçu Open Graph) ; un membre qui a refusé l'annuaire n'apparaît pas. |

## 1. Périmètre

### 1.1 Fonctions de M1 couvertes

| Fonction (M1) | Priorité | L2 |
|---|---|---|
| Accueil : thème, dates, lieu, compte à rebours, appels à l'action | P1 | Oui |
| Présentation de la conférence et des thématiques | P1 | Oui |
| Appel à communications : règles, formats, modèles de documents, dates clés | P1 | Oui |
| Dates importantes | P1 | Oui |
| Comités scientifique et d'organisation (photos, affiliations, pays) | P1 | Oui, avec consentement (E5) |
| Programme public | P1 | **Page « à venir »** ; données en L5 (E6) |
| Intervenants invités | P1 | **Page « à venir »** ; données en L5 / M10 (E6) |
| Inscription et tarifs | P1 | **Page « à venir »** ; données en L6 (E6) |
| Lieu, accès, hébergement, visas | P2 | Oui, en contenu éditorial (coût marginal, même mécanisme) |
| Sponsors, actualités, FAQ, contact | P2 | Non (contact : formulaire et anti-robots D16 en L3 au plus tôt) |
| Actes, archives, galerie | P3 | Non ; l'URL `/editions/<slug>/` est réservée (E10) |

Contraintes de l'étude : pages pré-rendues, Open Graph, plan de site, `schema.org/Event`.

### 1.2 Reports de L1 traités ici

- Annuaire public des comités (consentement `directory_listing` prêt depuis L1).
- Photo de profil et liens professionnels, avec une **classe « fichier public »** (B11).
- Contenus du portail (texte mis en forme).
- `GET /public/key-dates` séparé : **non nécessaire** (dates incluses dans l'édition publique).

### 1.3 Prérequis disponibles (L1)

`GET /v1/public/editions/current` (édition, thématiques, types, dates publiques), capacités par
édition et `ManageViewSet`, audit, i18n FR/EN, kit UI, `formatInZone`, budgets et CSP à
empreintes, `deploy.sh` (build sur le poste de déploiement).

## 2. Décisions à valider

| # | Question | Recommandation |
|---|---|---|
| E1 | Comment un site pré-rendu affiche-t-il des contenus de la base ? | Instantané au build + rafraîchissement dans le navigateur |
| E2 | URL des deux langues | `/` en français, `/en/…` en anglais, pré-rendues toutes les deux |
| E3 | Format des contenus éditoriaux | Markdown restreint, rendu par le serveur (`markdown-it-py`, HTML brut désactivé) |
| E4 | Fichiers publics (modèles, photos) | Classe « fichier public » hors racine web, servie par un endpoint public contrôlé ; photos réencodées par Pillow |
| E5 | Qui figure dans la page des comités ? | Seulement les membres actifs ayant consenti à l'annuaire ; photo avec un second consentement |
| E6 | Programme, intervenants, inscriptions | Pages « à venir » éditables en L2 ; vraies pages en L5 et L6 |
| E7 | Référencement | Métadonnées par page, `sitemap.xml`, JSON-LD `Event`, `hreflang`, URL canoniques |
| E8 | Compte à rebours et heure affichée | Calculé dans le navigateur après le rendu ; dates dans le fuseau de l'édition |
| E9 | Mise à jour du portail après une modification | `deploy.sh --portal-only` (rebuild du portail seul) ; le déploiement continu reste une décision séparée (D18) |
| E10 | Plusieurs éditions | Édition courante seule ; `/editions/<slug>/` réservé aux archives (P3) |
| E11 | Qui modifie le portail ? | Nouvelle capacité `portal.write` : `ADMIN`, `CHAIR`, et `OC_MEMBER` de fonction « communication » |
| E12 | Photo et liens du profil | Ajoutés au profil ; photo publique seulement avec consentement `photo_publication` |

### E1. Contenus dynamiques et pré-rendu

**Le problème.** Le portail est pré-rendu au build (CLAUDE.md : SSG, pas de SSR), et o2switch
n'exécute pas Angular côté serveur dans notre architecture. Or les dates, les comités et les
textes changent en base.

**Options.**
- **(a) Rendu dans le navigateur seulement** : pages pré-rendues vides, données chargées par
  l'API. Simple, mais aucun contenu pour les moteurs de recherche ni pour les aperçus de partage
  (Open Graph) : contraire à M1.
- **(b) Instantané au build seulement** : `deploy.sh` lit l'API publique de production et
  pré-rend les pages avec ces données. Bon référencement, mais toute modification attend un
  nouveau déploiement.
- **(c) Hybride (recommandé)** : (b), puis, dans le navigateur, un rafraîchissement depuis
  l'API publique. Les visiteurs voient la version à jour en quelques centaines de
  millisecondes ; les moteurs et les aperçus voient la version du dernier build.
- **(d) Serveur Node (SSR) sur o2switch** (« Setup Node.js App » existe en cPanel, **non
  vérifié**) : contraire à la stack imposée et au budget d'hébergement. Écarté.

**Détails de (c).**
- Endpoint unique `GET /v1/public/portal` (édition courante, pages, documents, comités) :
  l'instantané est **le même JSON** que celui lu dans le navigateur ; pas de deux sources.
- Au build, `GESTCONF_PORTAL_SNAPSHOT_URL` (production) ou un fichier local
  (`web/portal-snapshot.json`, développement et CI) ; sans édition publiée, le portail est
  pré-rendu en mode « bientôt » (aucune erreur de build).
- L'instantané est intégré aux pages par le `TransferState` d'Angular : pas de second appel au
  premier affichage si le rafraîchissement le juge inutile (même empreinte `ETag`).
- Une modification publiée est visible tout de suite par les visiteurs ; les moteurs la voient
  au rebuild suivant (E9).

### E2. Langues et URL

`/` (français, langue par défaut de l'édition) et `/en/…` (anglais), chaque page pré-rendue dans
les deux langues avec `hreflang` et `<html lang>`. Le sélecteur de langue change d'URL sur le
portail public (il reste un réglage d'interface sur `/compte`). Slugs traduits
(`/appel-a-communications` et `/en/call-for-papers`). Alternative : une seule URL dont la langue
change dans le navigateur ; les moteurs n'indexeraient que le français. Déconseillé.

### E3. Contenus éditoriaux

**Recommandation : Markdown restreint**, saisi dans la gestion (FR et EN), converti en HTML par
le **serveur** avec `markdown-it-py` (pur Python, licence MIT, **à confirmer**), HTML brut
**désactivé**, liens limités à `https:`, `http:` et `mailto:`, titres de niveau 2 et 3, listes,
gras, italique, liens, tableaux simples. Le HTML produit est stocké à côté de la source et
renvoyé par l'API ; Angular l'insère par `[innerHTML]`, qu'il nettoie de nouveau.

Pourquoi pas `nh3` (envisagé en L1) : avec le HTML brut désactivé, rien n'est à nettoyer, et
`nh3` est un paquet binaire (Rust) à valider sur o2switch. Il reste le repli si un éditeur
WYSIWYG est demandé plus tard. Aperçu en direct dans la gestion par un appel `POST …/preview`.

### E4. Fichiers publics

**Le problème.** La règle n° 8 (fichiers hors racine web, nom aléatoire, type vérifié par le
contenu, **servis par un endpoint authentifié**) vise les fichiers des soumissions. Les modèles
de documents et les photos des comités sont publics par nature (B11).

**Recommandation : une classe « fichier public » distincte**, qui garde tout le reste de la
règle n° 8 :
- stockage hors de `public_html` (`GESTCONF_MEDIA_ROOT/public/…`), nom aléatoire (UUID), jamais
  le nom fourni ;
- types en liste blanche, vérifiés par **signature** (octets de tête) et extension :
  PDF, DOCX, ODT, ZIP (modèle LaTeX), PNG, JPEG, WebP ; taille maximale 10 Mio (documents)
  et 5 Mio (images) ;
- **photos réencodées** par Pillow (taille maximale 800 px, métadonnées EXIF supprimées, dont la
  position GPS) ; **Pillow est un paquet binaire, à vérifier sur o2switch** (nouveau contrôle
  V28). Repli : refuser les JPEG porteurs de métadonnées EXIF et ne pas redimensionner ;
- servis par `GET /v1/public/files/<uuid>/<nom-affiché>` : `Content-Type` fixé par le serveur,
  `X-Content-Type-Options: nosniff`, `Content-Disposition: attachment` pour les documents,
  `Cache-Control: public, max-age=86400` ; jamais d'exécution ni d'aperçu HTML ;
- un fichier n'est servi que s'il est **publié** et rattaché à une édition publiée (ou, pour une
  photo, à un profil consentant) ; sinon 404 ;
- l'envoi passe par la gestion (`portal.write`) ou par le compte (sa propre photo), audité.

Aucun antivirus n'est disponible sur o2switch (**non vérifié**) : les fichiers acceptés sont
limités à des formats sans macro exécutable à l'ouverture, hors DOCX (macros impossibles dans
`.docx`, contrairement à `.docm`, refusé).

### E5. Comités publics

- Figurent les membres **actifs** de l'édition (`SC_CHAIR`, `SC_MEMBER`, `OC_MEMBER`, `CHAIR`)
  qui ont donné le consentement `directory_listing`. Les autres ne sont **pas** listés ; la page
  indique seulement « et N autres membres » (nombre, sans identité). **À valider** : ce nombre
  est-il souhaité ?
- Champs : titre, prénom, nom, institution, pays ; photo seulement avec le consentement
  `photo_publication` (nouveau, L2). Jamais l'adresse e-mail.
- Le consentement est **par compte** (L1) ; il deviendra « par édition » en L3 (`Consent.edition`).
- Retrait du consentement : effet immédiat dans l'API, et au rebuild suivant dans les pages
  pré-rendues (E9). **À valider** : délai acceptable, sinon rebuild déclenché à chaque retrait.

### E6. Programme, intervenants, inscriptions

Leurs données n'existent qu'en L5 (programme, M10) et L6 (tarifs). En L2, ces pages existent
avec un contenu éditorial (« Le programme sera publié en mai »), modifiable dans la gestion, et
sont exclues du plan de site tant qu'elles sont vides. Elles deviennent de vraies pages dans
leur lot. L'étude place le « programme public (lecture) » en L2 : **écart à valider**.

### E7. Référencement

- Par page : `<title>`, description, `og:title`, `og:description`, `og:image` (affiche de
  l'édition, fichier public), `og:locale`, URL canonique, `hreflang` FR/EN.
- `sitemap.xml` produit au build depuis l'instantané (pages non vides seulement) ; `robots.txt`
  existant complété par la ligne `Sitemap:`.
- JSON-LD `schema.org/Event` (nom, dates, lieu, organisateur, `inLanguage`) sur l'accueil. Un
  `<script type="application/ld+json">` n'est pas exécutable : il n'entre pas dans les empreintes
  de la CSP (`inject-csp.mjs` le vérifie déjà, à tester).
- Nom de domaine et URL publique : `GESTCONF_PUBLIC_URL`.

### E8. Compte à rebours et heures

Les dates sont affichées dans le **fuseau de l'édition** (D13), avec le fuseau indiqué. Le
compte à rebours est calculé dans le navigateur après le rendu (`afterNextRender`) : la page
pré-rendue affiche la date, jamais un nombre de jours figé au build.

### E9. Mettre à jour les pages pré-rendues

`deploy.sh --portal-only` relit l'instantané, rebuild le portail seul et le synchronise
(`public_html`, sans toucher à l'API ni à la gestion), en quelques minutes. La gestion affiche
« dernière publication du portail : <date du build> » (lue dans un fichier `build-info.json`).
Le déploiement continu (D18) permettrait un rebuild automatique ; il reste une décision séparée,
**à prendre avant L3**.

### E10. Plusieurs éditions

L2 affiche l'**édition courante** de la conférence (hypothèse mono-conférence, Q2). Les archives
(P3) prendront `/editions/<slug>/…` ; aucune route actuelle ne l'utilise.

### E11. Droits

Nouvelle capacité **`portal.write`** (pages, documents, choix de l'affiche) : `ADMIN`, `CHAIR`
et `OC_MEMBER` de fonction `communication`. C'est la première écriture « partielle » du CO
(Q12 non tranchée) : **à valider**. Lecture des contenus dans la gestion avec `edition.read`.
La matrice des droits et son test de complétude reçoivent les nouvelles routes.

### E12. Profil

Ajouts au profil : photo (fichier public, avec le consentement `photo_publication`), page web
personnelle et identifiants publics (ORCID déjà présent, Google Scholar, LinkedIn : URL
`https:` seulement). Ces données entrent dans le registre des données personnelles (export,
anonymisation : photo supprimée du disque).

## 3. Modèle de données (additif)

| Table | Champs | Remarques |
|---|---|---|
| `portal_page` | `edition`, `key` (énumération : `home_intro`, `about`, `call`, `practical`, `program_soon`, `speakers_soon`, `registration_soon`), `title_fr/en`, `body_fr/en` (Markdown), `html_fr/en` (rendu), `is_published`, `updated_by`, horodatages | Unicité (`edition`, `key`) ; pas de pages libres en L2 (structure fixe, menus stables) |
| `public_file` | `uuid`, `edition` (nullable : photos de profil), `kind` (`document`, `image`, `photo`), `storage_name`, `original_name`, `content_type`, `size`, `sha256`, `title_fr/en`, `position`, `is_published`, `uploaded_by` | FK `RESTRICT` ; suppression : ligne puis fichier, dans un `on_commit` |
| `edition` | `poster` (FK `public_file`, nullable) | Image Open Graph et bandeau d'accueil |
| `profile` | `photo` (FK `public_file`, nullable), `website`, `scholar_url`, `linkedin_url` | Données personnelles : registre mis à jour |
| `consent.kind` | `photo_publication` | Nouvelle valeur (choix, migration de choix seulement) |

## 4. API

**Public (anonyme, `AllowAny`, liste blanche du test de plateforme).**
- `GET /v1/public/portal` : édition courante, pages publiées (HTML seulement), documents
  publiés, dates publiques, comités publics ; `ETag` et `Cache-Control: public, max-age=300`.
  `GET /v1/public/editions/current` reste pour compatibilité (test de fumée).
- `GET /v1/public/files/<uuid>/<nom>` (E4).

**Gestion (`ManageViewSet`, 2FA).**
- `…/portal/pages` (liste, détail, modification ; `POST …/preview`).
- `…/portal/files` (liste, envoi multipart, modification du titre et de l'ordre, publication,
  suppression) ; `PATCH …/edition` accepte `poster`.
- `…/portal/status` : date du dernier build connu, nombre de modifications depuis.

**Compte.** `PUT /v1/me/photo` (multipart), `DELETE /v1/me/photo` ; liens dans
`PATCH /v1/me/profile`.

Le client TypeScript généré gère le multipart (à vérifier avec `ng-openapi-gen`, sinon
service écrit à la main et documenté).

## 5. Frontend

**Portail (pré-rendu FR et EN).** Accueil (titre, thème, dates, lieu, compte à rebours, appels
à l'action : « Soumettre » visible pendant l'appel, renvoyant vers `/compte` jusqu'à L3),
Présentation, Thématiques, Appel à communications (règles, formats, modèles, échéances),
Dates clés, Comités, Informations pratiques, Programme / Intervenants / Inscriptions (« à
venir »). Service d'instantané (`TransferState` puis rafraîchissement), sélecteur de langue par
URL, en-tête et pied de page de l'édition, métadonnées par route. Budgets surveillés (le
portail initial est à 361,8 kB pour 365 kB) : pas de Material sur les pages publiques.

**Gestion.** Rubrique « Portail » : pages (éditeur Markdown FR/EN avec aperçu), documents
(envoi, titres, ordre, publication), affiche, état de publication ; menu filtré par
`portal.write`.

**Compte.** Photo et liens dans « Profil » ; consentement `photo_publication` dans
« Confidentialité ».

## 6. Sécurité et données personnelles

- Rendu Markdown sans HTML brut, liens filtrés ; test de non-régression XSS (charges connues).
- Fichiers : signature, extension, taille, réencodage des photos, `nosniff`, `attachment`, aucun
  fichier servi par Apache ; quota d'envoi (limite de débit `portal_upload`).
- Comités : jamais d'adresse ; consentement vérifié dans la requête (pas seulement à l'affichage).
- Registre des données personnelles : photo, liens ; anonymisation supprime la photo du disque ;
  le test de balayage couvre les nouvelles colonnes.
- CSP inchangée (`img-src 'self' data:` couvre les images servies sous `/api/`).

## 7. Tests

- Backend : rendu Markdown (charges XSS), fichiers (types refusés, signature trompeuse,
  réencodage sans EXIF, 404 si non publié), `GET /v1/public/portal` (brouillon invisible,
  membres sans consentement absents, aucune adresse), matrice des droits (`portal.write`),
  introspection et balayage étendus.
- Frontend : service d'instantané (hydratation puis rafraîchissement), pages, sélecteur de
  langue, métadonnées ; build : chaque page pré-rendue dans les deux langues, CSP présente,
  JSON-LD valide, `sitemap.xml` cohérent.
- Test de fumée : `/`, `/en/`, `/sitemap.xml`, un fichier public.

## 8. Étapes

| Étape | Contenu | Critère de fin | Charge |
|---|---|---|---|
| L2.0 | Vérifications : `markdown-it-py`, Pillow sur o2switch (V28), multipart du client généré, routes FR/EN pré-rendues (preuve de concept) | Rapport ajouté à `L1-verifications-o2switch.md` ; décisions E1 à E4 confirmées | 1 – 1,5 |
| L2.1 | Pages éditoriales : modèle, rendu, API publique et gestion, écrans « Portail › Pages » | Démo : un texte FR/EN publié est servi par `/v1/public/portal` | 2,5 – 3 |
| L2.2 | Fichiers publics : stockage, contrôles, réencodage, endpoint public, écrans « Documents » et affiche ; photo du profil | Tests de sécurité des fichiers au vert ; démo d'envoi et de téléchargement | 3 – 3,5 |
| L2.3 | Portail : instantané au build, routes FR/EN, accueil, présentation, thématiques, appel, dates, pages « à venir », compte à rebours | Pages pré-rendues dans les deux langues, budgets tenus | 3 – 4 |
| L2.4 | Comités publics (consentements), liens du profil | Membre sans consentement absent (test) | 1 – 1,5 |
| L2.5 | Référencement (métadonnées, JSON-LD, `sitemap.xml`, `hreflang`), `deploy.sh --portal-only`, état de publication | Validation des aperçus Open Graph et du JSON-LD ; test de fumée étendu | 1,5 – 2 |
| L2.6 | Recette, documentation, mise à jour de l'étude | **Démo C sur o2switch** | 0,5 – 1 |
| **Total** | | | **12,5 – 16** |

## 9. Risques et hypothèses non vérifiées

| Risque | Mesure |
|---|---|
| Pillow ne s'installe pas sur o2switch (paquet binaire) | V28 en L2.0 ; repli : pas de réencodage, JPEG avec EXIF refusés |
| Le poste de déploiement n'atteint pas l'API de production au build | Instantané lu depuis un fichier exporté par une commande (`manage.py export_portal_snapshot`) |
| Pages pré-rendues en retard sur la base | État de publication affiché dans la gestion ; `--portal-only` ; décision CD (D18) |
| Budget du portail (361,8 kB sur 365) dépassé par les nouvelles pages | Pages chargées à la demande ; pas de Material public ; mesure à chaque étape |
| Formats de fichiers dangereux | Liste blanche courte, signature, `attachment`, `nosniff` ; antivirus **non vérifié** |
| Données personnelles publiées sans base légale | Consentements explicites, retirables ; cadre légal Q14 toujours ouvert |

## 10. Questions au commanditaire

1. Validation des décisions E1 à E12, en particulier E1 (hybride), E4 (Pillow), E5 (nombre de
   membres non listés), E6 (programme en L5 : écart avec l'étude) et E11 (écriture par le CO
   « communication »).
2. Textes définitifs (présentation, appel, informations pratiques) et affiche : à saisir par
   l'organisation, hors charge (étude §14.3).
3. Nom de domaine de production (pour les URL canoniques et le plan de site).
4. Déploiement continu (D18) : à décider avant L3.
