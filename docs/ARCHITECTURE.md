# Architecture — comment predcar fonctionne

## 1. En une phrase

predcar télécharge des statistiques publiques de parc automobile (UK, NL), les normalise
dans un schéma commun, reconnaît ~240 générations de modèles cibles 1990–2015, mesure à
quelle vitesse chacune disparaît de la route par rapport à ses pairs, et en tire un score de
potentiel « collector » dont chaque composante est visible.

## 2. Le flux de données

```
                 make fetch-uk / fetch-nl              make ingest-uk / ingest-nl
 sources ──────────────────────────► data/raw/ ─────────────────────────────► data/silver/
 (gov.uk, RDW)   immuable + sha256    <source>/<date>/     unpivot, typage,      fleet_stock_*.parquet
                                       MANIFEST.json       invariants            fleet_new_reg_*.parquet
                                                                                        │
                                                                     make normalize     │  mapping/
                                                                                        ▼
                                                                                  data/silver/
                                                                                  fleet_stock.parquet
                                                                                  fleet_new_reg.parquet
                                                                                  mapping_coverage.parquet
                                                                                        │
                                                                     make score         │  config/score.yaml
                                                                                        ▼
                                                                                  data/gold/
                                                                                  stock_series / indicators
                                                                                  scores / cohorts / ranking.csv
                                                                                        │
                                                          make export ◄─────────────────┼──────────────► make site
                                                                │                                             │
                                                                ▼                                             ▼
                                                     reports/<date>/ (committé)                 site/dist/ (GitHub Pages)
```

Trois couches, comme dans la spec §3 :

| Couche | Contenu | Versionné dans git ? |
|---|---|---|
| `data/raw/` | fichiers sources tels que téléchargés, un dossier par source et par date, `MANIFEST.json` (URL, sha256, taille, date) | manifests oui, payloads non (60 Mo+) |
| `data/silver/` | Parquet au schéma commun `fleet_stock` / `fleet_new_reg` (`predcar/schemas.py`) | non |
| `data/gold/` | indicateurs, scores, courbes de rétention par cohorte | non |
| `site/dist/` | site statique généré depuis gold (déployé sur GitHub Pages) | non |
| `reports/<date>/` | preuves d'un run réel (voir §7) | **oui** |

## 3. Les modules Python (`predcar/`)

| Module | Rôle | Entrée → sortie |
|---|---|---|
| `paths.py` | chemins du projet (`PREDCAR_ROOT` pour les tests) | — |
| `config.py` | modèles Pydantic de `config/score.yaml`, `mapping.yaml`, `sources.yaml` ; poids validés à la somme 1 | YAML → objets typés |
| `raw.py` | archive immuable : téléchargement atomique (`.part` puis rename), refus d'écraser, manifest sha256, `verify`, `latest_snapshot` | URL → `data/raw/<source>/<date>/` |
| `schemas.py` | schémas silver, `conform` (sélection + cast), invariants (`count ≥ 0`, clés uniques, statuts connus, colonnes non nulles) | DataFrame → DataFrame validé |
| `ingest/dft.py` | UK DfT/DVLA : résolution des URLs des CSV sur la page gov.uk, lecture « wide » (une colonne par trimestre ou année), unpivot, voitures uniquement, marqueurs `[c]`/`[x]`/`[z]` → ligne supprimée, `Total` vérifié = Licensed + SORN, snapshot complet exigé | raw → `fleet_stock_uk_dft.parquet`, `fleet_new_reg_uk_dft.parquet` |
| `ingest/rdw.py` | NL RDW : une requête SoQL **agrégée côté serveur** (marque × modèle × année de première admission), jamais de plaque, pagination, archive lignes + requête, réponse vide refusée | API → `fleet_stock_nl_rdw_<date>.parquet` |
| `normalize.py` | applique `mapping/` : alias de marque, règles regex + plages d'années → `make`, `model_gen`, `generation` ; règles contradictoires = erreur ; couverture par pays et gate à 95 % ; rien n'est écrit si la gate échoue | silver ingérés → `fleet_stock.parquet`, `fleet_new_reg.parquet`, `mapping_coverage.parquet` |
| `metrics.py` | séries annuelles par famille de source, choix du niveau (génération / modèle), attrition lissée, pairs, attrition relative, inflexion, SORN, ventes cumulées, survie, rareté, agrégat Europe | silver normalisé → indicateurs |
| `score.py` | composantes 0–1, poids renormalisés, gate de publication, rang | indicateurs → `scores.parquet`, `ranking.csv` |
| `export.py` | dossier de preuves best-effort pour l'analyse à distance | tout → `reports/<date>/` |
| `site.py` | site statique : classement filtrable, une page par cible (parc par pays, attrition, rétention par cohorte, composantes du score et leur *pourquoi*, sources datées), méthodologie rendue depuis `docs/methodology.md`, `ranking.csv` ; gabarits Jinja2 dans `site/templates/`, Plotly.js par CDN | gold → `site/dist/` |
| `cli.py` | Typer : `fetch uk|nl`, `ingest uk|nl`, `normalize`, `score`, `export`, `site`, `validate` | — |

Chaque transformation est une fonction pure : même raw → même silver → même gold.

## 4. Les trois niveaux de données, et pourquoi ils ne se mélangent pas

Les sources décrivent le même parc à des granularités différentes :

