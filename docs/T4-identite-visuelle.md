# T4 — Identité visuelle du portail (bilan)

- **Plan** : [`T4-identite-visuelle-plan.md`](T4-identite-visuelle-plan.md), décisions V1 à V13, **validé le 19 octobre 2026**.
- **Maquette de référence** : canevas Claude Design « GAHAA et ICHA 2027 — Sites web », pages « Accueil du portail » et « Appel et inscription », validées le 19 octobre 2026.
- **Étude** : §29, version 1.13.

## Ce qui est livré

| Étape | Contenu | Fichiers |
|---|---|---|
| T4.1 | Jetons `--pt-*`, surcharge de `--gc-primary`, `--gc-text`, `--gc-muted` et `--gc-font` pour le portail seul ; quatre polices woff2 en jeu latin, avec leurs licences OFL ; préchargement de deux d'entre elles ; motif d'ondes en SVG | `portail/src/styles.scss`, `portail/src/index.html`, `portail/public/fonts/`, `portail/public/images/ondes.svg` |
| T4.2 | Barre utilitaire, marque de l'édition (`brandName`) et ville, menu géré dont la page courante est soulignée d'or, pied de page en colonnes ; le `main` des pages publiques en pleine largeur | `app.html`, `app.scss`, `app.ts`, `site/brand.ts`, `site/site-nav.ts` |
| T4.3 | Accueil : héros avec affiche et deux boutons (Appel, Inscription), compte à rebours ; dates clés en cartes avec état calculé dans le navigateur (`dateStatus`) ; sections en bandes alternées ; thématiques numérotées ; bande des partenaires (`HomeSponsors`) | `site/widgets.ts`, `site/hero.scss`, `site/sections.ts`, `site/site.scss`, `site/community/home-sponsors.ts` |
| T4.4 | Pages intérieures : bandeau de titre et fil d'Ariane ; page Appel avec quatre étapes génériques traduites | `site/portal-page.html`, `site/portal-page.ts`, `site/page.scss`, `i18n/fr.json`, `i18n/en.json` |
| T4.5 | Tests unitaires V6, V8, V7 et V10, V11 ; audit axe ; captures comparées à la maquette ; E2E | `site/site.spec.ts` |

## Vérifications

- **Tests du portail** : 178 réussis, dont 4 nouveaux. `ng lint portail` et `prettier --check` passent.
- **Pré-rendu** contre une API locale chargée avec `icha-2027` : 20 routes complètes, CSP injectée.
- **Captures** à 1440 px et 390 px de l'accueil, de l'appel, de l'inscription et de la connexion, comparées à la maquette. Aucun débordement horizontal.
- **Audit axe** (WCAG 2.0 et 2.1, A et AA) aux deux largeurs, sur l'accueil (FR et EN), l'appel, l'inscription, les dates et la connexion : **aucune violation**.
- **Budgets** :

  | Mesure | Avant | Après |
  |---|---|---|
  | Bundle initial | 369,8 ko | 375,9 ko (+6,1 ko, dans la limite de +10 ko de V12) |
  | Budget initial (avertissement / erreur) | 375 / 380 ko | 380 / 385 ko |
  | Feuille globale | 0,6 ko | 1,8 ko |

  Chaque feuille de composant reste sous 4 ko : c'est pourquoi les styles sont répartis entre `site.scss`, `page.scss` et `hero.scss`.

## Écarts avec le plan et la maquette

- **V5** : le menu ne se replie pas dans un `<details>`. Ce repli exige soit du JavaScript, soit le pseudo-élément `::details-content`, encore récent dans les navigateurs. Sur téléphone, le menu passe donc à la ligne.
- **V8** : les cartes de dates ne reprennent que les dates clés de l'édition. L'ouverture et la clôture de la conférence restent dans le héros, car les sections n'ont pas accès à l'édition.
- **Contenu de l'accueil** : comme prévu au §5 du plan, programme, comités et tarifs sont posés sur l'accueil **dans la gestion**. Ils s'affichent les uns sous les autres.
- **`/compte`** : le bouton Material garde le thème de L1. Harmoniser `gc-theme.css` serait une étape à part.

## À faire pour la mise en ligne

1. **Contenu de l'accueil**, dans la gestion, par l'administrateur de l'édition : poser sur l'accueil les sections `programme-previsionnel`, `composition-comites` et `tarifs` ; ajouter au menu du pied de page un lien « GAHAA · gahaa.ci ».
2. **Publication du portail pré-rendu** avec `deploy.sh --portal-only`. Elle doit se faire depuis une machine qui atteint `conference.gahaa.ci` : le Mac (Node 22.22.3 ou plus, ou Node 24.15 ou plus). Ni la machine virtuelle de compilation ni le conteneur n'y ont accès.
