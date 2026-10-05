# Lot L2 — Portail public : plan d'implémentation

> **Statut : validé le 5 octobre 2026** (décisions E1 à E14, adaptations du §2.4 et
> propositions par défaut du §10). L2.0 est faite : résultats au §11.
>
> **v2** : le plan suit trois compétences imposées par le commanditaire (dépôt
> `zezesylvain/zds-skills`) :
> - `gestion-cms-portail-angular` : CMS-lite (pages composées de sections réutilisables,
>   menus gérables, pages personnalisées `/p/<slug>`, bilingue, pré-rendu au build) ;
> - `guide-utilisateur-integre-angular` : guide `/aide` et aide contextuelle `?` dans la gestion ;
> - `recherche-menu-topbar-angular` : rail rétractable et recherche d'écran dans la barre haute.
>
> Elles remplacent les choix de la v1 sur le rendu (instantané + rafraîchissement →
> pré-rendu seul avec bandeau d'écart), les URL (`/` → `/fr/` et `/en/`), le format des
> contenus (Markdown → HTML en liste blanche) et le modèle (`portal_page` à clés fixes →
> `Page`, `Section`, `PageSection`, `MenuItem`). Les écarts entre ces compétences et les règles
> de GEST-CONF sont signalés au §2.4.
>
> Sources : étude §4 (M1, M2), §10.1, §10.4, §14 (L2 : 10 à 14 j-h) ; plan L1 §1.3 (reports)
> et §1.4 (prérequis) ; décisions D1 à D18.

## En bref

| | |
|---|---|
| **Objectif** | Un site vitrine bilingue `/fr/…` et `/en/…`, pré-rendu et bien référencé, pour l'édition courante : accueil, appel à communications (règles, formats, modèles, dates), dates clés, thématiques, comités, pages « à venir » (programme, intervenants, inscription), pages personnalisées (informations pratiques…). Dans la gestion : un CMS-lite (sections, pages, menus, composeur, documents, publication). |
| **Ergonomie de la gestion** | Avec le portail, la gestion passe de 9 à 16 écrans : rail en catégories rétractables, recherche d'écran (`⌘K`), guide intégré et aide contextuelle, pour **toute** la gestion (écrans L1 compris). |
| **Point dur** | Pré-rendu au build : une modification n'est visible qu'au déploiement suivant. Ce n'est pas masqué : la gestion compte les modifications non publiées et l'annonce dans un bandeau ; `deploy.sh --portal-only` republie le portail seul. |
| **Hors périmètre** | Données du programme, des intervenants et des tarifs (L5, L6 : pages « à venir » éditables) ; contact, FAQ, actualités, sponsors (P2) ; archives (P3). |
| **Charge** | **17 à 21,5 j-h** (étude : 10 à 14 ; v1 : 12,5 à 16). Hausse : CMS-lite complet (+3), ergonomie de toute la gestion (+2,5 à 3). Détail au §8. |
| **Démo C** | Le président compose l'accueil (sections réutilisables), crée la page « Informations pratiques », l'ajoute au menu, publie deux modèles de documents, voit le bandeau « 5 modifications non publiées », republie ; un visiteur consulte le portail en FR et en EN, télécharge un modèle, partage le lien (aperçu Open Graph) ; un membre sans consentement n'apparaît pas dans les comités. Dans la gestion, `⌘K` « affiche » trouve « Documents », et `?` ouvre la fiche de l'écran courant. |

## 1. Périmètre

### 1.1 Fonctions de M1

| Fonction (M1) | Prio. | L2 |
|---|---|---|
| Accueil : thème, dates, lieu, compte à rebours, appels à l'action | P1 | Page du site (gabarit) + sections |
| Présentation et thématiques | P1 | Page du site « Thématiques » + sections ; présentation en sections |
| Appel à communications : règles, formats, modèles, dates | P1 | Page du site (gabarit : formats, échéances, documents) + sections |
| Dates importantes | P1 | Page du site |
| Comités (photos, affiliations, pays) | P1 | Page du site, avec consentements (E5) |
| Programme public, intervenants, inscription et tarifs | P1 | Pages du site au gabarit « à venir » + sections ; données en L5, L6 (E6) |
| Lieu, accès, hébergement, visas | P2 | Page personnalisée `/p/infos-pratiques` (aucun code dédié) |
| Sponsors, actualités, FAQ, contact | P2 | Non |
| Actes, archives, galerie | P3 | Non ; `/editions/<slug>/` réservé |

### 1.2 Reports de L1 traités ici

Annuaire public des comités, photo de profil et liens, classe « fichier public », contenus du
portail. `GET /public/key-dates` séparé : inutile.

## 2. Décisions à valider

### 2.1 Tableau

| # | Question | Recommandation |
|---|---|---|
| E1 | Rendu des contenus de la base dans un site pré-rendu | **Pré-rendu au build seul** ; bandeau « N modifications non publiées » dans la gestion (compétence CMS) |
| E2 | URL des langues | `/fr/…` et `/en/…`, tout bilingue ; `/` redirige vers `/fr/` ; `/compte` et `/gestion` inchangés |
| E3 | Format des textes | HTML en **liste blanche**, assaini à l'écriture (serveur) **et** au rendu (portail, sans DOM) |
| E4 | Fichiers publics (modèles, photos, images de sections) | Classe « fichier public » hors racine web, endpoint public contrôlé, photos réencodées (Pillow, à vérifier) |
| E5 | Comités publics | Membres actifs ayant consenti à l'annuaire ; photo avec un second consentement |
| E6 | Programme, intervenants, inscription | Pages « à venir » éditables par sections ; vraies pages en L5 et L6 (écart avec l'étude) |
| E7 | Référencement | Métadonnées par page, `hreflang`, canoniques, `sitemap.xml`, JSON-LD `Event` |
| E8 | Compte à rebours | Calculé dans le navigateur après le rendu ; dates dans le fuseau de l'édition |
| E9 | Republier | `deploy.sh --portal-only`, puis `manage.py mark_portal_published` ; déploiement continu : décision séparée (D18) |
| E10 | Plusieurs éditions | Édition courante seule |
| E11 | Droits | Capacité `portal.write` : `ADMIN`, `CHAIR`, `OC_MEMBER` de fonction `communication` |
| E12 | Profil | Photo (consentement `photo_publication`) et liens publics |
| E13 | Navigation de la gestion | Rail en catégories rétractables + recherche d'écran `⌘K` (compétence recherche) |
| E14 | Aide | Guide `/gestion/aide` et aide contextuelle `?` (compétence guide), pour toute la gestion |

### 2.2 Le CMS-lite (compétence `gestion-cms-portail-angular`)

- **Section typée**, catalogue fermé que le portail sait rendre ; un type inconnu n'affiche rien.
  Types proposés :

  | Type | Contenu | Source |
  |---|---|---|
  | `rich_text` | titre, sous-titre, corps | Section (HTML en liste blanche) |
  | `cta_banner` | titre, texte, deux boutons | Section |
  | `image_text` | image + texte | Section + fichier public |
  | `edition_hero` | habillage seulement | Édition (titre, thème, dates, lieu, compte à rebours) |
  | `key_dates` | habillage | Dates clés publiques |
  | `tracks` | habillage | Thématiques actives |
  | `submission_types` | habillage | Types de communication actifs |
  | `documents` | habillage, `config.kind` | Fichiers publics publiés de l'édition |
  | `committee` | habillage, `config.committee` (`scientific`, `organizing`) | Membres consentants (E5) |

  Les types « données » ne portent que l'habillage ; leur contenu vient des services publics
  existants, **jamais d'une copie**.
- **Pages du site** (gabarit codé, adresse figée, `is_system`, liste `SITE_ROUTES` unique lue
  par le menu, la résolution d'URL et les routes à pré-rendre) et **pages personnalisées**
  (`/p/<slug>`). Une page du site rend ses sections **après** son contenu ; une page
  personnalisée rend les siennes intégralement.
- **Le CMS ajoute, il ne remplace pas** : le *seed* livre les sections prêtes à poser, les pages
  du site et les menus, **aucune composition**.
- **Menus** `header` et `footer` gérables ; repli sur la navigation codée tant que la liste est
  vide (pas de clignotement).
- **Composeur** : poser, retirer, ordonner par boutons « monter » / « descendre » (pas de
  glisser-déposer, pas de dépendance) ; l'ordre est envoyé en **liste complète**, refusée (400)
  si elle ne correspond pas exactement ; les trois écritures renvoient la composition **relue
  depuis la base**. Chaque section indique les pages qui la portent.
- **Tout est bilingue** (`_fr`/`_en`), une colonne anglaise vide se repliant sur le français ;
  l'écran d'édition montre les deux langues côte à côte.
- **Pièges intégrés** : `pagination_class = None` sur les vues du CMS ; `config.limit` borné au
  rendu ; suppression d'une section encore posée → 400 nommant les pages ; route `/p/:slug`
  déclarée avant `**` ; **compte des routes pré-rendues vérifié au build** (une API injoignable
  donnerait un build vert avec moins de pages : refus de livrer un compte inférieur à
  l'attendu) ; aucune page du site n'est pré-rendue aussi sous `/p/<slug>`.

### 2.3 Gestion : rail, recherche et aide

**Rail et recherche (compétence `recherche-menu-topbar-angular`).**
- Table de navigation **unique** dans `gestion/src/app/core/navigation.ts`, sans import
  Angular : `buildNavigation(capabilities, activeRole)` → groupes (Pilotage, Paramétrage,
  Comités, Portail, Contrôle, Aide). Elle remplace la constante `NAV` de L1.7.
- Rail en accordéon : une seule catégorie ouverte, celle de l'écran courant (plus long préfixe),
  repli sur la première ; en-têtes en `<button aria-expanded>` ; corps masqués par `[hidden]`
  avec `[hidden]{display:none !important}`.
- Recherche dans la barre haute : `catalogue(groups)` **dérivé** du rail (un écran retiré du menu
  est introuvable), normalisation NFD, rangs 0 à 5, tri stable, combobox ARIA écrite à la main,
  `⌘K`/`Ctrl+K`, `(mousedown)`. Mots-clés métier dans la table (écrans fixes : pas de registre
  serveur dans GEST-CONF).
- Les gardes et la matrice des droits restent la sécurité (règle n° 2) ; le rail n'est que le
  reflet des capacités de `/me`.

**Guide intégré (compétence `guide-utilisateur-integre-angular`).**
- Fiches en **données typées** (`gestion/src/app/help/sheets.ts`, sans import Angular), gabarit
  unique, page `/gestion/aide` (sommaire suiveur, index par profil et par écran, impression),
  bouton `?` et tiroir montés **une fois** dans la coque ; la fiche se déduit de l'URL par la
  table de navigation (chaque entrée porte `help`).
- Fiches pour **tous** les écrans de gestion (L1 et L2) et transversales (premiers pas, 2FA et
  réauthentification, publier le portail) ; elles disent ce que le logiciel refuse et pourquoi.
- Les contrôles de cohérence (chaque écran pointe une fiche existante, aucune fiche orpheline
  hors liste `TRANSVERSAL`) sont des tests Vitest.

### 2.4 Adaptations des compétences aux règles de GEST-CONF (à valider)

| Compétence | Point | Adaptation | Raison |
|---|---|---|---|
| CMS | Administration par la console générique (`console-admin-generique`, registre de collections) | **Écrans dédiés** dans la gestion (sections, pages, menus, composeur), sur le modèle des écrans L1.7 | La gestion n'a pas de console générique ; celle-ci donne un CRUD sur une liste de modèles « réservé au super-admin », ce que D1 (aucun rôle global) exclut. Adopter cette compétence serait une décision séparée |
| CMS | Permission Django `cms.change_page` | Capacité d'édition `portal.write` (E11), `ManageViewSet`, 2FA | Rôles par édition (règle n° 5), pas de permissions de modèle Django (méta-test L1) |
| CMS | Modèles dans une app `cms`, routes `/api/v1/composition/` | App `portal`, routes `v1/public/portal/…` et `v1/manage/editions/{id}/portal/…` | Conventions d'URL de L1 (édition dans le chemin, D5) |
| CMS | Assainissement serveur non précisé | Liste blanche par `html.parser` de la bibliothèque standard | Pas de dépendance binaire (`nh3` est en Rust : règle n° 10) |
| CMS | « Réutiliser le modèle `Page` existant » | Nouveau modèle `Page` (GEST-CONF n'en a pas) | Rien à réutiliser |
| Recherche, guide | Identifiants en français (`construireNavigation`, `chercher`, `FICHES`) | Identifiants en anglais (`buildNavigation`, `search`, `HELP_SHEETS`) ; textes en français par i18n | `CLAUDE.md` : identifiants en anglais, textes par clés de traduction |
| Recherche, guide | Vérifications par esbuild + Node (`npm run verify:console`) | Tests **Vitest** (même contenu) | GEST-CONF a déjà Vitest ; un second outillage serait redondant |
| Guide | Fiches rédigées en français dans le code | Fiches en clés i18n FR/EN, parité vérifiée | Interface bilingue (aucune chaîne en dur) |

### 2.5 Autres décisions (inchangées depuis la v1, sauf mention)

- **E4 — Fichiers publics.** Stockage hors `public_html`, nom aléatoire (UUID), liste blanche
  vérifiée par signature (PDF, DOCX, ODT, ZIP de modèle LaTeX, PNG, JPEG, WebP), 10 Mio
  (documents) et 5 Mio (images) ; photos et images réencodées par **Pillow** (800 px pour les
  photos, 1 600 px pour les images, EXIF supprimé) — **paquet binaire à vérifier sur o2switch**
  (contrôle V28), repli : JPEG avec EXIF refusés, pas de redimensionnement ; servis par
  `GET /v1/public/files/<uuid>/<nom>` (`nosniff`, `attachment` pour les documents, cache
  public) seulement s'ils sont publiés et rattachés à une édition publiée (ou à un profil
  consentant). C'est une adaptation de la règle n° 8 (« servis par un endpoint authentifié »)
  aux fichiers publics par nature : **à valider**.
- **E5 — Comités.** Membres actifs (`CHAIR`, `SC_CHAIR`, `SC_MEMBER`, `OC_MEMBER`) ayant le
  consentement `directory_listing` ; photo avec `photo_publication` ; jamais l'adresse.
  Afficher « et N autres membres » : **à valider**. Retrait du consentement : visible au
  prochain build (bandeau d'écart) ; **à valider**, sinon republication déclenchée.
- **E6.** L'étude place le « programme public (lecture) » en L2 ; ses données n'existent qu'en
  L5 : **écart à valider**.
- **E7.** JSON-LD `<script type="application/ld+json">` : non exécutable, ignoré par les
  empreintes de la CSP (`inject-csp.mjs` le vérifie, testé).
- **E9.** `deploy.sh --portal-only` relit l'API publique de production, rebuild le portail seul,
  le synchronise, puis appelle `manage.py mark_portal_published` (date de mise en ligne ; le
  compteur de modifications repart de zéro).
- **E11.** Première écriture « partielle » du CO (Q12 non tranchée) : **à valider**.

## 3. Modèle de données (app `portal`, additif)

| Table | Champs principaux | Remarques |
|---|---|---|
| `portal_page` | `edition`, `slug`, `is_system`, `route`, `title_fr/en`, `description_fr/en` (métadonnées), `published` | `SITE_ROUTES` marque les pages du site à `save()` **et** par migration de données ; propriété `path` ; page système non supprimable, slug verrouillé |
| `portal_section` | `edition`, `key`, `section_type`, `title_fr/en`, `subtitle_fr/en`, `body_fr/en` (HTML assaini), `cta_label_fr/en`, `cta_url`, `cta2_label_fr/en`, `cta2_url`, `image` (FK `public_file`), `config` (JSON borné par type), `published` | Champs traduisibles déclarés (`TRANSLATABLE`) |
| `portal_page_section` | `page`, `section`, `position` | Unicité (`page`, `section`) et (`page`, `position`) ; FK `RESTRICT` côté section (suppression refusée si posée) |
| `portal_menu_item` | `edition`, `location` (`header`, `footer`), `label_fr/en`, `page` (FK nullable), `url`, `new_tab`, `position`, `published` | Page **ou** URL `https:` obligatoire |
| `portal_publication` | `edition`, `published_at`, `release`, `actor` | Dernière mise en ligne ; le compteur d'écart se calcule par l'audit (`portal.*` postérieurs) |
| `public_file` | `uuid`, `edition` (nullable), `kind` (`document`, `image`, `photo`), `storage_name`, `original_name`, `content_type`, `size`, `sha256`, `title_fr/en`, `position`, `published`, `uploaded_by` | Suppression : ligne puis fichier dans un `on_commit` |
| `edition` | `poster` (FK `public_file`, nullable) | Image Open Graph |
| `profile` | `photo` (FK `public_file`), `website`, `scholar_url`, `linkedin_url` | Registre des données personnelles mis à jour |
| `consent.kind` | `photo_publication` | Nouvelle valeur |

Toutes les écritures passent par `portal/services.py`, auditées (`portal.section_updated`…).

## 4. API

**Public** (`AllowAny`, liste blanche du test de plateforme, `pagination_class = None`) :
- `GET /v1/public/portal/routes` : routes à pré-rendre (`/fr/…`, `/en/…`, `/fr/p/<slug>`…) et
  leur **nombre attendu** ;
- `GET /v1/public/portal/composition/<chemin|slug>` : page, sections publiées ordonnées en paires
  de langue, données des sections « données » ; 404 si inconnue (le gabarit s'affiche seul) ;
- `GET /v1/public/portal/menu?location=header|footer` ;
- `GET /v1/public/portal/site` : édition, dates, thématiques, types, documents, comités (un seul
  appel pour les gabarits des pages du site) ;
- `GET /v1/public/files/<uuid>/<nom>`.

**Gestion** (`ManageViewSet`, 2FA, `portal.write` en écriture, `edition.read` en lecture) :
`…/portal/sections` (CRUD, `POST …/preview`), `…/portal/pages` (CRUD ; actions `attach`,
`detach`, `reorder`), `…/portal/menu` (CRUD, `reorder` par emplacement), `…/portal/files`
(multipart), `…/portal/status` (dernière mise en ligne, modifications depuis).

**Compte** : `PUT`/`DELETE /v1/me/photo`, liens dans `PATCH /v1/me/profile`.

## 5. Frontend

**Portail.** Routes `/fr/…` et `/en/…` (accueil, appel à communications, dates, thématiques,
comités, programme, intervenants, inscription), `/fr/p/:slug` et `/en/p/:slug` **avant** `**`,
pré-rendues à partir de `routes` ; `/compte/**` inchangé (rendu client). Rendu des sections
(`SectionsComponent`, un composant par type, type inconnu ignoré), assainisseur sans DOM
(`sanitize.ts`, liste blanche de balises, aucun attribut sauf `href` http(s)/interne/`mailto`/
`tel`), en-tête et pied de page à menus gérés (repli codé), sélecteur de langue par URL,
métadonnées par route. Pas de Material sur les pages publiques (budget : 361,8 kB sur 365).

**Gestion.** Rail et recherche (§2.3), guide et aide contextuelle (§2.3), rubrique « Portail » :
sections (édition FR/EN côte à côte, aperçu), pages (du site et personnalisées), composeur,
menus, documents, état de publication et bandeau d'écart.

**Compte.** Photo et liens dans « Profil » ; `photo_publication` dans « Confidentialité ».

## 6. Sécurité et données personnelles

- HTML assaini aux deux bouts ; tests avec des charges XSS connues (`<script>`, `style=`,
  `javascript:`, `on*=`, balises SVG) côté Python **et** côté portail.
- Fichiers : signature, extension, taille, réencodage, `nosniff`, `attachment`, jamais servis par
  Apache ; limite de débit `portal_upload`.
- Comités : jamais d'adresse ; consentement vérifié dans la requête.
- Registre des données personnelles (photo, liens) et test de balayage étendus.
- CSP inchangée.

## 7. Tests

Backend : assainisseur, composition (ordre, liste complète exigée, relue), pages du site
(marquage, pas de doublon `/p/`), menus (repli, validation), routes (compte attendu), fichiers,
comités (consentement), matrice des droits (`portal.write`), registre et balayage.
Frontend : navigation (une catégorie ouverte, repli, plus long préfixe), recherche (NFD, rangs,
tri stable, profil restreint : écran hors périmètre introuvable), cohérence des fiches d'aide,
rendu des sections (type inconnu, assainissement), pré-rendu (compte de routes, CSP, JSON-LD,
`sitemap.xml`). Vérification **dans le navigateur** du rail (le piège `[hidden]` ne se voit pas
hors navigateur). Test de fumée : `/fr/`, `/en/`, `/sitemap.xml`, un fichier public.

## 8. Étapes

| Étape | Contenu | Critère de fin | Charge |
|---|---|---|---|
| L2.0 | Vérifications : Pillow sur o2switch (V28), multipart du client généré, pré-rendu `/fr` + `/en` + `/p/:slug` alimenté par une API (preuve de concept), redirection `/` | Rapport ; E1 à E4 confirmées | 1 |
| L2.1 | Gestion : table de navigation, rail en accordéon, recherche `⌘K`, guide `/aide` et aide contextuelle, fiches des écrans L1 | Vérifications de la compétence au vert, dans le navigateur | 2,5 – 3 |
| L2.2 | CMS backend : modèles, assainisseur, services audités, API publique et de gestion, *seed* sans composition, `portal.write`, état de publication | Tests du CMS et matrice au vert | 3 – 3,5 |
| L2.3 | CMS gestion : sections, pages, composeur, menus, bandeau d'écart, fiches d'aide | Démo : composer une page, la voir dans l'aperçu | 3 – 3,5 |
| L2.4 | Fichiers publics, documents, affiche, photo du profil | Tests de sécurité des fichiers au vert | 2,5 – 3 |
| L2.5 | Portail : routes FR/EN pré-rendues, pages du site, rendu des sections, menus, `/p/:slug`, compte de routes, compte à rebours | Toutes les pages pré-rendues dans les deux langues ; budgets tenus | 3 – 4 |
| L2.6 | Comités publics, référencement, `deploy.sh --portal-only`, `mark_portal_published` | Aperçus Open Graph et JSON-LD valides ; test de fumée étendu | 1,5 – 2,5 |
| L2.7 | Recette, documentation, mise à jour de l'étude (§17) | **Démo C sur o2switch** | 0,5 – 1 |
| **Total** | | | **17 – 21,5** |

## 9. Risques et hypothèses non vérifiées

| Risque | Mesure |
|---|---|
| Pillow ne s'installe pas sur o2switch | V28 en L2.0 ; repli sans réencodage |
| API de production injoignable au build → pages manquantes, build vert | Compte de routes attendu fourni par l'API et vérifié ; refus de livrer |
| Modifications non visibles avant republication | Bandeau d'écart, `--portal-only`, fiche d'aide « publier le portail » ; déploiement continu (D18) |
| Budget du portail (361,8 kB sur 365) | Sections chargées à la demande ; pas de Material public ; mesure à chaque étape |
| Rail correct en logique, faux à l'écran (`[hidden]`) | Vérification visuelle dans Chromium à chaque étape touchant la coque |
| Formats de fichiers dangereux | Liste blanche courte, signature, `attachment`, `nosniff` ; antivirus non vérifié |
| Données personnelles publiées sans base légale | Consentements explicites et retirables ; cadre légal Q14 ouvert |

## 10. Questions au commanditaire

1. Validation de E1 à E14, et des adaptations du §2.4 (surtout : écrans dédiés plutôt que la
   console générique ; tests Vitest plutôt que `verify:console`).
2. E4 (fichiers publics : adaptation de la règle n° 8), E5 (« et N autres membres », délai de
   retrait du consentement), E6 (programme en L5), E11 (écriture par le CO « communication »).
3. Charge de 17 à 21,5 j-h, contre 10 à 14 dans l'étude.
4. Textes, affiche, nom de domaine de production ; déploiement continu (D18) avant L3.

## 11. Résultats de L2.0 (5 octobre 2026)

| Vérification | Résultat | Conséquence |
|---|---|---|
| **Pillow (V28)** | Pillow 12.3.0 ne publie que des roues `manylinux_2_27`/`2_28` (Python 3.12 et 3.13, x86_64) : glibc ≥ 2.27 exigée. Contrôle V28 ajouté à `deploy/check-o2switch.sh` (venv jetable de V03, réencodage réel JPEG avec EXIF → JPEG, WebP, PNG redimensionnés sans EXIF), exécuté avec succès en local ; **reste à lancer sur o2switch** | E4 confirmée sous réserve de V28 ; repli inchangé |
| **Multipart du client généré** | Preuve avec une vue DRF `MultiPartParser` + `FileField` : drf-spectacular décrit `multipart/form-data` et `format: binary` ; ng-openapi-gen génère un champ `Blob` et envoie un `FormData` sans fixer `Content-Type` (le navigateur ajoute la frontière) ; l'intercepteur CSRF s'applique | Téléversements par le client généré, sans code écrit à la main |
| **Pré-rendu `/fr`, `/en`, `/:lang/p/:slug` alimenté par une API** | Preuve de concept (copie de travail hors dépôt, API simulée) : `getPrerenderParams` lit les routes dans l'API au build ; 7 pages produites (`/`, `/fr`, `/en`, 2 pages × 2 langues), contenu et langue corrects | E1 et E2 confirmées |
| API injoignable au build | L'appel des routes échoue → **build en échec** (souhaité) | — |
| Une composition en erreur (404, 500) | La page est pré-rendue **vide** et le build reste **vert** | Confirme le risque du §9 : en L2.5, contrôle après build (`scripts/check-prerender.mjs`) : nombre de routes attendu fourni par l'API, et marqueur de rendu complet dans chaque page ; sinon refus de livrer |
| Cache de transfert (réhydratation) | Avec un intercepteur qui préfixe `/api` par l'origine de l'API, la clé du cache est l'URL absolue : le navigateur **redemande** la composition. Corrigé en réécrivant l'URL au niveau du `HttpBackend`, côté serveur seulement (`ServerApiBackend`, après le cache) : aucune requête de composition dans le navigateur (vérifié dans Chromium) | Variable `GESTCONF_PRERENDER_API_ORIGIN` lue au build ; `ServerApiBackend` dans `app.config.server.ts`, aucun code serveur dans `shared` |
| **Redirection `/`** | Angular produit pour `redirectTo` une page `index.html` à `meta refresh` vers `/fr` | En L2.5 : redirection 302 `^/$` → `/fr/` dans le `.htaccess` (référencement), la page à `meta refresh` restant un repli ; adresses canoniques **avec** barre finale (`/fr/`), comme les sert Apache (`DirectorySlash`) |
| Budget initial du portail | Routes `:lang` et pages chargées à la demande : bundle initial de 368,3 à 370,4 kB (au lieu de 361,9), par découpage des morceaux communs d'esbuild, non par du code ajouté | En L2.5 : mesurer et ramener sous 365 kB (morceaux communs, `ApiStatus` hors de l'accueil) ; sinon demander un relèvement du budget |

Les écarts de cette étape sont reportés dans les étapes concernées ; aucune décision E1 à E14
n'est remise en cause.

## 12. Bilan de L2.1 (5 octobre 2026)

**Livré dans la gestion** (toute la gestion, écrans L1 compris) :

- **Table de navigation unique** `gestion/src/app/core/navigation.ts` (sans import Angular) :
  `SCREENS`, `buildNavigation(editionId, capabilities, activeRole)`, `catalogue`, `activeGroup`
  et `entryForUrl` (plus long préfixe), `helpForUrl`. Elle remplace les constantes `NAV` et
  `ROLE_SECTIONS` de L1.7. `NavigationStore` partage l'édition et le rôle actif entre le rail
  et la barre haute.
- **Rail en accordéon** : catégories Pilotage, Paramétrage, Comités, Contrôle, Aide (la
  catégorie Portail arrive en L2.3). Une seule ouverte, celle de l'écran courant. Repli sur la
  catégorie déjà ouverte, puis sur la première. En-têtes en `<button aria-expanded
  aria-controls>`, corps masqués par `[hidden]` avec la règle globale
  `[hidden]{display:none !important}`.
- **Recherche d'écran** dans la barre haute (`core/search.ts`, `layout/screen-search.ts`) :
  - catalogue dérivé du rail ; normalisation NFD ; rangs 0 à 5 ; tri stable ;
  - saisie vide : tout le catalogue ; une lettre : rien ;
  - combobox ARIA écrite à la main, `⌘K`/`Ctrl+K`, `(mousedown)` sur les résultats.
  
  Mots-clés métier en clés i18n `gestion.nav.keywords.*` (écrans fixes : pas de registre
  serveur).
- **Guide** :
  - fiches en données typées, avec des clés i18n FR/EN (`help/help-sheets.ts`) :
    - 3 fiches transversales : premiers pas, double authentification et confirmation
      d'identité, rôles et droits ;
    - 8 fiches d'écran, dont une partagée par Thématiques et Types ;
  - page `/aide` : sommaire suiveur (`IntersectionObserver`, marge `-10% 0px -70% 0px`),
    index par profil et par écran, impression, `?fiche=<id>` ;
  - bouton `?` et tiroir montés une fois dans la coque ; la fiche se déduit de l'URL
    (`/editions` : premiers pas) ; pas de bouton sur `/aide` ni sur un écran sans fiche ;
    `Échap` et un clic sur le fond referment le tiroir.

  Les fiches ont été rédigées d'après le code : préconditions de publication, 14 jours de
  validité d'une invitation, trois envois au plus, réauthentification pour publier ou
  archiver, pour la confidentialité, pour tout retrait de rôle et pour inviter un ADMIN ou
  un CHAIR.

**Écarts avec le §2.3** :

- `/aide` est hors de la mise en page de l'édition (le guide ne dépend d'aucune édition) : le
  rail n'y est pas affiché, et la page propose un lien « Retour à la gestion ».
- La fiche « publier le portail » viendra avec la rubrique Portail (L2.3).

**Vérifications** :

- **Tests Vitest de la gestion : 56** (17 de plus) :
  - navigation : profils, rôle actif, plus long préfixe, repli, catalogue dérivé ;
  - recherche : NFD et ligature, rangs, tri stable ;
  - cohérence des fiches : chaque écran pointe une fiche existante, aucune fiche orpheline
    hors `TRANSVERSAL`, toutes les clés présentes en FR et en EN, aucune clé inutilisée ;
  - composants : combobox, clavier, souris, `⌘K`, profil restreint, tiroir, guide.
- **Dans Chromium** (Playwright, serveurs locaux, comptes ADMIN et OC_MEMBER avec 2FA) :
  - une seule catégorie visible à l'écran, et un clic en ouvre une autre ;
  - `Ctrl+K`, puis « echeance » et Entrée, mène au Calendrier ; le rail suit ;
  - un clic souris sur un résultat navigue ;
  - le tiroir montre la fiche de l'écran, focus sur son titre ; `Échap` le referme ;
  - « Voir le guide complet » mène à la fiche ;
  - le sommaire défile sans écrire dans l'historique ;
  - à l'impression, l'en-tête, le rail et le sommaire sont masqués ;
  - aucun débordement horizontal de 1 280 à 375 px ;
  - pour le CO, « journal » et « invit » ne trouvent rien ;
  - aucune erreur dans la console.
- **Bundle initial de la gestion** : 356,6 kB (336,7 avant), budget de 500 kB. Celui du
  portail est inchangé.
