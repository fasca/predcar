Run the full analysis pipeline for CarCollector Predictor. Calculate all sub-scores (rarefaction, reliability, desirability, market momentum, forum buzz) then compute the composite collector_potential score for all vehicles in the database.

```bash
python scripts/run_analysis.py
```

After analysis, show the top 20 vehicles by collector_potential score with their sub-scores breakdown.
