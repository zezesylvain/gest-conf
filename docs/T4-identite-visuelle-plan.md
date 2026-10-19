# T4 — Identité visuelle du portail (plan)

Demande du commanditaire du 19 octobre 2026 : appliquer au portail public la maquette « ICHA 2027 — Accueil du portail » et « Appel et inscription », **validée le 19 octobre 2026** (canevas Claude Design « GAHAA et ICHA 2027 — Sites web »). Plan **validé le 19 octobre 2026** ; bilan : [`T4-identite-visuelle.md`](T4-identite-visuelle.md). Le site du groupe GAHAA (gahaa.ci) **n'en fait pas partie** : sa maquette est encore en cours.

## 1. Constat

- Le portail (`web/projects/portail`) a un rendu sobre : jetons `--gc-*` partagés avec la gestion (bleu `#1d3a6e`), polices système, une colonne de 72 rem, en-tête bleu uni, sections en blocs simples (`site/site.scss`, 155 lignes).
- La structure suit déjà la maquette : pages codées (accueil, appel, dates, thématiques, comités, programme, intervenants, inscription, partenaires, actualités), menus gérés, sections à catalogue fermé (`site/sections.ts`), pré-rendu au build.
- Contraintes relevées :
  - **CSP** de `public_html` : `font-src 'self'`, d'où l'interdiction de Google Fonts ; `style-src 'self' 'unsafe-inline'` ;
  - **budgets** (`angular.json`) : `initial` à 375 ko (avertissement) et 380 ko (erreur), `anyComponentStyle` à 4 ko (avertissement) et 8 ko (erreur). `site.scss` est rechargé par chaque composant qui le cite ;
  - **données publiques** : `PublicSite` expose l'édition, l'affiche (`poster`), les documents et les comités. Il n'existe ni titre court, ni champ « hybride », ni lien vers l'organisateur ;
  - **configuration des sections** : `image_position` n'accepte que `left` ou `right` (`apps/portal/services.py`).

## 2. Décisions proposées

| N° | Décision |
|---|---|
| V1 | **Portail seul.** La gestion garde son apparence. Les jetons propres au portail (`--pt-*`) sont dans `portail/src/styles.scss`. Le portail y surcharge `--gc-primary` en `#092b40` (bleu nuit de l'affiche) pour que les écrans de `/compte` restent cohérents. `shared/ui-kit/_tokens.scss` ne change pas. |
| V2 | **Palette fixe pour l'installation**, tirée de l'affiche, avec les contrastes vérifiés au §3 : bleu nuit `#092b40` et `#061f2f`, or `#e8b44a` (sur fond sombre seulement), sarcelle `#086f6c` (liens et numéros sur fond clair), texte `#1b2b36` et `#3d5361`, gris d'appoint `#5b7383`, fond alterné `#f3f6f8`. Pas de couleur par édition dans ce lot : il faudrait un champ et un rendu sans attribut `style` pré-rendu, à décider plus tard. |
| V3 | **Polices auto-hébergées** (licence OFL, sans dépendance npm) : Archivo 800 et 900 pour les titres, IBM Plex Sans 400 et 600 pour le texte, en woff2, jeux latin et latin étendu, dans `portail/public/fonts/` avec leurs licences. `font-display: swap` et préchargement des deux fichiers du premier écran. IBM Plex Mono, présente dans la maquette, est remplacée par les chiffres tabulaires de Plex Sans. |
| V4 | **Motif d'ondes** : un fichier SVG décoratif servi par le portail (`img-src 'self'`) et posé en fond CSS du héros et des bandeaux. Il n'apparaît pas dans le DOM et ne gêne pas l'accessibilité. |
| V5 | **Gabarit commun** (`app.html` et `app.scss`) :<br>• barre utilitaire avec langue et compte ;<br>• en-tête bleu nuit avec la marque et le menu géré de l'en-tête (le lien actif est souligné d'or) ;<br>• `main` en pleine largeur, chaque bloc fixant son conteneur de 1200 px ;<br>• pied de page en quatre colonnes : résumé de l'édition, menu géré du pied (dont le lien vers gahaa.ci, saisi dans la gestion), liens « Votre compte » codés, mentions.<br>Sous 48 rem, le menu se replie dans un `<details>`, sans JavaScript, compatible avec le pré-rendu. |
| V6 | **Marque de l'en-tête** : le code de l'édition, séparé de son année quand il finit par elle (« ICHA2027 » devient « ICHA 2027 »), avec la ville en sous-titre. Si l'édition n'est pas encore chargée, la marque est le nom de l'application. Pas de nouveau champ « titre court » dans ce lot. |
| V7 | **Héros de l'accueil** (`EditionHero`) :<br>• à gauche : sur-titre « code · année », titre de l'édition en h1, thème, dates en or, lieu, deux boutons (Appel, Inscription) et compte à rebours ;<br>• à droite : l'**affiche** (`site.poster`), car c'est la donnée disponible, au lieu du portrait du parrain de la maquette. Le portrait reste dans la section « Parrainage », rendue en carte juste après le héros.<br>La bande « Sur place et en direct · Anglais et français · Springer · Forum doctoral » n'a pas de données. Elle n'est pas reprise et son contenu reste dans la section de présentation. |
| V8 | **Dates clés en cartes** : les dates de l'édition (`key_dates`), plus l'ouverture et la clôture tirées de `start_date` et `end_date`. Le badge « En cours », « À venir » ou « Passée » est calculé **dans le navigateur**, comme le compte à rebours : une page pré-rendue ne doit pas figer un état. |
| V9 | **Sections restylées, sans nouveau type ni changement d'API** :<br>• `rich_text` : titre en Archivo, listes en grille ;<br>• `tracks` : cartes numérotées 01 à 0N ;<br>• `cta_banner` : bandeau bleu nuit, titre en or ;<br>• `image_text` : carte ;<br>• `committee` : liste ;<br>• `documents` : liens.<br>Les fonds alternent (blanc, puis `#f3f6f8`) selon le rang de la section. |
| V10 | **Partenaires sur l'accueil** : une bande de logos par niveau en bas de l'accueil, qui réutilise les données de la page « Partenaires » (`CommunityData`, liste blanche publique). C'est le seul ajout de contenu codé. Le programme, les comités et les tarifs vus dans la maquette s'obtiennent **sans code**, en posant sur l'accueil, dans la gestion, les sections `programme-previsionnel`, `composition-comites` et `tarifs`. Elles s'affichent les unes sous les autres, et non en deux colonnes. |
| V11 | **Pages intérieures** :<br>• bandeau de titre bleu nuit avec fil d'Ariane ;<br>• page Appel : les quatre étapes « Comment soumettre », génériques et traduites (FR/EN), valables pour toute édition ;<br>• page Inscription : la présentation actuelle, restylée (tableau dans `table-wrap`). |
| V12 | **Styles** : la base visuelle passe dans la feuille globale du portail (hors budget `anyComponentStyle`). `site.scss` ne garde que le propre de chaque composant. Le budget `initial` est mesuré à chaque étape et ne doit pas augmenter de plus de 10 ko (CSS seul ; les polices ne comptent pas). |
| V13 | **Accessibilité** : contrastes du §3, cibles de 44 px au moins, focus visible (or sur fond sombre, sarcelle sur fond clair), un seul h1 par page, `expectAccessible` inchangé dans l'E2E. |

