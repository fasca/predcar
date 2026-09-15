# Source : UK DfT — STATS19 road casualty statistics, table `vehicle`

**Statut : vérifié le 2026-09-15 sur le fichier réel, écarté.** Le fichier est ouvert, propre
et joignable, mais son libellé de modèle est une liste fermée de modèles courants : les cibles
rares du projet n'y existent pas. Aucun parseur n'a été écrit ; ce document consigne l'observation
qui a conduit à la décision, pour ne pas la refaire.

Page : https://www.data.gov.uk/dataset/cb7ae6f0-4be6-4935-9277-47e5ce24a11f/road-safety-data
(HTTP 200). Licence : Open Government Licence v3.0.
Fichier observé : https://data.dft.gov.uk/road-accidents-safety-data/dft-road-casualty-statistics-vehicle-last-5-years.csv
(HTTP 200, 103 741 631 octets, téléchargé en entier). Le guide de données lié depuis la page
(`…/dft-road-casualty-statistics-road-safety-open-dataset-data-guide-2024.xlsx`) répond **404**.

## Schéma observé

937 265 lignes (un véhicule impliqué dans une collision corporelle), années `collision_year`
2021–2025, 32 colonnes, toutes numériques codées sauf les identifiants et le libellé :

| Colonne | Observé | Note |
|---|---|---|
| `collision_index`, `collision_year`, `collision_ref_no`, `vehicle_reference` | clé | jointure possible avec la table `collision` (gravité) |
| `vehicle_type` | code | `9` = voiture ; 68 % des lignes |
| `generic_make_model` | texte `MARQUE MODELE` ou `-1` | voir ci-dessous |
| `age_of_vehicle` | entier, `-1` si inconnu | 35 % ≥ 10 ans, 21 % inconnus |
| `age_of_driver`, `age_band_of_driver`, `sex_of_driver` | codes | |
| `engine_capacity_cc`, `propulsion_code` | | |
| autres (manœuvre, point d'impact, `lsoa_of_driver`, `driver_imd_decile`…) | codes | sans usage ici |

Aucune donnée personnelle directe ; `lsoa_of_driver` est une zone statistique.

## Le libellé `generic_make_model` — pourquoi la source est écartée

- **Liste fermée** : 593 libellés distincts sur cinq ans, motos comprises. Tout ce qui n'est
  pas dans la liste vaut `-1` : **24 % des véhicules, 14 % des voitures**. Le libellé n'est
  pas celui de la DVLA (VEH0120 en compte des dizaines de milliers) mais un « modèle
  générique » d'usage statistique.
- **Les marques rares en sont absentes** : aucun libellé Ferrari, Aston Martin, Lotus, TVR,
  Alpine, Caterham. Alfa Romeo = Giulietta, MiTo, Giulia, 159, Stelvio, 147 seulement.
  Absents aussi : Audi RS2, S2, Coupé, Cabriolet ; BMW 1M, Z3 M, Z4 M, Z8 ; Citroën C6, C2 VTS,
  Saxo VTS, Xsara VTS, DS3 Racing ; Peugeot 205, 106 ; Renault Clio Williams (« RENAULT CLIO »
  seulement, toutes générations).
- **Niveau modèle, toutes générations confondues** : « BMW M3 » couvre E30 → G80, « AUDI TT »
  8N → 8S. Le libellé ne permet pas d'atteindre la génération, qui est l'unité du score.
- **Couverture des cibles après mapping** (`mapping/makes.csv` + `models.csv`, mêmes règles que
  VEH0120, marque isolée par le plus long alias en préfixe) : 95 % des libellés des marques
  cibles se mappent, mais **35 des 200 modèles cibles ont au moins un véhicule accidenté sur
  cinq ans, 165 aucun**. Les 35 sont les modèles courants — Ford Puma 1 640, VW Scirocco 1 020,
  Audi TT 922, Audi S3 845, Mazda MX-5 790 — et les rares sont à la limite du bruit — Honda S2000
  10, Mazda RX-8 12, Audi R8 25, Porsche Cayman 29.

Un taux d'accident normalisé par le parc VEH0120 n'existerait donc que pour **17 % des cibles,
précisément les moins rares**. C'est le biais de comparabilité de l'Allemagne
(`docs/methodology.md` §3 bis) en pire, et orienté contre ce que le score récompense : les
cibles rares n'auraient pas « peu d'accidents », elles n'auraient **pas de donnée**, ce qu'un
score ne doit jamais confondre avec zéro. Ni dans le score, ni publié à côté.

## Ce qui rouvrirait la piste

Un libellé DVLA complet (marque + modèle tels qu'immatriculés) dans la table `vehicle`, ou une
table de correspondance publiée entre `generic_make_model` et les modèles DVLA. Ni l'un ni
l'autre n'est publié aujourd'hui.
