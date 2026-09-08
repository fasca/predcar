# Source : UK DfT / DVLA — Vehicle licensing statistics (VEH0120, VEH0124, VEH0160)

**Statut : schéma *présumé*, à valider contre un échantillon réel.**
L'environnement de développement de la première itération n'avait pas accès à `gov.uk`
(proxy sortant). Le layout ci-dessous est celui décrit dans la spec et connu des publications
DfT ; il doit être confirmé par `make fetch-uk` puis `make ingest-uk` sur une machine avec
accès réseau. Toute divergence lève `DftSchemaError` avec le détail (colonne manquante, statut
inconnu, aucune colonne de période) : corriger `predcar/ingest/dft.py` **et** ce document.

Page : https://www.gov.uk/government/statistical-data-sets/vehicle-licensing-statistics-data-files
Licence : Open Government Licence v3.0.
Les URLs des CSV changent à chaque publication (`assets.publishing.service.gov.uk/media/<id>/…`) ;
elles sont résolues à la volée depuis la page par nom de fichier (`resolve_asset_urls`).

## Layout commun

Tables « larges » : colonnes d'identification puis **une colonne par période**, la plus
récente en premier.

| Fichier | Colonnes d'identification | Colonnes de période | Silver |
|---|---|---|---|
| `df_VEH0120_GB.csv` | `BodyType, Make, GenModel, Model, Fuel, LicenceStatus` | `YYYY Qn` (1994 Q4 →) | `fleet_stock`, `status` = licensed / sorn |
| `df_VEH0124_AM.csv`, `df_VEH0124_NZ.csv` | `BodyType, Make, GenModel, Model, Fuel, YearFirstUsed, YearOfManufacture` | `YYYY` (2014 →) | `fleet_stock`, `status` = licensed, `year_first_reg` = `YearFirstUsed` |
| `df_VEH0160_GB.csv` | `BodyType, Make, GenModel, Model, Fuel` | `YYYY Qn` (2001 →) | `fleet_new_reg` |

Points à vérifier sur l'échantillon réel (cases à cocher) :

- [ ] Noms exacts des colonnes d'identification (casse, espaces).
- [ ] Format des en-têtes de période (`2024 Q2` vs `2024Q2` — les deux sont acceptés).
- [ ] Valeurs de `LicenceStatus` : `Licensed`, `SORN`, et présence ou non d'une ligne `Total`.
- [ ] Marqueurs de suppression / non-disponibilité : `[c]`, `[x]`, `[z]`, `[low]`, `:`, `-`.
- [ ] Séparateur de milliers dans les valeurs (`1,200`) — accepté.
- [ ] Valeur exacte de `BodyType` pour les voitures (`Cars`).
- [ ] VEH0124 : présence éventuelle d'une colonne `LicenceStatus` (supposée absente : licensed only).

## Règles de parsing

- **Voitures uniquement** : `BodyType == "Cars"`.
- **Périodes** : `YYYY Qn` → dernier jour du trimestre ; `YYYY` → 31 décembre.
- **Comptes** : entiers, virgules de milliers retirées. Tout marqueur non numérique
  (`[c]`, `[x]`, `[z]`, `[low]`, `:`, `-`, vide) → ligne **supprimée** (jamais imputée à 0),
  nombre de lignes supprimées journalisé.
- **Statut** (VEH0120) : `Licensed` → `licensed`, `SORN` → `sorn`. Une ligne `Total`/`All`,
  si présente, est vérifiée (`licensed + sorn == total` par modèle et période, uniquement
  quand les deux statuts sont visibles, sinon `InvariantError`) puis supprimée. Tout autre
  libellé → `DftSchemaError`.
- **Snapshot complet** : l'ingestion exige les quatre fichiers présents sur disque **et** dans
  `MANIFEST.json` ; un fetch partiel n'est jamais ingéré. Un snapshot est immuable : refetch le
  même jour → erreur, jamais d'écrasement.
- **Agrégation** : somme sur `Fuel` et `YearOfManufacture` ; `make_raw`, `model_gen_raw`
  (`GenModel`), `model_raw` (`Model`) sont conservés en majuscules, tels que fournis.
- **Colonnes de normalisation** (`make`, `model_gen`, `generation`) : nulles à cette étape,
  remplies en phase 1 étape 3 (mapping).

## Écart au schéma silver de la spec

`model_gen_raw` est ajouté à `fleet_stock` et `fleet_new_reg` (§3 ne prévoit que `model_raw`)
car DfT fournit deux niveaux (`GenModel` regroupé, `Model` variante exacte) et le MVP travaille
au niveau `GenModel` tout en ayant besoin de la variante pour détecter les générations depuis le
libellé (§4). `fleet_new_reg` porte aussi `make_raw`, `model_raw`, `source_file` pour la
traçabilité.
