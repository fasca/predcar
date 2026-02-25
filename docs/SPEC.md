# 🚗 CarCollector Predictor — Spécification Technique Complète

## Vision

Outil d'analyse prédictive identifiant les véhicules susceptibles de devenir collectors dans les 5-10 ans. Croise raréfaction, fiabilité, sentiment forums, et signaux marché pour un **score de potentiel collector** par modèle.

---

## 1. Architecture

```
┌─────────────────── DASHBOARD (Streamlit) ───────────────────┐
│  Classement futurs collectors | Courbes raréfaction          │
│  Alertes mouvements | Filtres (marque, époque, budget)       │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                  MOTEUR D'ANALYSE (Python)                    │
│  Attrition | Fiabilité | Désirabilité | Marché | Forums      │
│  → Score composite "collector_potential" (0-100)              │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│               BASE DE DONNÉES (SQLite/SQLAlchemy)            │
│  vehicles | park_snapshots | market_signals                  │
│  reliability_data | forum_signals | collector_scores          │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    COLLECTEURS DE DONNÉES                     │
│                                                              │
│  ┌────────┐ ┌───────┐ ┌────────────┐ ┌──────────────────┐   │
│  │UK DVLA │ │NL RDW │ │ 5 Market-  │ │ Forums (FR/UK/DE)│   │
│  │(CSV)   │ │(API)  │ │ places     │ │ Sentiment        │   │
│  └────────┘ └───────┘ └────────────┘ └──────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Sources de Données

### 2.1 UK — DVLA (GOV.UK)

- **Type:** CSV/ODS trimestriels
- **URL:** https://www.gov.uk/government/collections/vehicles-statistics
- **Fichiers:** VEH0120 (par marque/modèle/statut), VEH0124 (+ année fabrication)
- **Granularité:** marque → modèle générique → variante
- **Données:** count taxed (en circulation), count SORN (hors route), historique depuis 2014
- **Licence:** Open Government Licence v3.0
- **Alternative:** HowManyLeft.co.uk (même données, format web)

### 2.2 Pays-Bas — RDW (API REST)

- **Endpoint:** `https://opendata.rdw.nl/resource/m9d7-ebf2.json`
- **Champs:** merk, handelsbenaming, datum_eerste_toelating, catalogusprijs, brandstof_omschrijving
- **Taille:** ~15M véhicules depuis 1952
- **Limite:** 1000 lignes/requête, paginer avec $offset
- **Auth:** Aucune clé nécessaire
- **Licence:** Domaine public
- **Compléments:** carburant/émissions (8ys7-d773), historique APK

### 2.3 Marketplaces (5 sources)

| Source | Couverture | URL Pattern | Anti-bot |
|--------|-----------|-------------|----------|
| AutoScout24 | Pan-EU (FR,DE,IT,ES,NL,BE,AT,CH) | `/lst/{marque}/{modele}` | Élevé |
| mobile.de | DE, AT | `/fahrzeuge/search.html?ms=...` | Modéré |
| LeBonCoin | FR | `/recherche?category=2&text=...` | Modéré |
| eBay Motors UK | UK | `/sch/Cars/9801/i.html?_nkw=...` | Faible |
| Marktplaats.nl | NL | `/q/{marque}+{modele}/` | Faible |

**Données extraites par source:** listing_count, price_min/max/median/avg, avg_mileage_km, avg_year
**Fréquence:** Hebdomadaire à mensuelle
**Stack:** httpx + BeautifulSoup4, playwright si JS nécessaire

### 2.4 Forums — Sentiment Communautaire

**Rôle:** Leading indicator — le buzz forums précède de 1-2 ans la montée des prix.

**Forums généralistes:**
- Forum-Auto.com (FR), PistonHeads.com (UK), Motor-Talk.de (DE)

**Forums marque (exemples):**
- 205GTIDrivers.com, GolfGTIforum.co.uk, E46Fanatics.com, ClubCivic.com, MR2oc.com

**Données extraites:**
- Threads actifs récents (30/90/365 jours)
- Ratio "cherche/WTB" vs "vends/FS" (demande vs offre)
- Keywords: "collection", "collector", "investissement", "cote", "rare", "hausse"
- Volume de membres actifs sur le sous-forum

**Fréquence:** Mensuelle
**Important:** Agrégation statistique uniquement, pas de stockage de contenu individuel

---

## 3. Modèle de Données

