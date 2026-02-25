# Prompt d'initialisation — CarCollector Predictor

## Contexte

Tu vas construire **CarCollector Predictor**, un outil Python qui prédit quels véhicules d'occasion vont devenir des voitures de collection (horizon 5-10 ans). Le principe : croiser raréfaction du parc, fiabilité mécanique, buzz forums, et signaux marché pour attribuer un score de potentiel collector par modèle.

Lis d'abord `CLAUDE.md` (mémoire projet) et `docs/SPEC.md` (spec technique complète) avant de commencer.

## Stack

Python 3.10+ | SQLite (SQLAlchemy) | Streamlit | Plotly | httpx + BeautifulSoup4

## Sources de données (MVP)

1. **UK DVLA** — CSV GOV.UK (VEH0120/VEH0124), trimestriel, par marque/modèle
2. **NL RDW** — API REST `opendata.rdw.nl`, tous véhicules NL depuis 1952, no auth
3. **5 Marketplaces** — AutoScout24, mobile.de, LeBonCoin, eBay Motors UK, Marktplaats.nl
4. **Forums** — Forum-Auto.com, PistonHeads.com, Motor-Talk.de + forums marque

## Base de données — 6 tables

1. **vehicles** — Référentiel modèles (brand, model, variant, engine, production years, iconic_factor)
2. **park_snapshots** — Comptages en circulation par modèle/source/date
3. **market_signals** — Prix et volume annonces par source/date
4. **forum_signals** — Activité threads, ratio WTB/FS, keywords sentiment
5. **reliability_data** — Taux CT, is_lemon, known_issues
6. **collector_scores** — Scores calculés (5 sous-scores + composite)

## Scoring

```
collector_potential = (
    rarefaction_score     * 0.30 +
    desirability_score    * 0.25 +
    reliability_score     * 0.20 +
    market_momentum_score * 0.15 +
    forum_buzz_score      * 0.10
)
```

## Commande de démarrage

Commence par:
1. Lire CLAUDE.md et docs/SPEC.md
2. Lire tasks/todo.md pour le plan
3. Créer `config.py`, `requirements.txt`
4. Créer `database/models.py` (SQLAlchemy, 6 tables)
5. Créer `database/init_db.py`
6. Créer `data/seed_vehicles.json` (~60 modèles)
7. Créer `data/known_lemons.json`
8. Créer `data/forum_sources.json`
9. Créer `scripts/seed_database.py`
10. Tests: `tests/test_database.py`

Puis on attaque les collecteurs un par un.

## Règles

- Plan mode pour toute tâche de 3+ étapes
- Vérifier que ça marche avant de dire que c'est fini
- Update `tasks/lessons.md` après chaque correction
- Code propre: type hints, docstrings, logging, gestion erreurs
- Rate limiting sur TOUT le scraping (2-5s delays)
- Jamais de données personnelles
