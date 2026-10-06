# Polices des pièces de facturation (plan L6, J8)

Les polices de base du PDF ne couvrent que le latin-1 ; les noms des participants n'y
tiennent pas tous (vietnamien, polonais, turc…). Les factures, avoirs et pro forma
embarquent donc un sous-ensemble de **DejaVu Sans** 2.37 (normal et gras), généré par
`fpdf2` à chaque PDF (quelques dizaines de ko). Rien n'est supposé sur les polices
installées chez o2switch.

| Fichier | Provenance | SHA-256 |
|---|---|---|
| `DejaVuSans.ttf` | paquet Debian `fonts-dejavu-core` 2.37-8 | `ae7b7855e115a5966d8b1b3f80f254ccc117ec86f9965e202ee2940453837280` |
| `DejaVuSans-Bold.ttf` | paquet Debian `fonts-dejavu-core` 2.37-8 | `5c1247acef7f2b8522a31742c76d6adcb5569bacc0be7ceaa4dc39dd252ce895` |

Licence : `LICENSE` (texte amont de DejaVu : licence Bitstream Vera ; modifications de
DejaVu dans le domaine public ; glyphes Arev). Redistribution autorisée, fichiers non
modifiés.