| Famille | Pays | Granularité | Niveau | Apporte |
|---|---|---|---|---|
| VEH0120 | GB | trimestriel depuis 1994 | modèle générique (pas d'année) | long historique, **SORN** |
| VEH0124 | GB | annuel depuis 2014 | génération (année de 1re immatriculation) | cohortes |
| VEH0160 | GB | trimestriel depuis 2001 | modèle générique | ventes neuves |
| RDW | NL | un snapshot par mois, depuis notre premier | génération | stock NL |

Règles (`metrics.py`) : deux familles ne sont **jamais additionnées** ; pour une génération
cible on prend la série de niveau génération si elle existe, sinon la série de niveau modèle,
et seulement si la génération est la seule de son modèle ; le ratio SORN vient toujours de
VEH0120 ; le niveau utilisé est exposé dans les sorties.

## 5. Le mapping, « le vrai travail » (spec §4)

`mapping/target_models.csv` liste les cibles `(marque, modèle, génération, segment, années)`.
`makes.csv` ramène les libellés bruts de marque à une forme canonique. `models.csv` contient
les règles : une regex sur le libellé brut, une plage d'années optionnelle, un `model_gen` et
une `generation`. Trois cas :

- le libellé seul identifie la génération (`^M3 CSL`) → règle sans plage ;
- le libellé couvre plusieurs générations (`^M3\b`) → une règle par génération, plages
  disjointes, la génération vient de l'année de première immatriculation ;
- ligne sans année (VEH0120) → `model_gen` seul, pas de génération.

Les fourre-tout par marque (`^3[0-9][0-9]` → `3 SERIES`) ne servent qu'à la couverture. Toute
ligne qui matche deux `model_gen` différents fait échouer la normalisation : c'est un bug de
règle, pas un choix à faire en silence. Détails : `docs/mapping.md`.

## 6. Le score (spec §5, `docs/methodology.md`)

```
score = 0.35·rareté + 0.25·conservation + 0.20·ratio_SORN + 0.20·point_inflexion_récent
```

- **rareté** : 1 pour le stock le plus faible de la population (min-max sur −ln stock) ;
- **conservation** : rang de −attrition relative (disparaît moins vite que ses pairs = haut) ;
- **ratio SORN** : part du parc GB déjà retirée de la route mais conservée ;
- **inflexion récente** : 1 si l'attrition est passée sous la médiane des pairs il y a moins
  de 5 ans.

Une composante absente est exclue et les poids restants renormalisés ; le score n'est
publié qu'avec au moins 60 % de poids couverts. Tout paramètre est dans
`config/score.yaml`, jamais dans le code.

## 7. La boucle de retour sur données réelles

L'environnement Claude Code **dans le cloud** (claude.ai/code) passe par un proxy qui bloque
gov.uk, opendata.rdw.nl, kba.de et data.gouv.fr ; Claude Code lancé **depuis un terminal sur
la machine de l'utilisateur** (WSL2, 2026-09-08) accède aux sources. Les parseurs, les regex
et la distribution des indicateurs ont d'abord été écrits sur des schémas présumés, puis
validés et corrigés sur le premier run réel (`reports/2026-09-08/`, `CHANGELOG.md`). Le cycle
prévu, quel que soit l'endroit où tourne le pipeline :

1. l'utilisateur lance, depuis une machine connectée, `make fetch-uk ingest-uk fetch-nl
   ingest-nl`, `uv run predcar normalize --min-coverage 0`, `make score`, `make export` ;
2. il committe `data/raw/**/MANIFEST.json` et `reports/<date>/` ;
3. Claude Code lit `reports/<date>/manifest.json` en début de session (`stages` dit quelles
   étapes ont tourné, `errors` pourquoi une étape a échoué), corrige parseurs,
   règles et indicateurs à partir des preuves (en-têtes verbatim, profils, libellés réels,
   anomalies), puis relance le cycle.

Une divergence de schéma lève toujours une erreur explicite (`DftSchemaError`,
`RdwSchemaError`, `MappingError`, `CoverageError`) plutôt que de produire de faux chiffres.

## 8. Qualité

- 147 tests pytest : maths des indicateurs, schémas, invariants, parseurs sur fixtures,
  toutes les cibles du mapping résolues sans conflit, pipeline bout en bout, export, site.
- ruff (lint + format), CI GitHub Actions sur chaque PR.
- Reviews automatiques (Codex) traitées et résolues à chaque PR ; leçons dans
  `tasks/lessons.md`.

## 9. Le site et son déploiement

`make site` rend `site/dist/` **uniquement depuis `data/gold/`** (jamais silver ni raw) :

- `index.html` : classement des cibles publiées, filtres segment / décennie / pays et tri
  (score, raréfaction la plus rapide ou la plus lente, parc le plus faible) côté client,
  top 50 par défaut, liste repliée des cibles avec données mais score non publié ;
- `modeles/<marque-modèle-génération>.html` : une page par cible, publiée ou non — score et
  chaque composante avec poids, part et *pourquoi*, parc par pays, attrition lissée,
  rétention par cohorte (VEH0124 ; NL après plusieurs snapshots), comparaison au segment,
  sources citées avec dernière observation et licence, date de génération ;
- `methodologie.html` : `docs/methodology.md` rendu, précédé des paramètres réels de
  `config/score.yaml` ;
- `ranking.csv` : export du classement (cibles publiées).

`.github/workflows/site.yml` reconstruit tout depuis les sources officielles (fetch, ingest,
normalize, score, site) et déploie sur GitHub Pages : cron trimestriel (le 20 des mois de
janvier, avril, juillet, octobre, après les publications DfT), déclenchement manuel, et
chaque push sur `main`. Le run échoue — plutôt que de publier de faux chiffres — si un schéma
source change ou si la couverture du mapping passe sous 95 %. Limite : le snapshot RDW
téléchargé par le workflow n'est pas conservé, l'historique néerlandais se construit sur la
machine de l'utilisateur (voir `tasks/todo.md`).

## 10. Ce qui n'existe pas encore

- Phase 2 : KBA (DE), immatriculations FR, STATS19, Google Trends, YouTube.
- Phase 3 : enchères, extrapolation Weibull, alertes.
