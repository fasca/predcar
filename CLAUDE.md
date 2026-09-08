# predcar — CarCollector Predictor

## Project Overview

Python data pipeline producing a **sourced, dated statistical proof** of the rarefaction of
1990–2015 car models in Europe, built only from official open data, and deriving a
**collector potential score** per model/generation.

**MVP scope (v2):** zero scraping, zero user accounts, zero market prices. A reproducible
Parquet pipeline + a static site.

**Stack:** Python 3.12 | Polars | DuckDB | Pydantic | Typer | uv | static site (Astro or
MkDocs + Plotly) | `make` + GitHub Actions (monthly cron) | GitHub Pages
**UI Language:** French | **Code Language:** English

## Communication

- **TOUJOURS répondre en français** à l'utilisateur (explications, résumés, questions)
- Code, variables, docstrings, logs : en anglais
- Commentaires dans le code : en anglais
- Messages de commit : en français
- Site (labels, titres, page méthodologie) : en français

## Key Commands

Planned targets (to be created in phase 1; keep this list in sync with the `Makefile`):

```bash
uv sync                          # Install dependencies
make ingest-uk                   # Download + normalize DfT/DVLA files (VEH0120/0124/0160)
make ingest-rdw                  # Monthly aggregated RDW snapshot (SoQL, no personal data)
make normalize                   # Apply mapping/ → data/silver/, fail if coverage < 95 %
make score                       # Indicators + score v1 → data/gold/
make site                        # Build static site from data/gold/
uv run pytest tests/ -v          # Run all tests
```

## Architecture

```
data/raw/      → Immutable downloads, <source>/<YYYY-MM-DD>/<file>, with checksum
data/silver/   → Normalized Parquet, common schemas (fleet_stock, fleet_new_reg)
data/gold/     → Aggregates, indicators, scores (input of the site)
mapping/       → makes.csv, models.csv, target_models.csv (make/model normalization)
config/        → score.yaml (ALL score weights and thresholds)
predcar/       → Python package: ingestion, normalization, metrics, Typer CLI
site/          → Static site generator sources
docs/          → SPEC.md (reference), SOURCES.md (URLs + licences), sources/<source>.md
tests/         → pytest: schema per source vintage, invariants, snapshot tests
tasks/         → todo.md + lessons.md (task tracking)
```

## Style Guide

- Python 3.12, type hints everywhere
- PEP 8, max line 100 chars
- Google-style docstrings on all public functions
- snake_case functions/vars, PascalCase classes, UPPER_SNAKE constants
- Specific exceptions only, never bare `except:`
- `logging` module only, never `print()` in production
- Polars for all dataframes (no pandas), DuckDB for ad-hoc queries over Parquet
- Pydantic models for every source schema and config file
- Transformations are pure functions: same raw input → same silver/gold output
- Group imports: stdlib → third-party → local, alphabetical

## Workflow Rules

### Plan First
- Enter plan mode for ANY task with 3+ steps or architectural decisions
- One phase-step per PR (see `docs/SPEC.md` §7)
- If something goes sideways, STOP and re-plan — don't keep pushing
- Use plan mode for verification, not just building

### Source-First (before any parser)
1. Download a sample of the source into `data/raw/`
2. Document the observed schema in `docs/sources/<source>.md`
3. Write the schema tests
4. **Then** write the parser
- Uncertain URL (KBA, data.gouv) → verify with an HTTP request, record the final URL
  in `docs/SOURCES.md`

### Verify Before Done
- Never mark a task complete without proving it works
- Run tests, check logs, demonstrate correctness
- Invariants must hold: stock ≥ 0, licensed + SORN consistent, cohorts non-increasing
  except imports (log a rise as an anomaly, do not reject it)
- Snapshot tests on 5 witness models: BMW E46 M3, Peugeot 205 GTI, Honda S2000,
  Renault Clio Williams, Audi RS2
- Ask: "Would a staff engineer approve this?"

### Self-Improvement
- After ANY correction: update `tasks/lessons.md`
- Write rules that prevent the same mistake
- Review lessons at session start

### Code Quality
- **Simplicity First**: Minimal code, minimal impact
- **No Laziness**: Root causes only, no temp fixes
- **DRY**: Flag repetition, deduplicate immediately
- **Engineered enough**: Not hacky, not over-abstracted
- **Edge cases**: Handle more, not fewer
- **Explicit > Clever**

### Task Tracking
1. Write plan to `tasks/todo.md` with checkable items
2. Check in before starting implementation
3. Mark items complete as you go
4. Update `tasks/lessons.md` after corrections

## Data Sources

### Phase 1 (MVP)
- **UK DfT/DVLA**: CSV from GOV.UK — `df_VEH0120_GB` (quarterly stock, Licensed/SORN),
  `df_VEH0124_AM`/`_NZ` (stock by first-registration year, annual), `df_VEH0160_GB`
  (first registrations). Work at `GenModel` level + manual generation mapping.
- **NL RDW**: Socrata dataset `m9d7-ebf2`, aggregated server-side with `$select`/`$group`.
  Snapshot only (no history) → archive a monthly snapshot in `data/raw/rdw/YYYY-MM/`.

### Phase 2
- **DE KBA**: FZ 10 / FZ 17 XLSX (multi-line headers, labels change per vintage)
- **FR SDES / data.gouv.fr**: new registrations by model only (no stock by model)
- **STATS19** (UK accidents), **Google Trends** (pytrends), **YouTube Data API**

### Phase 3 (optional)
- Public auction results (Collecting Cars, Car & Classic, Catawiki, BaT, Aguttes…)
- Marketplaces only if value is demonstrated, with robots.txt + rate limiting

## Indicators and Score

Per (model_gen, generation, country), then aggregated for Europe:
Stock(t), Survival(t), annual attrition (−Δln(Stock)/Δt, 3-year smoothing),
relative attrition vs. same segment/age, SORN ratio (UK), inflection point, absolute rarity.

```
score = 0.35 * rarity
      + 0.25 * conservation          # = -relative_attrition
      + 0.20 * sorn_ratio
      + 0.20 * recent_inflection_point
```

- Every component is normalized 0–1 and oriented "higher = more collector"
- Missing components (e.g. `sorn_ratio` outside UK) are excluded and the remaining weights
  renormalized — never imputed as 0; publish only if weight coverage ≥ `min_weight_coverage`
- Cohort survival = aggregated retention curves, **not Kaplan-Meier** (no individual events)
- Generation is assigned from `year_first_reg` (VEH0124, RDW); VEH0120 rows without a year
  stay at `model_gen` level unless the label itself is discriminant

Weights and thresholds live in `config/score.yaml` — **never hardcoded**. Every component
is exposed individually on the site (show the *why*, not just the rank).

## Critical Rules

- **No marketplace scraping in phases 1–2.** No forum scraping at all.
- Never store personal data: RDW `kenteken` is never downloaded, always aggregate via API
- Every raw file is archived immutably with a checksum; transformations are replayable
- The normalization step fails if < 95 % of a country's fleet is mapped for target makes
- Source licences documented in `docs/SOURCES.md` (OGL v3 UK, CC0 RDW, DL-DE/BY-2-0 KBA,
  Licence Ouverte FR)
- Reference: `docs/SPEC.md` for the full specification
