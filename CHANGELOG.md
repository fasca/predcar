# Changelog

Toutes les évolutions notables de predcar, par pull request fusionnée. Format inspiré de
[Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) ; pas encore de version publiée,
tout est dans « Non publié » jusqu'à la première release (fin de phase 1).

Chaque entrée signale aussi ce qui reste **non validé sur données réelles**. L'accès aux
sources dépend de l'environnement et se revérifie à chaque session (leçon du 2026-09-09) :
il fonctionne depuis le WSL2 de l'utilisateur et, au 2026-09-12, depuis l'environnement
Claude Code. Voir `docs/ARCHITECTURE.md` §7.

## Non publié

### 2026-09-12 — PR : site statique (phase 1, étape 5)
**Ajouté**
- `predcar site` / `make site` (`predcar/site.py`, gabarits Jinja2 dans `site/templates/`,
  CSS/JS dans `site/static/`) : site statique en français rendu vers `site/dist/` (non versionné).
  - Classement des cibles publiées avec filtres segment / décennie / pays et tri (score,
    « se raréfient le plus vite / le moins vite », parc le plus faible), top 50 par défaut,
    barres des quatre composantes, liste repliée des cibles à score non publié et pourquoi.
  - Une page par génération cible : rang et score, tableau des composantes (valeur, poids,
    part du score, explication), parc par pays, attrition lissée, rétention par cohorte,
    comparaison au segment (médiane des pairs, nombre de pairs, inflexion, ratio SORN),
    sources citées avec dernière observation et licence, date des données.
  - Page méthodologie rendue depuis `docs/methodology.md`, précédée des paramètres réels de
    `config/score.yaml` ; classement téléchargeable (`ranking.csv` et une copie datée
    `predcar-classement-<date>.csv`).
  - Graphiques Plotly.js chargés depuis le CDN, données embarquées dans chaque page ; message
    de repli si le CDN est inaccessible ; axe des parcs à zéro.
