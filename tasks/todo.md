# CarCollector Predictor — Plan de Développement

## Phase 1 — Fondations
- [ ] Créer la structure de dossiers complète
- [ ] Écrire `config.py` (URLs, chemins, constantes scoring)
- [ ] Écrire `database/models.py` (SQLAlchemy, 6 tables)
- [ ] Écrire `database/init_db.py` (création base)
- [ ] Écrire `data/seed_vehicles.json` (~60 modèles)
- [ ] Écrire `data/known_lemons.json`
- [ ] Écrire `data/forums_sources.json`
- [ ] Écrire `scripts/seed_database.py`
- [ ] Tests: `tests/test_database.py`

## Phase 2 — Collecteurs
- [ ] `collectors/base_collector.py` (classe abstraite + rate limiter)
- [ ] `collectors/dvla_uk.py` (download CSV + parse VEH0120/VEH0124)
- [ ] `collectors/rdw_nl.py` (API Socrata, pagination)
- [ ] `collectors/scraper_autoscout.py` (prix/volume pan-EU)
- [ ] `collectors/scraper_mobile_de.py` (prix/volume DE/AT)
- [ ] `collectors/scraper_leboncoin.py` (prix/volume FR)
- [ ] `collectors/scraper_ebay_uk.py` (prix/volume UK)
- [ ] `collectors/forum_scraper.py` (sentiment multi-forums)
- [ ] Tests: `tests/test_collectors.py`

## Phase 3 — Moteur d'Analyse
- [ ] `analysis/attrition.py` (taux raréfaction)
- [ ] `analysis/reliability.py` (score fiabilité)
- [ ] `analysis/desirability.py` (score désirabilité)
- [ ] `analysis/market_signals.py` (tendance prix/volume)
- [ ] `analysis/forum_buzz.py` (score sentiment forums)
- [ ] `analysis/scorer.py` (score composite final)
- [ ] Tests: `tests/test_analysis.py`

## Phase 4 — Dashboard Streamlit
- [ ] `dashboard/app.py` (main, navigation)
- [ ] `dashboard/pages/overview.py` (classement top modèles)
- [ ] `dashboard/pages/model_detail.py` (fiche modèle + graphiques)
- [ ] `dashboard/pages/trends.py` (courbes comparatives)
- [ ] `dashboard/pages/alerts.py` (modèles en mouvement)
- [ ] Filtres: marque, époque, motorisation, budget, score minimum

## Phase 5 — Automatisation
- [ ] Tâches cron pour collecte automatique
- [ ] Notifications (Telegram/email) pour alertes
- [ ] Sources supplémentaires (KBA DE, ASTRA CH)
- [ ] Export rapports PDF

---

## Review Notes
_Section à remplir après chaque phase complétée._
