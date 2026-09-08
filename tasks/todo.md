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
- [ ] **Valider le schéma présumé sur un échantillon réel** (`make fetch-uk` sur une machine
      avec accès à gov.uk), cocher la liste de `docs/sources/dft_uk.md`, consigner l'URL dans
      `docs/SOURCES.md`, committer le MANIFEST.json
- [ ] Ajouter les 5 modèles témoins en snapshot tests sur les données réelles

### Étape 2 — Ingestion RDW (snapshot agrégé mensuel)
- [x] Requête SoQL agrégée (jamais `kenteken`), pagination `$limit`/`$offset`, `predcar fetch nl` / `ingest nl`
- [x] `docs/sources/rdw_nl.md` (schéma présumé + liste de vérification), tests MockTransport
- [ ] **Valider sur une réponse réelle** (`make fetch-nl` depuis une machine connectée), cocher
      la liste, committer le MANIFEST.json ; planifier le cron mensuel (GitHub Actions)

### Étape 3 — Mapping marques/modèles
- [x] `mapping/target_models.csv` (~240 générations cibles), `makes.csv` (alias), `models.csv`
      (règles regex + plages d'années, catch-alls par marque cible)
- [x] `predcar normalize` : application, détection d'ambiguïtés, couverture par pays, rapport
      des non-mappés, échec si < `config/mapping.yaml:min_coverage` (0.95)
- [x] `docs/mapping.md`, tests (règles témoins, pipeline bout en bout)
- [ ] **Itérer sur données réelles** : `predcar normalize --min-coverage 0`, compléter
      `models.csv` jusqu'à ≥ 95 % GB et NL

### Étape 4 — Indicateurs et score v1
- [ ] Stock, survie, attrition (lissage 3 ans), attrition relative, ratio SORN, inflexion, rareté
- [ ] Score composite, composantes manquantes renormalisées, `components_available`

### Étape 5 — Site statique
- [ ] Classement, page modèle, méthodologie, export CSV ; GitHub Pages ; cron trimestriel

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
