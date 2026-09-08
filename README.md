# predcar

**Preuve statistique, sourcée et datée, de la raréfaction des modèles automobiles 1990–2015 en Europe**, à partir de données publiques officielles, et score de potentiel « collector » qui en découle.

Périmètre MVP : zéro scraping, zéro compte utilisateur, zéro prix de marché. Un pipeline de données reproductible et un site statique. Spécification complète : [`docs/SPEC.md`](docs/SPEC.md).

## Stack

Python 3.12 · [uv](https://docs.astral.sh/uv/) · Polars · DuckDB · Pydantic · Typer · Parquet · site statique (GitHub Pages) · `make` + GitHub Actions.

## Démarrage

```bash
uv sync                 # dépendances
make fetch-uk           # archive les CSV DfT/DVLA dans data/raw/uk_dft/<date>/ (+ MANIFEST.json sha256)
make ingest-uk          # data/silver/fleet_stock_uk_dft.parquet, fleet_new_reg_uk_dft.parquet
make validate           # invariants silver
make test               # pytest
make lint               # ruff
```

## Arborescence

```
config/     score.yaml (poids, seuils), sources.yaml (registre des sources)
mapping/    makes.csv, models.csv, target_models.csv — normalisation marque/modèle
data/       raw/ (immuable, manifest versionné), silver/ (parquet normalisés), gold/ (scores)
predcar/    package : config, raw (archive), schemas (silver + invariants), ingest/, cli
docs/       SPEC.md, SOURCES.md (URLs + licences), sources/<source>.md (schémas observés)
tests/      pytest — schémas, invariants, parseurs, fixtures
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

Composantes normalisées 0–1, orientées « plus haut = plus collector », pondérations dans `config/score.yaml`. Composante manquante = exclue et poids renormalisés, jamais imputée à 0.

## Licence

MIT. Données : voir les licences de chaque source dans `docs/SOURCES.md`.
