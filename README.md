# predcar

**Preuve statistique, sourcée et datée, de la raréfaction des modèles automobiles 1990–2015 en Europe**, à partir de données publiques officielles, et score de potentiel « collector » qui en découle.

Périmètre MVP : zéro scraping, zéro compte utilisateur, zéro prix de marché. Un pipeline de données reproductible et un site statique. Spécification complète : [`docs/SPEC.md`](docs/SPEC.md) · fonctionnement de bout en bout : [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) · historique des features : [`CHANGELOG.md`](CHANGELOG.md).

## Stack

Python 3.12 · [uv](https://docs.astral.sh/uv/) · Polars · DuckDB · Pydantic · Typer · Parquet · site statique (GitHub Pages) · `make` + GitHub Actions.

## Installation

```bash
git clone https://github.com/fasca/predcar.git && cd predcar
uv sync            # crée .venv avec Python 3.12 et toutes les dépendances
make test          # 80+ tests, doit être vert
```

## Récupérer les données (à faire depuis votre machine)

> ⚠️ L'environnement Claude Code utilisé pour développer ce dépôt passe par un proxy qui
> **bloque gov.uk, opendata.rdw.nl, kba.de et data.gouv.fr**. Les parseurs ont donc été écrits
> sur des schémas *présumés* et documentés (`docs/sources/*.md`). Les commandes ci-dessous
> doivent être lancées depuis une machine avec accès Internet normal. Elles téléchargent,
> archivent avec checksum, puis parsent ; toute divergence de schéma lève une erreur explicite
> plutôt que de produire de faux chiffres.

### 1. Royaume-Uni — DfT/DVLA (VEH0120, VEH0124, VEH0160)

```bash
make fetch-uk      # résout les URLs des 4 CSV sur la page gov.uk, les archive dans
                   # data/raw/uk_dft/<AAAA-MM-JJ>/ avec MANIFEST.json (sha256, URL, date)
make ingest-uk     # → data/silver/fleet_stock_uk_dft.parquet, fleet_new_reg_uk_dft.parquet
```

Si `make ingest-uk` échoue avec `DftSchemaError` (colonne manquante, statut inconnu, aucune
colonne de période), le layout réel diffère du layout présumé : ouvrir le CSV, corriger
`predcar/ingest/dft.py` et cocher la liste de vérification de
[`docs/sources/dft_uk.md`](docs/sources/dft_uk.md).

### 2. Pays-Bas — RDW (dataset `m9d7-ebf2`)

```bash
make fetch-nl      # une requête SoQL agrégée (marque × modèle × année), paginée,
                   # jamais de kenteken ; archive data/raw/nl_rdw/<AAAA-MM-JJ>/
make ingest-nl     # → data/silver/fleet_stock_nl_rdw_<AAAA-MM-JJ>.parquet
```

Points à confirmer sur la première réponse réelle (liste dans
[`docs/sources/rdw_nl.md`](docs/sources/rdw_nl.md)) : la colonne typée
`datum_eerste_toelating_dt` et `date_extract_y`, le `$limit` de 50 000. À relancer **chaque
mois** : le RDW n'a pas d'historique, on le construit snapshot par snapshot.

### 3. Après les deux premiers runs réussis

1. Committer les `MANIFEST.json` et `query.json` (les payloads sont ignorés par git).
2. Cocher les listes de vérification dans `docs/sources/dft_uk.md` et `docs/sources/rdw_nl.md`.
3. Consigner les URLs vérifiées et la date dans `docs/SOURCES.md`.

### 4. Normaliser marques/modèles

```bash
uv run predcar normalize --min-coverage 0   # première passe : lire le rapport des non-mappés
#   → compléter mapping/models.csv (voir docs/mapping.md)
make normalize                              # échoue si < 95 % du parc des marques cibles est mappé
make validate                               # invariants sur tous les Parquet silver
```

### 5. Indicateurs et score

```bash
make score        # data/gold/indicators.parquet, scores.parquet, ranking.csv (docs/methodology.md)
```

### 6. Exporter les résultats pour analyse à distance

Le développement se fait sans accès aux sources : les schémas, les regex de mapping et les
indicateurs ont été écrits sur des hypothèses. L'export produit un **dossier de preuves,
léger et versionnable**, que vous committez ; il permet à Claude Code d'analyser les vraies
données depuis son environnement et de corriger schémas, règles et bugs.

```bash
make export                       # reports/<AAAA-MM-JJ>/ (marche même si normalize a échoué)
git add data/raw reports && git commit -m "données réelles du <date>" && git push
```

Contenu de `reports/<date>/` :

| Fichier | Contenu | Sert à |
|---|---|---|
| `manifest.json` | commit git, versions, config, comptes, **erreurs par étape** | savoir ce qui a marché |
| `raw/<source>/<date>/*.head.csv` | 60 premières lignes verbatim de chaque CSV | valider le layout présumé |
| `raw/…/*.profile.json` | colonnes, valeurs distinctes des colonnes d'identification, marqueurs `[c]`/`[x]`…, en-têtes de période ; échantillon et types pour le JSON RDW | corriger les parseurs |
| `silver/summary.json` | lignes, périodes, statuts, comptes par fichier silver | cohérence d'ensemble |
| `silver/labels_target_makes.csv` | **tous** les libellés bruts des marques cibles avec leur mapping et leur volume | écrire les règles manquantes |
| `silver/unmapped_target_makes.csv`, `coverage.csv`, `other_makes.csv` | rapport de couverture complet | atteindre 95 % |
| `gold/anomalies.csv` | cohortes en hausse (imports), sauts de stock suspects | repérer glitches et changements de libellé |
| `gold/*.csv` | indicateurs, scores, séries, classement | vérifier les résultats |

Aucun payload brut n'est copié (taille) ; un CSV > 20 Mo est gzippé. Les données sources
sont agrégées, sans donnée personnelle.

## Commandes

| Commande | Effet |
|---|---|
| `make fetch-uk` / `make ingest-uk` | Archive puis parse les CSV DfT/DVLA |
| `make fetch-nl` / `make ingest-nl` | Archive puis parse un snapshot agrégé RDW |
| `make normalize` | Applique `mapping/` → `data/silver/fleet_stock.parquet`, gate de couverture |
| `make score` | Indicateurs (stock, attrition, SORN, inflexion, rareté) + score v1 → `data/gold/` |
| `make export` | Dossier de preuves `reports/<date>/` à committer pour analyse à distance |
| `make validate` | Invariants silver (stock ≥ 0, clés uniques, statuts) |
| `make test` / `make lint` | pytest / ruff |
| `uv run predcar --help` | Toutes les sous-commandes (`fetch`, `ingest`, `normalize`, `score`, `export`, `validate`) |

## Arborescence

```
config/     score.yaml (poids, seuils), mapping.yaml (couverture), sources.yaml (registre des sources)
mapping/    makes.csv, models.csv, target_models.csv — normalisation marque/modèle (docs/mapping.md)
data/       raw/ (immuable, manifest versionné), silver/ (parquet normalisés), gold/ (scores)
predcar/    package : config, raw (archive), schemas (silver + invariants), ingest/, normalize, metrics, score, export, cli
docs/       SPEC.md, ARCHITECTURE.md, SOURCES.md, sources/<source>.md (schémas), mapping.md, methodology.md
tests/      pytest — schémas, invariants, parseurs, mapping, fixtures
reports/    exports datés (preuves de runs réels, committés)
tasks/      todo.md, lessons.md
```

## Sources (phase 1)

| Source | Contenu | Licence |
|---|---|---|
| UK DfT/DVLA VEH0120 / VEH0124 / VEH0160 | Parc trimestriel (Licensed/SORN), cohortes par année de 1re immatriculation, immatriculations neuves | OGL v3.0 |
| NL RDW `m9d7-ebf2` | Parc actuel véhicule par véhicule, agrégé côté API, snapshot mensuel | CC0 |

Phase 2 : KBA (DE), SDES (FR), STATS19, Google Trends, YouTube. Voir `docs/SOURCES.md`.

## Score v1

```
score = 0.35·rareté + 0.25·conservation + 0.20·ratio_SORN + 0.20·point_inflexion_récent
```

Composantes normalisées 0–1, orientées « plus haut = plus collector », pondérations dans `config/score.yaml`. Composante manquante = exclue et poids renormalisés, jamais imputée à 0. Formules, sources et limites : [`docs/methodology.md`](docs/methodology.md).

## Licence

MIT. Données : voir les licences de chaque source dans `docs/SOURCES.md`.
