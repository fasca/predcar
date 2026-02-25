# CarCollector Predictor

## Project Overview

Python tool predicting which used cars will become sought-after collectors (5-10 year horizon). Crosses rarefaction data, reliability, forum sentiment, and market signals to produce a **collector potential score** per model.

**Stack:** Python 3.10+ | SQLite (SQLAlchemy) | Streamlit | Plotly
**UI Language:** French | **Code Language:** English

## Communication

- **TOUJOURS répondre en français** à l'utilisateur (explications, résumés, questions)
- Code, variables, docstrings, logs : en anglais
- Commentaires dans le code : en anglais
- Messages de commit : en français
- Dashboard UI (labels, titres, descriptions) : en français

## Key Commands

```bash
python scripts/seed_database.py       # Init DB with seed data
python scripts/run_collection.py      # Run all data collectors
python scripts/run_analysis.py        # Calculate all scores
streamlit run dashboard/app.py        # Launch dashboard
pytest tests/ -v                      # Run all tests
```

## Architecture

```
collectors/    → Fetch data (DVLA, RDW, forums, marketplaces)
analysis/      → Score calculation from collected data
database/      → SQLAlchemy models, DB init
dashboard/     → Streamlit pages + components
data/          → Static seed JSON files
scripts/       → CLI entry points (collect, analyze, seed)
tests/         → pytest tests mirroring src structure
tasks/         → todo.md + lessons.md (task tracking)
docs/          → SPEC.md (full technical reference)
```

## Style Guide

- Python 3.10+, type hints everywhere
- PEP 8, max line 100 chars
- Google-style docstrings on all public functions
- snake_case functions/vars, PascalCase classes, UPPER_SNAKE constants
- Specific exceptions only, never bare `except:`
- `logging` module only, never `print()` in production
- SQLAlchemy ORM, no raw SQL in business logic
- Group imports: stdlib → third-party → local, alphabetical

## Workflow Rules

### Plan First
- Enter plan mode for ANY task with 3+ steps or architectural decisions
- If something goes sideways, STOP and re-plan — don't keep pushing
- Use plan mode for verification, not just building

### Verify Before Done
- Never mark a task complete without proving it works
- Run tests, check logs, demonstrate correctness
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

### Parc (rarefaction)
- **UK DVLA**: CSV from GOV.UK (VEH0120/VEH0124), quarterly, by make/model
- **NL RDW**: REST API opendata.rdw.nl, all vehicles since 1952, no auth

### Market Signals
- **AutoScout24**: scrape, pan-European
- **mobile.de**: scrape, DE/AT
- **LeBonCoin**: scrape, FR
- **eBay Motors UK**: scrape, UK
- **Marktplaats.nl**: scrape, NL

### Forum Sentiment
- **Forum-Auto.com**, **PistonHeads.com**, **Motor-Talk.de** + brand-specific forums
- Measure: thread count, "cherche"/"WTB" frequency, sentiment keywords

### Reliability
- MOT UK data, RDW APK data, curated `data/known_lemons.json`

## Scoring Formula

```
collector_potential = (
    rarefaction_score     * 0.30 +
    desirability_score    * 0.25 +
    reliability_score     * 0.20 +
    market_momentum_score * 0.15 +
    forum_buzz_score      * 0.10
)
```

## Critical Rules

- All scraping: respect robots.txt, 2-5s delays, rotate User-Agent
- Never store personal data
- DVLA = Open Government Licence v3.0
- RDW = public domain, 1000 rows/request, paginate with $offset
- Forum scraping = aggregate stats only, not individual posts
- Reference: `docs/SPEC.md` for full technical specification
