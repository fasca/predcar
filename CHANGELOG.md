# Changelog

Toutes les évolutions notables de predcar, par pull request fusionnée. Format inspiré de
[Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) ; pas encore de version publiée,
tout est dans « Non publié » jusqu'à la première release (fin de phase 1).

Chaque entrée signale aussi ce qui reste **non validé sur données réelles** : l'environnement
de développement n'atteint pas les sources (proxy), voir `docs/ARCHITECTURE.md` §7.

## Non publié

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

### Non validé sur données réelles (à ce jour)
- Layout des CSV DfT (`docs/sources/dft_uk.md`), réponse de l'API RDW
  (`docs/sources/rdw_nl.md`), regex de `mapping/models.csv`, distribution des composantes
  du score. Premier `make export` réel attendu.