### vehicles
```sql
CREATE TABLE vehicles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand TEXT NOT NULL,
    model TEXT NOT NULL,
    variant TEXT,
    generation TEXT,
    production_start INTEGER,
    production_end INTEGER,
    engine_type TEXT,            -- petrol, diesel, petrol_turbo, etc.
    engine_code TEXT,            -- ex: "OM642", "K20A", "EJ207"
    engine_displacement_cc INTEGER,
    horsepower INTEGER,
    transmission TEXT,           -- manual, automatic
    drive_type TEXT,             -- FWD, RWD, AWD
    body_type TEXT,              -- hatchback, sedan, coupe, van, suv
    estimated_total_production INTEGER,
    iconic_factor INTEGER DEFAULT 0,  -- 0-10 score manuel
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(brand, model, variant)
);
```

### park_snapshots
```sql
CREATE TABLE park_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),
    source TEXT NOT NULL,         -- dvla_uk, rdw_nl
    snapshot_date DATE NOT NULL,
    count_registered INTEGER,
    count_sorn INTEGER,          -- UK only
    count_total INTEGER,
    country TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(vehicle_id, source, snapshot_date)
);
```

### market_signals
```sql
CREATE TABLE market_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),
    source TEXT NOT NULL,         -- autoscout24, mobile_de, leboncoin, ebay_uk, marktplaats
    snapshot_date DATE NOT NULL,
    listing_count INTEGER,
    price_min REAL,
    price_max REAL,
    price_median REAL,
    price_avg REAL,
    avg_mileage_km INTEGER,
    avg_year INTEGER,
    country TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(vehicle_id, source, snapshot_date, country)
);
```

### forum_signals
```sql
CREATE TABLE forum_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),
    source TEXT NOT NULL,         -- forum-auto, pistonheads, motor-talk, etc.
    snapshot_date DATE NOT NULL,
    active_threads_30d INTEGER,
    active_threads_90d INTEGER,
    active_threads_365d INTEGER,
    wtb_count INTEGER,           -- "cherche" / "WTB" posts
    fs_count INTEGER,            -- "vends" / "FS" posts
    sentiment_keywords TEXT,     -- JSON dict of keyword frequencies
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(vehicle_id, source, snapshot_date)
);
```

### reliability_data
```sql
CREATE TABLE reliability_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),
    source TEXT NOT NULL,
    year INTEGER,
    pass_rate REAL,
    common_failures TEXT,        -- JSON
    known_issues TEXT,
    is_lemon INTEGER DEFAULT 0,
    lemon_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(vehicle_id, source, year)
);
```

### collector_scores
```sql
CREATE TABLE collector_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),
    calculated_date DATE NOT NULL,
    rarefaction_score REAL,       -- 0-100
    reliability_score REAL,       -- 0-100
    desirability_score REAL,      -- 0-100
    market_momentum_score REAL,   -- 0-100
    forum_buzz_score REAL,        -- 0-100
    exclusivity_score REAL,       -- 0-100
    collector_potential REAL,     -- score final pondéré 0-100
    confidence_level TEXT,        -- high, medium, low
    reasoning TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(vehicle_id, calculated_date)
);
```

---

## 4. Algorithme de Scoring

### Score composite
```
collector_potential = (
    rarefaction_score     * 0.30 +
    desirability_score    * 0.25 +
    reliability_score     * 0.20 +
    market_momentum_score * 0.15 +
    forum_buzz_score      * 0.10
)
```

### rarefaction_score (taux d'attrition)
- attrition_rate = (count_t0 - count_t1) / count_t0 * 100
- 5-8%/an = zone idéale (raréfaction active) → score élevé
- <2%/an = déjà en collection → score moyen
- >10%/an = disparition rapide, peut-être trop tard → score modéré
- Bonus si count_total < 500 (UK) ou < 200 (NL)

### desirability_score
- +20: moteur atmosphérique haute performance
- +15: boîte manuelle
- +15: propulsion ou AWD
- +10: design iconique reconnaissable
- +10: présence jeux vidéo (GT, NFS, Forza)
- +10: dernière génération d'une techno (dernier V8 atmo, etc.)
- +10: version sportive d'un modèle populaire
- -20: boîte automatique générique
- -15: diesel non sportif
- -10: pas d'identité forte

### reliability_score
- Base: taux réussite CT/MOT
- is_lemon = 1 → score divisé par 2
- Bonus: moteur réputé fiable (liste curated)
- Bonus: pièces encore disponibles

### market_momentum_score
- Prix ↑ + Volume ↓ = SIGNAL FORT (raréfaction active)
- Prix stable + Volume ↓ = pré-décollage
- Prix ↑ + Volume stable = demande croissante
- Prix ↓ + Volume ↑ = pas encore le moment