## 3. Contrastes (WCAG 2.1 AA, calculés)

- Blanc sur `#092b40` : 14,7:1.
- `#c9d6df` sur `#092b40` : 9,9:1.
- Or `#e8b44a` sur `#092b40` : 7,7:1. Inversement, bleu nuit sur or : 7,7:1.
- `#9fb4c2` sur `#061f2f` : 7,9:1. Sur `#0e3650` : 5,9:1.
- Sarcelle `#086f6c` sur blanc : 6,0:1. Sur `#f3f6f8` : 5,5:1.
- `#3d5361` sur blanc : 8,1:1.
- `#5b7383` sur `#f3f6f8` : 4,6:1.
- L'**or sur blanc ne fait que 1,9:1** : il n'est donc jamais utilisé comme texte sur fond clair.

## 4. Étapes

| Étape | Contenu |
|---|---|
| T4.0 | Ce plan, validé le 19 octobre 2026. Fait. |
| T4.1 | Jetons, polices et feuille globale (V1 à V4, V12) ; mesure des budgets. |
| T4.2 | Gabarit : barre utilitaire, en-tête, marque, menu repliable, pied de page (V5, V6). |
| T4.3 | Accueil : héros, dates clés en cartes, sections restylées, bande des partenaires (V7 à V10). |
| T4.4 | Pages intérieures, appel en quatre étapes, inscription (V11). |
| T4.5 | Tests unitaires (`site.spec.ts` : marque, badge de date, repli du menu), E2E, axe, `check-prerender` ; captures à 1440 px et à 390 px comparées à la maquette. |
| T4.6 | Bilan, mise à jour de l'étude (§29, Markdown et HTML) et de CLAUDE.md ; PR. |

T4.1 à T4.5 sont livrées (commit `b05efc4`) ; écarts et mesures dans le bilan.

## 5. Hors périmètre et points ouverts

- **Publication** : le portail est pré-rendu à partir de l'API de production (`GESTCONF_PRERENDER_API_ORIGIN`). Ni la machine virtuelle de compilation ni ce conteneur n'atteignent `conference.gahaa.ci`, car le proxy refuse la connexion. La compilation pré-rendue devra donc se faire **sur le Mac** (Node 22.22.3 ou plus) avec `deploy.sh --portal-only`. Autre voie possible : une base locale chargée à l'identique, mais elle s'écarte dès qu'un contenu est modifié dans la gestion. À trancher avant T4.6.
- **Contenu** : poser `programme-previsionnel`, `composition-comites` et `tarifs` sur l'accueil, et le lien vers gahaa.ci dans le menu du pied de page, est une saisie dans la gestion, faite par l'administrateur de l'édition.
- Champ « titre court » et couleur par édition : à décider plus tard (V2, V6).
- Le site GAHAA (gahaa.ci), maquette en cours, fera l'objet d'une décision séparée.
