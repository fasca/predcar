# Source : UK DfT / DVLA — Vehicle licensing statistics (VEH0120, VEH0124, VEH0160)

**Statut : schéma observé sur les fichiers réels du 2026-09-08** (`data/raw/uk_dft/2026-09-08/`,
publication DfT du 13 juillet 2026 pour VEH0120/VEH0160, du 27 avril 2026 pour VEH0124). La première
version du parseur avait été écrite sur un schéma présumé : VEH0120 et VEH0160 étaient conformes,
**VEH0124 ne l'était pas** (pas de colonne `Fuel`, `YearManufacture` et non `YearOfManufacture`,
et une colonne `LicenceStatus` Licensed/SORN supposée absente). Toute divergence future lève
`DftSchemaError` avec le détail : corriger `predcar/ingest/dft.py` **et** ce document.

Page : https://www.gov.uk/government/statistical-data-sets/vehicle-licensing-statistics-data-files
Licence : Open Government Licence v3.0.
Les URLs des CSV changent à chaque publication (`assets.publishing.service.gov.uk/media/<id>/…`) ;
elles sont résolues à la volée depuis la page par nom de fichier (`resolve_asset_urls`).

## Layout commun

Tables « larges » : colonnes d'identification puis **une colonne par période**, la plus
récente en premier.

| Fichier | Colonnes d'identification | Colonnes de période | Silver |
|---|---|---|---|
| `df_VEH0120_GB.csv` | `BodyType, Make, GenModel, Model, Fuel, LicenceStatus` | `YYYY Qn` (2026 Q1 → 1994 Q4, 85 colonnes) | `fleet_stock`, `status` = licensed / sorn |
| `df_VEH0124_AM.csv`, `df_VEH0124_NZ.csv` | `BodyType, Make, GenModel, Model, YearFirstUsed, YearManufacture, LicenceStatus` | `YYYY` (2025 → 2014) | `fleet_stock`, `status` = licensed / sorn, `year_first_reg` = `YearFirstUsed` |
| `df_VEH0160_GB.csv` | `BodyType, Make, GenModel, Model, Fuel` | `YYYY Qn` (2026 Q1 → 2001 Q1, 101 colonnes) | `fleet_new_reg` |

Liste de vérification, cochée sur les fichiers du 2026-09-08 :

- [x] Noms exacts des colonnes d'identification : ceux du tableau ci-dessus, sans espace parasite.
- [x] Format des en-têtes de période : `2024 Q2` (avec espace) ; `2024Q2` reste accepté.
- [x] Valeurs de `LicenceStatus` : `Licensed`, `SORN` uniquement, **aucune ligne `Total`** (VEH0120
      245 043 lignes : 141 869 Licensed, 103 174 SORN ; VEH0124_AM 566 977 lignes : 319 492 / 247 485).
      La vérification `licensed + sorn == total` reste codée au cas où une publication en ajouterait.
- [x] Marqueurs : VEH0120 et VEH0160 n'en contiennent aucun ; VEH0124 contient `[z]` massivement
      (376 903 cellules voitures dans AM, 230 228 dans NZ : année de parc antérieure à la 1re mise en
      circulation) et `[x]` dans `YearFirstUsed` / `YearManufacture` (cohortes supprimées : 86 525 lignes
      voitures dans AM, soit 1,7 % des véhicules 2025 → seau « année inconnue », jamais rejeté).
- [x] Pas de séparateur de milliers observé (accepté quand même).
- [x] `BodyType` voitures = `Cars` (autres valeurs : Light goods vehicles, Motorcycles, Other vehicles,
      Heavy goods vehicles, Buses and coaches).
- [x] VEH0124 : colonne `LicenceStatus` **présente** (Licensed / SORN), contrairement à l'hypothèse
      initiale ; pas de colonne `Fuel`.

## Règles de parsing

- **Voitures uniquement** : `BodyType == "Cars"`.
- **Périodes** : `YYYY Qn` → dernier jour du trimestre ; `YYYY` → 31 décembre.
- **Comptes** : entiers, virgules de milliers retirées. Tout marqueur non numérique
  (`[c]`, `[x]`, `[z]`, `[low]`, `:`, `-`, vide) → ligne **supprimée** (jamais imputée à 0),
  nombre de lignes supprimées journalisé.
- **Statut** (VEH0120 et VEH0124) : `Licensed` → `licensed`, `SORN` → `sorn`. Une ligne
  `Total`/`All`, si présente, est vérifiée (`licensed + sorn == total` par modèle, cohorte et
  période, uniquement quand les deux statuts sont visibles, sinon `InvariantError`) puis
  supprimée. Tout autre libellé → `DftSchemaError`.
- **Année de 1re mise en circulation** (VEH0124) : `YearFirstUsed` entier ; `[x]` → `year_first_reg`
  null (seau « année inconnue », nombre de lignes journalisé).
- **Snapshot complet** : l'ingestion exige les quatre fichiers présents sur disque **et** dans
  `MANIFEST.json` ; un fetch partiel n'est jamais ingéré. Un snapshot est immuable : refetch le
  même jour → erreur, jamais d'écrasement.
- **Année de fabrication** (VEH0124) : `YearManufacture` conservée dans `year_manufacture` (`[x]` → null) ;
  c'est elle qui place une voiture importée dans sa génération (`docs/mapping.md`).
- **Agrégation** : somme sur `Fuel` (VEH0120, VEH0160) ; `make_raw`, `model_gen_raw`
  (`GenModel`), `model_raw` (`Model`) sont conservés en majuscules, tels que fournis.
- **Colonnes de normalisation** (`make`, `model_gen`, `generation`) : nulles à cette étape,
  remplies en phase 1 étape 3 (mapping).

## Écart au schéma silver de la spec

`model_gen_raw` est ajouté à `fleet_stock` et `fleet_new_reg` (§3 ne prévoit que `model_raw`)
car DfT fournit deux niveaux (`GenModel` regroupé, `Model` variante exacte) et le MVP travaille
au niveau `GenModel` tout en ayant besoin de la variante pour détecter les générations depuis le
libellé (§4). `fleet_new_reg` porte aussi `make_raw`, `model_raw`, `source_file` pour la
traçabilité.
