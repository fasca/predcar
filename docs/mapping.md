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
`handelsbenaming`, en majuscules) **débarrassé d'un éventuel préfixe marque** : le RDW écrit
`TOYOTA AYGO`, `ALFA GIULIETTA`, `HONDA S2000` là où DfT écrit `AYGO`. Tout alias de la marque
(`makes.csv`) suivi d'un espace est retiré avant le test, sauf s'il ne resterait rien (`MINI`).
`model_raw` lui-même n'est jamais modifié.

| Cas | `year_from`/`year_to` | Effet |
|---|---|---|
| Le libellé seul identifie la génération (`^M3 CSL`, `^S ?2000`) | vides | `model_gen` + `generation`, quelle que soit l'année, y compris VEH0120 sans année |
| Le libellé couvre plusieurs générations (`^M3\b`) | une ligne par génération, plages **disjointes** | `generation` selon l'année de fabrication si la source la donne (VEH0124), sinon `year_first_reg` ; si l'année est absente → `model_gen` seul |
| Le libellé couvre plusieurs générations mais certaines années n'en sont aucune (`^PUMA` 2003–2018) | une ligne supplémentaire sans plage ni génération | `model_gen` seul pour ces années, au lieu de rien |
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
`model_gen`. Les libellés par lesquels la source déclare elle-même le modèle inconnu
(`config/mapping.yaml: unknown_labels`, ex. `MODEL MISSING` du DfT, 1 % du parc GB des
marques cibles) sont comptés à part et exclus du dénominateur : rien ne pourra jamais les
mapper. Seuil dans `config/mapping.yaml` (`min_coverage: 0.95`, SPEC §4).

Pièges rencontrés sur les libellés réels (2026-09-08), à garder en tête pour toute nouvelle
règle : une finition qui contient le nom d'une version sportive (`FIESTA ST-LINE`, `GOLF
R-LINE`, `CLIO DYNAMIQUE 16V`, `CIVIC TYPE-S`), un tiret ou un espace variable (`TYPE-R`,
`TYPE R`), une version inférieure au nom proche (`SAXO VTR` ≠ `VTS`, `306 XSI` ≠ `S16`,
`PUNTO HGT` ≠ `GT`), un libellé abîmé par un tableur (`09-MAR` pour `9-3`). Sous le seuil,
`normalize` échoue et journalise les plus gros groupes non mappés
(`report_top_unmapped`) : c'est la boucle d'itération sur données réelles.

```bash
uv run predcar normalize --min-coverage 0    # explorer sans échouer, lire le rapport
# → ajouter les règles manquantes dans mapping/models.csv, relancer
make normalize                               # seuil de config/mapping.yaml
```

État (2026-09-08, premières données réelles) : couverture **GB 97,9 %**, **NL 98,2 %**
(immatriculations neuves GB 98,1 %). La première passe a révélé 11 familles de regex trop larges
(`^900` capturait `9000`, `^MX-3` capturait `MX-30`, `^C2` capturait `C25`, `^ASTRA` capturait
`ASTRAVAN`…) : toute règle sur un libellé numérique ou court se termine par `\b`. Le plus gros
reste non mappé est `MODEL MISSING` (DfT), volontairement laissé sans `model_gen`.
