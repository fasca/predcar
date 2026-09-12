# Prochaine session — ce qu'il reste à faire

Fichier de reprise, lu **en premier** par Claude Code à chaque démarrage (voir `CLAUDE.md`).
Il ne décrit que les actions **en attente** ; le plan complet est dans `tasks/todo.md`, les
leçons dans `tasks/lessons.md`. Cocher et mettre à jour à chaque étape franchie ; supprimer
une section quand elle est terminée.

## 1. Run réel après les PR #7 et #8 (machine connectée : WSL2 ou VM)

Pourquoi : les corrections de la PR #7 (règles de mapping, `year_manufacture`, Δt réel, SORN
génération, anomalies) et la PR #8 (`cohorts.parquet`, site) n'ont **jamais tourné sur les
vraies données**. Le seul export réel est `reports/2026-09-08/`, antérieur à ces PR.

Si tu es Claude Code et que `curl -sS -o /dev/null -w "%{http_code}" https://www.gov.uk/`
répond `200`, exécute ces commandes toi-même, dans l'ordre, et arrête-toi à la première
erreur (une erreur de schéma ou de couverture est une information, pas un obstacle à
contourner) :

```bash
git checkout main && git pull
uv sync                                   # nouvelles dépendances : jinja2, markdown
ls data/raw/uk_dft data/raw/nl_rdw        # les payloads du 2026-09-08 doivent être là ;
                                          # sinon : make fetch-uk && make fetch-nl
make ingest-uk && make ingest-nl && make normalize && make score && make export
make site                                 # après fusion de la PR #8 ; ouvrir site/dist/index.html
make test
git add data/raw reports
git commit -m "run réel après PR #7 et #8"
git push
```

- [ ] Pipeline relancé sans erreur (`reports/<date>/manifest.json` → `stages` tous `ok`)
- [ ] `data/raw/**/MANIFEST.json` et `reports/<date>/` committés et poussés
- [ ] `site/dist/index.html` ouvert : classement, une page modèle, méthodologie, graphiques

## 2. Analyse du nouvel export (n'importe quel environnement, réseau inutile)

Comparer `reports/<nouvelle date>/gold/` à `reports/2026-09-08/gold/` :

- [ ] Honda Civic Type R EP3 : parc GB en centaines/milliers (était 1 exemplaire)
- [ ] Nissan Skyline R33 / R34 : générations séparées par année de fabrication
- [ ] Mitsubishi Lancer Evo : une ligne par génération (I_IV … X), pas selon l'année GB
- [ ] Renault Clio 16V MK1 : parc de quelques centaines, plus 12 M de `DYNAMIQUE 16V`
- [ ] Ford Fiesta ST / Focus ST : `ST-LINE` exclu
- [ ] `gold/anomalies.csv` : nombre de lignes très inférieur à 1 123 (montées en charge
      exclues) ; lire celles qui restent
- [ ] `silver/coverage.csv` : GB ≥ 99 %, NL ≥ 98 % hors `MODEL MISSING`
- [ ] Les 5 modèles témoins (BMW M3 E46, Peugeot 205 GTI, Honda S2000, Renault Clio Williams,
      Audi RS2) ont les 4 composantes et un score publié
- [ ] Corriger ce qui cloche (`mapping/models.csv`, `predcar/metrics.py`), ajouter un test
      sur les libellés réels, entrée `CHANGELOG.md`, leçon dans `tasks/lessons.md`, PR
- [ ] Ensuite : snapshot tests des 5 témoins à partir des valeurs réelles validées

## 3. GitHub Pages (une fois, par l'utilisateur)

- [ ] Settings → Pages → Source : **GitHub Actions**
- [ ] Lancer le workflow « Site » (*Actions → Site → Run workflow*) ou attendre le prochain
      push sur `main` ; vérifier l'URL publiée et que les graphiques Plotly s'affichent
- [ ] Si le job `build` échoue à `make fetch-uk` : les URLs DfT ont changé de page ou de nom,
      voir `docs/sources/dft_uk.md` et `config/sources.yaml`

## 4. Ensuite

- Conserver l'historique RDW côté CI (voir `tasks/todo.md`, étape 5)
- Phase 2 : KBA (DE) — Source-First, commencer par un échantillon dans `data/raw/`