- `data/gold/cohorts.parquet` (`metrics.cohort_retention`) : courbes de rétention agrégées par
  (cible, pays, cohorte d'immatriculation), `retention = stock / stock maximal observé`.
- `.github/workflows/pages.yml` : build et déploiement GitHub Pages sur push touchant `site/`,
  `reports/`, `predcar/site.py`, `docs/methodology.md` ou `config/score.yaml`, `workflow_call`
  et déclenchement manuel. Aucun accès réseau aux sources, aucun run de pipeline.
- `.github/workflows/refresh.yml` : cron trimestriel (20 janvier / avril / juillet / octobre),
  pipeline complet, export, **tests rejoués sur le nouveau bundle avant tout commit** (un
  relabellisage DfT ou une dérive de couverture échoue là, pas en production), compression du
  snapshot RDW, commit, puis appel explicite du déploiement.
- Tests (13 → 14 sur le site, 220 au total) : rendu complet sur la population synthétique,
  formats français, JSON embarqué qui ne peut pas fermer la balise `<script>`, **égalité
  stricte entre un build depuis le Parquet d'un run et depuis le CSV d'un bundle**, bundle
  incomplet ignoré, absence de chemin absolu dans les pages, cohorte à une seule observation
  nommée et non dessinée.

**Le site lit le dernier bundle committé, pas `data/gold/`**
`site.resolve_gold_dir()` prend le `gold/` du plus récent `reports/<date>/` contenant
`gold/ranking.csv` (un export dont l'étape `score` a échoué est sauté, pas une erreur), et la
**date affichée est celle du bundle**, pas celle du rendu. Conséquences : un déploiement prend
quelques secondes au lieu de ~190 Mo et 20 minutes, ne casse pas si gov.uk est momentanément
indisponible ou si la gate de couverture échoue, et ce que le site affiche est reproductible
depuis le dépôt seul. `--gold-dir data/gold` rend un run local frais. `export.latest_report()`
accepte un critère de complétude plutôt que de dupliquer la recherche du dernier bundle.

**Honnêteté des graphiques** — le site prétend mesurer un déclin :
- l'axe des parcs démarre à zéro (un axe tronqué exagère exactement ce qu'on mesure) ;
- une cohorte observée **une seule fois** (toutes les cohortes RDW tant que les snapshots
  mensuels ne se sont pas accumulés) est **exclue** de la courbe de rétention et **nommée** sous
  le graphique avec la raison : normalisée par elle-même elle afficherait 100 %, ce qui se
  lirait « rien n'a encore disparu » ;
- une composante absente est signalée absente (poids renormalisés), jamais dessinée à 0 ;
- la page dit que `sorn_ratio` est le ratio brut repris *tel quel* comme composante, sinon la
  carte « part SORN » et la barre de composante semblent mesurer deux choses différentes.

**Modifié**
- `metrics.COHORTS_SCHEMA` rendu public (il était lu comme membre privé depuis `site.py`).
- `score.py` : suppression de `is_finite()`, morte depuis son introduction. `pyproject.toml` :
  `duckdb` documenté comme outil de requêtes ad-hoc, non importé par le paquet.
- Suppression de `tasks/next.md` : `tasks/todo.md` (le plan) et `tasks/lessons.md` (les règles)
  suffisent — trois fichiers de reprise concurrents finissent par se contredire, voir la leçon
  du 2026-09-12 sur les branches ouvertes.
- `docs/ARCHITECTURE.md`, `README.md` §7, `CLAUDE.md`, `docs/methodology.md` §7 alignés.

**Vérifié sur données réelles** — rendu depuis `reports/2026-09-12/` : 242 cibles, 228 classées,
aucun lien interne cassé, et les 5 témoins conformes au bundle (parc et rang) : M3 E46 4 863
(rang 72), S2000 3 801 (64), 205 GTI 1 989 (43), Clio Williams 142 (100), RS2 34 (4) — les
parcs à −1 viennent du snapshot RDW du 2026-09-08 rejoué à la place de celui du 12, jamais
committé (voir l'entrée du run réel).
**Restent à observer sur GitHub** : le premier déploiement Pages (opt-in *Settings → Pages →
Source : GitHub Actions* requis) et les deux crons. La courbe de rétention par cohorte
n'apparaîtra qu'au premier bundle exporté après cette PR, `cohorts.csv` n'existant dans aucun
bundle antérieur.

### 2026-09-12 — PR : cron mensuel RDW et archives brutes compressées
**Ajouté**
- `.github/workflows/rdw-snapshot.yml` : tous les 1ᵉʳ du mois (03h17 UTC) + `workflow_dispatch`.
  Il archive un snapshot agrégé, **vérifie qu'il est exploitable** (`ingest nl` avant tout
  commit, pour ne jamais versionner une réponse tronquée), le compresse et committe
  `MANIFEST.json` + `*.json.gz` sur `main`.
- `predcar compress nl` / `make compress-nl` et `raw.compress()`, `raw.resolve()`,
  `raw.read_bytes()` : une archive brute peut être stockée gzippée. Le manifest garde le
  sha256 du contenu **décompressé**, donc compresser ne change pas l'identité d'un fichier —
  `raw.verify()` et `rdw.ingest()` relisent l'un ou l'autre de façon transparente.
- `.gitignore` : les snapshots RDW gzippés sont versionnés (exception documentée).

**Pourquoi versionner ce payload-là** — le RDW est un instantané *sans historique amont* : un
mois qui n'est pas conservé est perdu pour toujours, et c'est précisément l'historique que le
projet cherche à construire. Un cron qui ne committerait que le `MANIFEST.json` archiverait
l'empreinte de données qu'on n'a plus. Gzippé, un mois pèse 1,2 Mo (contre 16,7 Mo brut) — soit
~14 Mo/an, acceptable. Les CSV DfT restent hors de git : 66 Mo et re-téléchargeables depuis
gov.uk avec tout leur historique.

**Modifié**
- `export.py` retrouve un payload archivé qu'il soit compressé ou non (`raw.resolve`), et
  profile la version décompressée ; la branche CSV/JSON suit le nom du manifest, pas le
  suffixe du fichier stocké.

### 2026-09-12 — PR : snapshot tests des 5 témoins et filet anti-régression
**Ajouté**
- `tests/witnesses.py` : les 5 modèles témoins de SPEC §8 (BMW M3 E46, Peugeot 205 GTI,
  Honda S2000, Renault Clio Williams, Audi RS2) avec leurs libellés réels, leurs libellés
  pièges et des bornes de stock larges (≈ ×5/÷5 autour du run de référence).
- `tests/test_witnesses.py` (45 cas) : deux couches indépendantes — *mapping* (les libellés
  réels du bundle rejoués dans les règles **courantes**, les finitions ne doivent pas tomber
  sur la cible) et *gold* (bornes de stock, invariant **EU = GB + NL**, série de niveau
  génération, 4 composantes de score, stock GB décroissant).
- `tests/test_real_labels.py` (13 cas) : filet générique sur **tous** les libellés réels —
  aucun conflit de règle, couverture ≥ 95 % par pays rejouée hors code de production, toute
  cible atteignable depuis un libellé réel (allowlist documentée : `FORD / RACING PUMA`), et
  une table `KEYWORD_RULES` qui encode chaque bug déjà survenu (ST-LINE, TYPE-R, 16V, VTR,
  XSI, Evo).
- `predcar.export.latest_report()` et `paths.REPORTS_DIR` : accès au bundle le plus récent.
- Fixtures de session partagées dans `tests/conftest.py` (`report`, `real_labels`,
  `real_labels_mapped`, `gold`, `stock_frame`) ; `tests/test_normalize.py` réutilise
  `stock_frame` au lieu de sa copie locale.

**Conception** — aucune nouvelle fixture figée : `reports/<date>/` est déjà versionné, donc la
CI y a accès sans réseau ni `data/`. Le bundle sert de **corpus d'entrée** (`model_raw`), jamais
d'oracle de mapping : ses colonnes `model_gen` / `generation` datent des règles du jour de
l'export. Seuls `gold/*.csv` servent d'oracle, en bornes larges insensibles à une republication
trimestrielle. Les tests tournent dans la CI existante, sans marqueur ni `skipif`.

**Vérifié par mutation** — en réintroduisant chaque bug historique, les tests échouent bien :
`TYPE[- ]?R` → `TYPE R` (2 échecs), lookahead `(?!-?LINE)` retiré (2 échecs), `year_manufacture`
ignoré (2 échecs), précédence des libellés retirée (1 échec). 142 → 200 tests.

**Limite assumée** — `labels_target_makes.csv` ne porte pas d'année : le filet générique ne peut
pas couvrir le bug « année d'immatriculation au lieu d'année de fabrication ». Il est couvert par
`test_witnesses.py::test_generation_uses_build_year` (seule la M3 est discriminée par l'année,
les 4 autres témoins portent leur génération dans le libellé — le contraste est asserté) et par
`test_normalize.py::test_generation_uses_build_year_before_first_registration_year`.

### 2026-09-12 — PR : re-run réel post-PR #7 et précédence des règles de libellé
**Corrigé**
- `normalize.apply` : une règle dont le **libellé porte lui-même la génération** (pas de plage
  d'années) l'emporte désormais sur une règle à plage d'années, comme `docs/methodology.md` §1
  le décrit déjà. Sans cette précédence, `M3 CSL` (année enregistrée 2012) et
  `LANCER EVOLUTION IX GT` / `EVO VIII GSR` faisaient échouer toute la normalisation
  (`MappingError`, 264 lignes, 168 véhicules, 0 conflit de `model_gen`). Les fourre-tout sans
  génération (`^PUMA(?!.*RACING)`) restent des replis et ne prennent pas le dessus — deux tests
  verrouillent les deux sens. Le bug était invisible avant #7 : c'est la priorité donnée à
  `year_manufacture` qui a déplacé les années de référence et créé les recouvrements.

**Ajouté**
- `reports/2026-09-12/` : premier bundle de preuves produit **après** la PR #7. Les 4 CSV DfT
  sont bit-à-bit identiques à ceux du 2026-09-08 (mêmes sha256), donc tout écart mesuré vient
  des corrections, pas d'un nouveau millésime.

**Résultats mesurés (2026-09-08 → 2026-09-12, stock Europe)**
| Cible | Avant | Après |
|---|---|---|
| HONDA CIVIC TYPE R EP3 | 2 (rang 31) | 4 139 (rang 48) |
| HONDA CIVIC TYPE R FN2 / EK9 | 1 978 / 2 | 7 174 / 38 (EK9 rang 5) |
| NISSAN SKYLINE GT-R R32 / R33 / R34 | 16 / 34 / 24 | 162 / 206 / 117 |
| MITSUBISHI LANCER EVOLUTION V_VI / VII_IX | 38 / 528 | 256 / 651 |
| RENAULT CLIO 16V MK1 | 148 | 264 |
| FORD FIESTA ST MK7 | 36 784 | 21 997 (ST-LINE retirées) |
| Couverture GB / NL (stock) | 0,9788 / 0,9820 | **0,9899 / 0,9840** |
| Anomalies | 1 123 (935 `cohort_rise` VEH0120) | **82**, toutes VEH0124 |
| Cibles avec données / publiées | 241 / 225 | 242 / 228 |

Témoins stables et cohérents (invariant EU = GB + NL vérifié, 4 composantes, couverture de
poids 1,0) : M3 E46 4 864, S2000 3 801, 205 GTI 1 990, Clio Williams 142, RS2 34.

**Connu, non corrigé**
- `predcar export` parcourt tous les dossiers `data/raw/<source>/<date>/` : sur un clone frais,
  les snapshots anciens n'ont que leur `MANIFEST.json` et produisent une erreur par payload
  absent (6 ici). Les trois étapes restent `ok` ; à traiter à part.

### 2026-09-09 — PR #7 : corrections d'après le premier export réel
**Corrigé (diagnostic de `reports/2026-09-08/`)**
- Mapping : `FIESTA ST-LINE` / `FOCUS ST-LINE` ne sont plus des ST (1,3 M et 1,0 M véhicules
  mal classés) ; `CIVIC TYPE-R` (tiret) rejoint la Civic Type R (2,8 M véhicules ratés, EP3
  comptée à 1 exemplaire) ; `CLIO DYNAMIQUE 16V` et consorts ne sont plus des Clio 16V MK1
  (12 M véhicules) ; `SAXO VTR`, `XSARA VTR`, `C2 VTR` ne sont plus des VTS ; `306 XSI` n'est
  plus une S16 ; `PUNTO HGT` n'est plus une Punto GT ; `CORSA GSI` n'est plus une VXR ; les
  Lancer Evo prennent leur génération du numéro dans le libellé (`EVO VI`) et non de l'année
  d'immatriculation en GB ; libellés RDW et DfT exotiques (`09-MAR` = 9-3, `380 SL`, `AMG A 35`,
  `8D AUDI A4`, `2CV6`, campers) ; repli sans génération pour les années hors plage (Puma).
  Couverture recalculée sur les libellés réels : GB 99,0 %, NL 98,5 %.
- Génération des imports : `year_manufacture` (VEH0124 `YearManufacture`) conservé dans le
  schéma silver et utilisé avant l'année de première immatriculation pour placer une voiture
  dans sa génération (une Skyline de 1999 immatriculée en GB en 2010 restait une R34).
- Attrition : Δt en années réelles entre dates d'observation (le trimestre Q1 2026 après le
  Q4 2025 comptait pour une année entière de pertes).