### forum_buzz_score
- Threads actifs en hausse → buzz positif
- Ratio WTB/FS > 2 → demande forte
- Keywords collector/rare en hausse → signal avancé
- Pondéré par la taille du forum (normalisation)

---

## 5. Structure Projet

```
carcollector-predictor/
├── CLAUDE.md                     # Mémoire projet Claude Code
├── README.md
├── requirements.txt
├── config.py
├── .claude/
│   └── commands/
│       ├── collect.md            # /collect
│       ├── analyze.md            # /analyze
│       └── techdebt.md           # /techdebt
├── tasks/
│   ├── todo.md                   # Plan et suivi
│   └── lessons.md                # Leçons apprises
├── docs/
│   └── SPEC.md                   # Ce fichier
├── database/
│   ├── __init__.py
│   ├── models.py
│   └── init_db.py
├── collectors/
│   ├── __init__.py
│   ├── base_collector.py
│   ├── dvla_uk.py
│   ├── rdw_nl.py
│   ├── scraper_autoscout.py
│   ├── scraper_mobile_de.py
│   ├── scraper_leboncoin.py
│   ├── scraper_ebay_uk.py
│   ├── scraper_marktplaats.py
│   ├── forum_scraper.py
│   └── utils.py
├── analysis/
│   ├── __init__.py
│   ├── attrition.py
│   ├── reliability.py
│   ├── desirability.py
│   ├── market_signals.py
│   ├── forum_buzz.py
│   └── scorer.py
├── dashboard/
│   ├── app.py
│   ├── pages/
│   │   ├── overview.py
│   │   ├── model_detail.py
│   │   ├── trends.py
│   │   └── alerts.py
│   └── components/
│       ├── charts.py
│       └── filters.py
├── data/
│   ├── seed_vehicles.json
│   ├── known_lemons.json
│   ├── forum_sources.json
│   └── iconic_ratings.json
├── scripts/
│   ├── run_collection.py
│   ├── run_analysis.py
│   └── seed_database.py
└── tests/
    ├── test_database.py
    ├── test_collectors.py
    ├── test_analysis.py
    └── test_scoring.py
```

---

## 6. Dépendances

```
python>=3.10
sqlalchemy>=2.0
requests>=2.31
httpx>=0.25
beautifulsoup4>=4.12
lxml>=4.9
playwright>=1.40
pandas>=2.1
numpy>=1.25
streamlit>=1.29
plotly>=5.18
python-dotenv>=1.0
tenacity>=8.2
fake-useragent>=1.4
tqdm>=4.66
schedule>=1.2
pytest>=7.4
```

---

## 7. Seed Vehicles (~60 modèles)

**FR:** 205 GTI 1.6/1.9, 306 S16/GTI-6, Clio Williams, Clio RS (I/II/III/IV), Mégane RS (I/II/III/IV), Saxo VTS, 106 Rallye/S16, Peugeot RCZ R

**DE:** BMW E30/E36/E46 M3, BMW Z3 M Coupé, Golf 2 GTI 16S, Golf R32 (IV/V), Mercedes 190E 2.5-16, Porsche 996/997, Boxster 986, BMW E39 540i, Mercedes W124 E500, BMW E60 M5 V10

**JP:** Supra MK4, S2000, MX-5 NA/NB, Integra Type R DC2/DC5, Lancer Evo VI-IX, Impreza STI (GC8/GDB), MR2 SW20, Celica GT-Four, Nissan Skyline R33/R34, Nissan 350Z

**IT:** Alfa 147/156 GTA, Fiat Coupé Turbo, Fiat Barchetta, Alfa GTV/Spider 916

**UK/SE:** Saab 9-3 Viggen, Volvo 850 T5-R

**Vans:** Mercedes Viano W639, VW T4/T5 California, Mercedes G W463

---

## 8. Known Lemons

| Moteur | Problème | Modèles affectés |
|--------|----------|------------------|
| PSA 1.2 PureTech (EB2) | Chaîne distribution, conso huile | 208, 308 II, C3 III, DS3 |
| Renault 1.2 TCe (H5F) | Surconsommation huile | Captur, Clio IV |
| BMW N47 | Chaîne côté volant moteur | 118d/120d E87, 318d/320d E90 |
| Renault 1.5 dCi (certaines) | Vanne EGR, turbo | Mégane II, Scénic II |
| Ford 1.0 EcoBoost (gen1) | Joint culasse, refroidissement | Focus III, Fiesta VII |
| Fiat 1.3 MultiJet (certaines) | Vanne EGR | Punto, 500L |
