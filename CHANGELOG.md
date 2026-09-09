# Changelog

Toutes les évolutions notables de predcar, par pull request fusionnée. Format inspiré de
[Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) ; pas encore de version publiée,
tout est dans « Non publié » jusqu'à la première release (fin de phase 1).

Chaque entrée signale aussi ce qui reste **non validé sur données réelles** : l'environnement
de développement n'atteint pas les sources (proxy), voir `docs/ARCHITECTURE.md` §7.

## Non publié

### 2026-09-09 — PR #8 : site statique (phase 1, étape 5)
**Ajouté**
- `predcar site` / `make site` (`predcar/site.py`, gabarits Jinja2 dans `site/templates/`,
  CSS/JS dans `site/static/`) : site statique en français généré uniquement depuis
  `data/gold/` vers `site/dist/` (non versionné).
  - Classement des cibles publiées avec filtres segment / décennie / pays et tri (score,
    « se raréfient le plus vite / le moins vite », parc le plus faible), top 50 par défaut,
    barres des quatre composantes, liste repliée des cibles à score non publié et pourquoi.
  - Une page par génération cible : rang et score, tableau des composantes (valeur, poids,
    part du score, explication), parc par pays, attrition lissée, rétention par cohorte,
    comparaison au segment (médiane des pairs, nombre de pairs, inflexion, ratio SORN),
    sources citées avec dernière observation et licence, date de génération.
  - Page méthodologie rendue depuis `docs/methodology.md`, précédée des paramètres réels de
    `config/score.yaml` ; `ranking.csv` téléchargeable.
  - Graphiques Plotly.js chargés depuis le CDN, données embarquées dans chaque page ; message
    de repli si le CDN est inaccessible.
- `data/gold/cohorts.parquet` (`metrics.cohort_retention`) : courbes de rétention agrégées par
  (cible, pays, cohorte d'immatriculation), `retention = stock / stock maximal observé`.
- `.github/workflows/site.yml` : fetch des sources officielles, pipeline complet, build et
  déploiement GitHub Pages — cron trimestriel (20 janvier / avril / juillet / octobre),
  déclenchement manuel, push sur `main`.
- Tests : rendu complet du site sur la population synthétique (pages, classement, cibles non
  publiées, méthodologie, JSON embarqué sûr), formats français, rétention par cohorte.

**Modifié**
- `docs/ARCHITECTURE.md` §9 (site et déploiement), README §7, CLAUDE.md (`make site` n'est
  plus « planned »), `docs/methodology.md` §7 (`cohorts.parquet`).

**Non validé sur données réelles** : le rendu a été vérifié sur l'export
`reports/2026-09-08/` (241 pages, 225 classées) ; le premier déploiement Pages et le cron
restent à observer sur GitHub.

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

### Validé sur données réelles (2026-09-08) et reste à vérifier
- Validé : layout des CSV DfT, réponse de l'API RDW, couverture du mapping, 241 cibles scorées
  avec les quatre composantes.
- À vérifier au prochain run : effet de `year_manufacture` sur les générations des imports
  (Skyline, Evo, Supra), distribution des composantes après correction des règles, stock des
  cibles témoins (Civic Type R EP3 attendu en centaines, plus 1).
