# Normalisation marque/modèle (`mapping/`)

Trois fichiers CSV, appliqués par `make normalize` (`predcar normalize`) à tous les Parquet
silver ingérés. Résultat : `data/silver/fleet_stock.parquet`, `fleet_new_reg.parquet` et
`mapping_coverage.parquet`.

## `makes.csv` — `alias,make`

Libellé brut (DfT `Make`, RDW `merk`) → marque canonique. Un libellé absent du fichier est
conservé tel quel (identité). Exemples : `VAUXHALL → OPEL`, `MERCEDES → MERCEDES-BENZ`,
`VW → VOLKSWAGEN`.

## `models.csv` — `make,model_raw_regex,year_from,year_to,model_gen,generation`

Une règle s'applique quand la marque canonique vaut `make` **et** que la regex (insensible à
la casse, recherche non ancrée : mettre `^`) matche `model_raw` (DfT `Model`, RDW
`handelsbenaming`, en majuscules).

| Cas | `year_from`/`year_to` | Effet |
|---|---|---|
| Le libellé seul identifie la génération (`^M3 CSL`, `^S ?2000`) | vides | `model_gen` + `generation`, quelle que soit l'année, y compris VEH0120 sans année |
| Le libellé couvre plusieurs générations (`^M3\b`) | une ligne par génération, plages **disjointes** | `generation` selon `year_first_reg` ; si l'année est absente → `model_gen` seul |
| Modèle non cible d'une marque cible (`^3[0-9][0-9]` → `3 SERIES`) | vides | `model_gen` seul, sert la couverture |

Règles de cohérence, vérifiées à l'exécution (`MappingError`) :

- toutes les règles qui matchent une même ligne doivent donner le **même `model_gen`** →
  exclure les variantes sportives des règles génériques avec un lookahead négatif :
  `^206(?!.*(GTI|RC\b))` ;
- les plages d'années d'un même libellé ne doivent pas se chevaucher ;
- chaque `(make, model_gen, generation)` de `target_models.csv` doit être produit par au
  moins une règle.

## `target_models.csv` — `make,model_gen,generation,segment,year_from,year_to`

Liste cible (~240 générations, 1990–2015, segments `SPORTIVE`, `GTI`, `COUPE`, `ROADSTER`,
`PREMIUM`, `SUPERCAR`). Ses **marques** définissent le périmètre de la couverture.

## Couverture

Par pays, part (en nombre de véhicules) des lignes des marques cibles qui obtiennent un
`model_gen`. Seuil dans `config/mapping.yaml` (`min_coverage: 0.95`, SPEC §4). Sous le seuil,
`normalize` échoue et journalise les plus gros groupes non mappés
(`report_top_unmapped`) : c'est la boucle d'itération sur données réelles.

```bash
uv run predcar normalize --min-coverage 0    # explorer sans échouer, lire le rapport
# → ajouter les règles manquantes dans mapping/models.csv, relancer
make normalize                               # seuil de config/mapping.yaml
```

État : les règles ont été écrites **sans accès aux libellés réels** (proxy). Elles sont
testées sur des libellés témoins (`tests/test_normalize.py`) ; la première passe sur données
réelles produira certainement un rapport non vide à traiter.