- Ratio SORN au niveau génération (VEH0124 porte le statut), repli modèle générique.
- Anomalies : seulement les vraies cohortes (VEH0124, RDW) après la fin de production ; les
  montées en charge d'un modèle neuf et les générations déduites du libellé (VEH0120) ne sont
  plus signalées (1 123 « anomalies » dont l'immense majorité était du bruit).
- Couverture : les libellés `MODEL MISSING` / `(MISSING)` / `ONBEKEND` sont comptés à part et
  exclus du dénominateur (`config/mapping.yaml: unknown_labels`).
- Export : `manifest.json.stages` (`ok` / `absent` / `failed`) ; `uv run` dans le cycle documenté.

**Ajouté**
- `CHANGELOG.md`, `docs/ARCHITECTURE.md`, liens dans le README, règle « une entrée par PR ».

### 2026-09-09 — commit direct sur `main` (session Claude Code locale) : premier run réel
**Modifié**
- VEH0124 : schéma réel (pas de `Fuel`, `YearManufacture`, `LicenceStatus` Licensed/SORN
  présent), marqueur `[z]` massif, `[x]` dans les années → seau « année inconnue ».
- RDW : lignes sans `handelsbenaming` → `(MISSING)`, lignes sans année ; préfixe marque
  retiré des libellés (`TOYOTA AYGO` → `AYGO`), familles BMW (`3ER REIHE`).
- `models.csv` : 11 familles de regex trop larges corrigées (`\b`), règles ajoutées ; couverture
  GB 97,9 %, NL 98,2 % ; 241 cibles avec données, 225 publiées.
- Docs des sources cochées sur les fichiers réels, `docs/SOURCES.md` avec URLs vérifiées,
  `reports/2026-09-08/` committé, leçons dans `tasks/lessons.md`.

### 2026-09-08 — PR #6 : export des résultats pour analyse à distance
**Ajouté**
- `predcar export` / `make export` : dossier de preuves `reports/<date>/` léger et
  versionnable — manifest (commit git, versions, config, comptes, erreurs par étape),
  60 premières lignes verbatim et profil de chaque CSV brut, profil du JSON RDW, résumé
  silver, tous les libellés bruts des marques cibles avec mapping et volume, non-mappés
  complets, couverture, anomalies (cohortes en hausse, sauts de stock), gold en CSV.
- Best-effort : `manifest.json` consigne l'état de chaque étape (`stages` : `ok`, `absent`
  quand il n'y avait rien à exporter, `failed` avec le détail dans `errors`) et le reste est
  écrit quand même.
- README §6 (commandes à lancer et à committer), `CLAUDE.md` : lire le dernier export en
  début de session.

### 2026-09-08 — PR #5 : indicateurs et score v1 (phase 1, étape 4)
**Ajouté**
- `predcar/metrics.py` : séries annuelles par famille de source (VEH0120, VEH0124, RDW,
  jamais additionnées), niveau génération ou modèle générique, attrition −Δln(Stock)/Δt
  lissée sur 3 ans, pairs (même pays, segment, tranche d'âge de 5 ans, ≥ 3 modèles
  distincts), attrition relative, point d'inflexion, ratio SORN, ventes cumulées, survie,
  étiquette de rareté, agrégat Europe.
- `predcar/score.py` : composantes 0–1, poids renormalisés sur les composantes disponibles,
  gate `min_weight_coverage`, `components_available`, rang ; `predcar score` / `make score`
  → `data/gold/` + `ranking.csv`.
- `config/score.yaml` : `peers.age_bucket_years`, `peers.min_peers`.
- `docs/methodology.md` : chaque formule, chaque source, chaque limite.

**Corrigé (review)**
- Identité des cibles `(marque, modèle, génération)` : SPIDER Alfa Romeo et SPIDER Renault
  ne sont plus fusionnées.
- Repli sur le stock du modèle générique seulement si la génération est la seule de son
  modèle ; un modèle seul dans son segment n'est pas son propre pair ; somme Europe nulle
  si nulle partout ; run d'inflexion réinitialisée sur année manquante ; `ranking.csv`
  limité aux cibles publiées ; `data/gold/*.csv` hors git.

### 2026-09-08 — PR #4 : mapping marques/modèles et `normalize` (phase 1, étape 3)
**Ajouté**
- `mapping/target_models.csv` (~240 générations cibles 1990–2015), `makes.csv` (alias),
  `models.csv` (règles regex + plages d'années disjointes, fourre-tout par marque).
- `predcar/normalize.py` et `predcar normalize` / `make normalize` : application des règles,
  détection des règles contradictoires, couverture par pays, rapport des non-mappés,
  `CoverageError` sous `config/mapping.yaml:min_coverage` (0.95), `--min-coverage 0` pour
  explorer.
- README « Récupérer les données (à faire depuis votre machine) », `docs/mapping.md`.

**Corrigé (review)**
- Conflits `NSX`, `POLO GTI`, `SCIROCCO` entre fourre-tout et règles cibles ; sorties
  écrites seulement après la gate de couverture ; test systématique sur toutes les cibles.

### 2026-09-08 — PR #3 : ingestion RDW (phase 1, étape 2)
**Ajouté**
- `predcar/ingest/rdw.py` : requête SoQL agrégée côté serveur (marque × modèle × année de
  première admission), garde-fou contre tout champ personnel (`kenteken`), pagination
  stable, archive immuable lignes + requête, parse → `fleet_stock` NL (période = date du
  snapshot). `predcar fetch nl` / `ingest nl`, `make fetch-nl` / `ingest-nl`.
- `docs/sources/rdw_nl.md` (schéma présumé + liste de vérification).

**Corrigé (review)**
- `date_extract_y(datum_eerste_toelating_dt)` au lieu de `substring` sur un champ Number ;
  réponse vide refusée avant écriture ; écriture atomique ; `query.json` exigé.

### 2026-09-08 — PR #2 : bootstrap v2 et ingestion UK DfT (phase 1, étape 1)
**Ajouté**
- Projet uv / Python 3.12 / Polars / DuckDB / Pydantic / Typer, Makefile, ruff, pytest, CI
  GitHub Actions ; `config/score.yaml`, `config/sources.yaml` ; archive raw immuable avec
  `MANIFEST.json` (sha256) ; schémas silver `fleet_stock` / `fleet_new_reg` et invariants.
- `predcar/ingest/dft.py` : résolution des URLs sur la page gov.uk, unpivot des tables
  VEH0120 / VEH0124 / VEH0160, voitures uniquement, marqueurs de suppression rejetés,
  `Total` vérifié = Licensed + SORN. `predcar fetch uk` / `ingest uk` / `validate`.
- `docs/sources/dft_uk.md`, `docs/SOURCES.md`, README v2 ; `requirements.txt` supprimé.

**Corrigé (review)**
- Snapshot incomplet refusé ; totaux vérifiés seulement si les deux statuts sont visibles ;
  téléchargement atomique et refus d'écraser un snapshot.

### 2026-09-08 — PR #1 : spécification v2
**Modifié**
- `docs/SPEC.md` remplacé par la spec MVP v2 (open data uniquement, zéro scraping, zéro
  prix) ; `CLAUDE.md` aligné ; `CLAUDE_CODE_PROMPT.md` supprimé.

**Corrigé (review)**
- Composante d'attrition orientée (`conservation = −attrition_relative`) ; règle de
  composantes manquantes (exclusion + renormalisation) ; génération attribuée depuis
  l'année de première immatriculation uniquement ; courbes de rétention agrégées à la place
  de Kaplan-Meier.

### Validé sur données réelles (dernier état : 2026-09-12)
- Validé au 2026-09-08 : layout des CSV DfT, réponse de l'API RDW, couverture du mapping,
  241 cibles scorées avec les quatre composantes.
- Vérifié depuis, par le re-run du 2026-09-12 (`reports/2026-09-12/`) : l'effet de
  `year_manufacture` sur les générations des imports (Skyline R32/R33/R34 séparées, Evo par le
  numéro du libellé), la distribution des composantes après correction des règles, et le stock
  des cibles témoins — Civic Type R EP3 à 4 139 exemplaires au lieu de 1.
- Reste à observer sur GitHub : le premier déploiement Pages et les crons (mensuel RDW,
  trimestriel de rafraîchissement).
