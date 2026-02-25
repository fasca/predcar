Run all data collectors for CarCollector Predictor. Execute each collector in sequence: DVLA UK, RDW NL, then marketplace scrapers (AutoScout24, mobile.de, LeBonCoin, eBay UK), then forum scrapers. Log progress and errors. If a collector fails, continue with the next one and report failures at the end.

```bash
python scripts/run_collection.py --all
```

After collection, show a summary: how many new snapshots were added, how many errors occurred, which sources succeeded/failed.
