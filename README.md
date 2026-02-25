# 🚗 CarCollector Predictor

**Predict which used cars will become valuable collectors in 5-10 years.**

CarCollector Predictor crosses vehicle rarefaction data, mechanical reliability, community sentiment from forums, and market signals to produce a **collector potential score** for each model.

## How It Works?

1. **Rarefaction tracking** — How fast is each model disappearing from the road? (UK DVLA, NL RDW data)
2. **Reliability filtering** — Exclude badly-designed models ("lemons") that disappear due to mechanical failure, not collectibility
3. **Forum sentiment** — Early buzz on enthusiast forums is a leading indicator of rising collector interest
4. **Market signals** — Price trends and listing volumes across 5 European marketplaces

## Data Sources

| Source | Type | Coverage | Update |
|--------|------|----------|--------|
| UK DVLA (GOV.UK) | Vehicles in circulation by model | UK | Quarterly |
| NL RDW (Open API) | All registered vehicles since 1952 | Netherlands | Real-time |
| AutoScout24 | Listings & prices | Pan-European | Weekly |
| mobile.de | Listings & prices | DE, AT | Weekly |
| LeBonCoin | Listings & prices | France | Weekly |
| eBay Motors | Listings & prices | UK | Weekly |
| Marktplaats | Listings & prices | Netherlands | Weekly |
| Forums (10+) | Community sentiment | FR, UK, DE | Monthly |

## Tech Stack

- **Python 3.10+** — Core language
- **SQLite / SQLAlchemy** — Database
- **Streamlit** — Dashboard
- **Plotly** — Charts
- **httpx + BeautifulSoup4** — Data collection

## Quick Start

```bash
# Clone and setup
git clone https://github.com/YOUR_USER/carcollector-predictor.git
cd carcollector-predictor
pip install -r requirements.txt

# Initialize database with seed data
python scripts/seed_database.py

# Run data collection
python scripts/run_collection.py

# Calculate scores
python scripts/run_analysis.py

# Launch dashboard
streamlit run dashboard/app.py
```

## Project Structure

```
├── CLAUDE.md              # Claude Code project memory
├── config.py              # Configuration & constants
├── database/              # SQLAlchemy models & DB init
├── collectors/            # Data collectors (DVLA, RDW, scrapers, forums)
├── analysis/              # Scoring engine
├── dashboard/             # Streamlit web interface
├── data/                  # Seed data (JSON)
├── scripts/               # CLI entry points
├── tests/                 # pytest test suite
├── tasks/                 # Development tracking
└── docs/                  # Full technical specification
```

## Scoring Formula

```
collector_potential = (
    rarefaction_score     × 0.30    # How fast is it disappearing?
  + desirability_score    × 0.25    # Is it special? (engine, driving experience)
  + reliability_score     × 0.20    # Is it reliable? (not a lemon)
  + market_momentum_score × 0.15    # Are prices rising, listings dropping?
  + forum_buzz_score      × 0.10    # Are enthusiasts talking about it?
)
```

## Contributing

This project is built with [Claude Code](https://claude.ai). See `CLAUDE.md` for development conventions and `docs/SPEC.md` for the complete technical specification.

## License

MIT
