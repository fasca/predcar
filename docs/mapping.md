# Normalisation marque/modèle (`mapping/`)

Trois fichiers CSV, appliqués par `make normalize` (`predcar normalize`) à tous les Parquet
silver ingérés. Résultat : `data/silver/fleet_stock.parquet`, `fleet_new_reg.parquet` et
`mapping_coverage.parquet`.

## `makes.csv` — `alias,make[,model_regex]`

Libellé brut (DfT `Make`, RDW `merk`, KBA `Hersteller`) → marque canonique. Un libellé absent
du fichier est conservé tel quel (identité). Exemples : `VAUXHALL → OPEL`,
`MERCEDES → MERCEDES-BENZ`, `VW → VOLKSWAGEN`.

La troisième colonne, **optionnelle**, rend la marque **conditionnelle au libellé du modèle** :

```csv
BMW,BMW,
BMW,MINI,^(MINI\b|COOPER|CLUBMAN|JOHN ?COOPER ?WORKS|…)
DAIMLER (D),SMART,^(EQ )?(FORTWO|FORFOUR|…)
```

Un constructeur n'est pas toujours une marque : le KBA vend les MINI sous `BMW` et les Smart
sous `DAIMLER (D)`, or **MINI et Smart sont des marques cibles**. Sans cette colonne, leurs
5,1 millions de véhicules allemands seraient crédités à BMW et Mercedes-Benz, et les cibles
MINI Cooper S et Smart Roadster n'auraient aucun parc allemand.

La surcharge s'applique sur `make_raw` **avant** toute règle de modèle, donc le reste du
pipeline voit la vraie marque. Une ligne sans `model_regex` reste l'alias inconditionnel de sa
marque ; les deux formes coexistent pour un même alias. Le même mécanisme réglera les groupes
multi-marques (`FCA`, `STELLANTIS`, `GENERAL MOTORS`, `JAGUAR LAND ROVER`).

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

**Élargir la liste** : `make candidates` (`predcar candidates`) écrit
`reports/<date>/candidates.csv` — les modèles mappés, absents de la liste, dont le parc GB
(VEH0120, hors SORN) a perdu au moins la moitié de son maximum, avec le parc au pic, le parc
actuel, la perte, et les cibles que la marque a déjà (pour repérer une `306` à côté d'une
`306 S16 MK1`). Seuils dans `config/mapping.yaml: candidates`. **L'outil propose, la liste se
décide à la main** : une cible est une génération avec ses années de production, ce que la
donnée ne porte pas. Retenir un candidat = lui donner ses générations, ses années, et ses
règles dans `models.csv`, comme pour toute cible.

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

État (2026-09-13, `reports/2026-09-13/silver/coverage.csv`) : couverture **GB 99,0 %**,
**NL 98,4 %**, **DE 98,5 %** (immatriculations neuves GB 99,2 %), hors libellés `unknown_labels`. La première
passe (2026-09-08 : GB 97,9 %, NL 98,2 %) avait révélé 11 familles de regex trop larges
(`^900` capturait `9000`, `^MX-3` capturait `MX-30`, `^C2` capturait `C25`, `^ASTRA` capturait
`ASTRAVAN`…) : toute règle sur un libellé numérique ou court se termine par `\b`. Le plus gros
reste non mappé est `MODEL MISSING` (DfT), volontairement laissé sans `model_gen`.

## Particularités allemandes (KBA)

Les libellés du KBA ne se comportent pas comme ceux du DfT ou du RDW, et trois familles de
pièges s'ajoutent à celles ci-dessus :

- **Le constructeur n'est pas la marque.** `Hersteller` est un groupe industriel avec un suffixe
  pays (`VOLKSWAGEN (D)`, `MAZDA (B/J/USA/RC)`) ; `mapping/makes.csv` porte un alias par forme.
  Les groupes multi-marques (`FCA (I)`, `STELLANTIS (F)`, `GENERAL MOTORS`, `JAGUAR LAND ROVER`,
  `MG ROVER`) sont résolus par la même colonne `model_regex` : une ligne **sans** regex porte la
  marque dominante du groupe, les lignes conditionnelles les autres. Les regex d'un même groupe
  sont tenues **disjointes**, pour que l'ordre de déclaration n'ait jamais d'effet.
- **Des marques filles sont vendues sous leur maison mère** : MINI sous `BMW`, Smart sous
  `DAIMLER (D)`, Dacia sous `RENAULT (F)`, Cupra sous `SEAT (E)`. Quand la marque fille n'est pas
  une cible (Dacia, Cupra), un fourre-tout suffit. Quand elle en est une (**MINI**, **SMART**),
  un fourre-tout serait faux — il attribuerait des MINI à BMW : ces lignes restent délibérément
  non mappées, voir `tasks/todo.md`.
- **Un libellé peut en contenir plusieurs**, séparés par une virgule ou un point-virgule :
  `8D,AUDI A4,S4`, `BUSINESS;MULTIVAN`, `VW 1600,KAEFER 1303 LS`. Une règle ancrée sur `^` rate
  tout ce qui suit le premier nom. Corollaire : une regex ne peut pas contenir de virgule, le
  fichier est un CSV — utiliser `\W` ou une classe explicite.

Deux pièges d'inversion rencontrés, où l'ordre des mots change le modèle :
`CUPRA LEON` (marque Cupra, après 2018) n'est **pas** la cible `LEON CUPRA` (Seat, 1999–2012),
et `AMG C 43` n'est pas la cible `C43 AMG`. Les règles ancrées les distinguent naturellement ;
une regex non ancrée les confondrait.
