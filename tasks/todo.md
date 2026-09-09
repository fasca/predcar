# predcar — Plan de développement (SPEC v2, §7)

## Phase 1 — MVP

### Étape 0 — Bootstrap
- [x] pyproject.toml (uv, Python 3.12), Makefile, ruff, pytest
- [x] config/score.yaml (poids v1), config/sources.yaml
- [x] mapping/*.csv (squelettes avec les 5 modèles témoins)
- [x] data/raw|silver|gold, archive raw avec MANIFEST.json (sha256)
- [x] Schémas silver `fleet_stock` / `fleet_new_reg` + invariants
- [x] README, docs/SOURCES.md, suppression de requirements.txt

### Étape 1 — Ingestion UK (VEH0120, VEH0124, VEH0160)
- [x] Résolution des URLs depuis la page gov.uk, `predcar fetch uk`
- [x] Parseur wide → long (unpivot, marqueurs, statuts, Total vérifié), `predcar ingest uk`
- [x] Tests : périodes, statuts, colonnes manquantes, agrégations, ingestion bout en bout
- [x] **Valider le schéma présumé sur un échantillon réel** (2026-09-08 : VEH0120/VEH0160 conformes,
      VEH0124 corrigé — pas de `Fuel`, `YearManufacture`, `LicenceStatus` présent), liste de
      `docs/sources/dft_uk.md` cochée, URLs dans `docs/SOURCES.md`, MANIFEST.json à committer
- [ ] Ajouter les 5 modèles témoins en snapshot tests sur les données réelles

### Étape 2 — Ingestion RDW (snapshot agrégé mensuel)
- [x] Requête SoQL agrégée (jamais `kenteken`), pagination `$limit`/`$offset`, `predcar fetch nl` / `ingest nl`
- [x] `docs/sources/rdw_nl.md` (schéma présumé + liste de vérification), tests MockTransport
- [x] **Valider sur une réponse réelle** (2026-09-08 : 203 051 lignes, layout conforme, cas
      `handelsbenaming` absent et `jaar` absent ajoutés), liste cochée, MANIFEST.json à committer
- [ ] Planifier le cron mensuel (GitHub Actions) pour `make fetch-nl`

### Étape 3 — Mapping marques/modèles
- [x] `mapping/target_models.csv` (~240 générations cibles), `makes.csv` (alias), `models.csv`
      (règles regex + plages d'années, catch-alls par marque cible)
- [x] `predcar normalize` : application, détection d'ambiguïtés, couverture par pays, rapport
      des non-mappés, échec si < `config/mapping.yaml:min_coverage` (0.95)
- [x] `docs/mapping.md`, tests (règles témoins, pipeline bout en bout)
- [x] **Itérer sur données réelles** (2026-09-08) : retrait du préfixe marque des libellés RDW,
      11 familles de regex trop larges corrigées, règles ajoutées → GB 97,9 %, NL 98,2 %

### Étape 4 — Indicateurs et score v1
- [x] `predcar/metrics.py` : séries annuelles par famille (VEH0120 / VEH0124 / RDW, jamais
      sommées), niveau génération vs modèle générique, attrition lissée, pairs (segment ×
      tranche d'âge, ≥ 3 modèles distincts), attrition relative, inflexion, SORN, survie, rareté,
      agrégat Europe
- [x] `predcar/score.py` : composantes 0–1, poids renormalisés, `min_weight_coverage`,
      `components_available`, rang ; `make score` → gold parquet + `ranking.csv`
- [x] `docs/methodology.md` (source de la page Méthodologie du site)
- [x] Premier run réel (2026-09-08) : 241 cibles avec données, 225 publiées ; les 5 témoins scorés
      avec les 4 composantes
- [x] Corriger les défauts relevés par le diagnostic de `reports/2026-09-08/` (PR #7 : règles
      ST-LINE / TYPE-R / CLIO 16V / VTR / XSI / HGT / Evo, `year_manufacture`, Δt réel, SORN
      génération, anomalies post-production, couverture hors `MODEL MISSING`)
- [ ] Relancer le pipeline et `make export` après fusion de la PR #7, comparer aux valeurs du
      2026-09-08 (Civic Type R EP3, Skyline R33/R34, Evo, Clio 16V)
- [ ] Snapshot tests sur les 5 modèles témoins à partir des valeurs réelles

### Étape 4 bis — Boucle de retour sur données réelles
- [x] `predcar export` → `reports/<date>/` : preuves raw, libellés des marques cibles, couverture,
      anomalies, gold CSV, manifest avec erreurs par étape ; README §6 ; CLAUDE.md
- [x] Premier export réel produit (`reports/2026-09-08/`, 23 fichiers, 0 erreur) — à committer
- [ ] Corriger parseurs / règles / indicateurs d'après le diagnostic

### Étape 5 — Site statique
- [x] `predcar/site.py` + `site/templates/` : classement filtrable (segment / décennie / pays,
      tri score / raréfaction), page par cible (composantes et leur pourquoi, parc par pays,
      attrition, rétention par cohorte, comparaison au segment, sources datées), méthodologie
      depuis `docs/methodology.md`, `ranking.csv` ; `make site`
- [x] `gold/cohorts.parquet` (rétention par cohorte) écrit par `make score`
- [x] `.github/workflows/site.yml` : fetch + pipeline + build + déploiement GitHub Pages,
      cron trimestriel, déclenchement manuel, push sur `main`
- [ ] Activer GitHub Pages (Settings → Pages → Source : GitHub Actions) et vérifier le premier
      déploiement (les URLs DfT sont résolues à chaque run ; un échec = schéma ou couverture)
- [ ] Conserver l'historique RDW côté CI (committer les snapshots agrégés, ~20 Mo/mois, ou un
      cache) pour que l'attrition NL existe un jour sans la machine de l'utilisateur

## Phase 2
- [ ] KBA (DE) : inventaire des XLSX 2010–2026 et schémas par millésime
- [ ] Immatriculations FR (SDES), STATS19, Google Trends, YouTube

## Phase 3
- [ ] Enchères, extrapolation Weibull publiée, newsletter/alertes

---

## Review Notes
- 2026-09-08 : gov.uk et opendata.rdw.nl inaccessibles depuis l'environnement Claude Code
  (proxy). Le parseur DfT est écrit sur un schéma présumé et documenté ; la validation sur
  échantillon réel est la première tâche à faire depuis une machine connectée.
- 2026-09-09 : le réseau fonctionne depuis l'environnement Claude Code (WSL2 de l'utilisateur) :
  premier run complet sur données réelles, export `reports/2026-09-08/` ; diagnostic multi-agents
  en cours, corrections à suivre.
