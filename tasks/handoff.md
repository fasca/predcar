# Passation — état au 2026-09-12

Document de reprise pour une nouvelle session. À lire après `tasks/todo.md` et
`tasks/lessons.md`. Il sera périmé dès que les PR ci-dessous seront fusionnées : le supprimer
à ce moment-là plutôt que de le laisser mentir.

## 1. Ce qu'il faut faire des PR ouvertes

| PR | Fusionner ? | Pourquoi |
|---|---|---|
| **#9** Re-run réel post-#7 + précédence des règles de libellé | **oui, en premier** | corrige un bug bloquant de `normalize` et produit le bundle de référence `reports/2026-09-12/` dont tout le reste dépend |
| **#10** Snapshot tests des 5 témoins + filet anti-régression | **oui, après #9** | ses bornes sont calées sur `reports/2026-09-12/` |
| **#11** Cron mensuel RDW + archives compressées | **oui** | indépendante ; urgent car le RDW n'a pas d'historique amont |
| **#8** Site statique Jinja2 (étape 5) | **non, pas en l'état** | voir §2 |
| **#12** Site statique Astro (étape 5) | **non, pas en l'état** | doublon de #8, voir §2 |

**Conflits : un seul type, trivial.** `#11` et `#12` ne heurtent que `CHANGELOG.md` (deux entrées
ajoutées en tête) ; `#8` heurte `CHANGELOG.md`, `docs/ARCHITECTURE.md`, `predcar/paths.py` et
`tasks/todo.md`. **Aucun conflit de code.** Résolution : garder les deux entrées du changelog.

## 2. Tâche n°1 — fusionner le meilleur de #8 et #12

Les deux PR implémentent l'étape 5 avec des stacks différentes. Elles ne partagent aucun
fichier source (`predcar/site.py` + `site/templates/` contre `site/src/`), seulement de la
documentation — donc les fusionner toutes les deux donnerait **deux générateurs de site**.

**Décision arrêtée avec l'utilisateur : prendre #8 comme base et y porter ce qui vaut de #12.**

### Ce que #8 fait mieux — à garder tel quel
- **Rétention par cohorte réelle** (`metrics.cohort_retention`, `data/gold/cohorts.parquet`) :
  rétention par millésime. #12 se contentait du stock normalisé à la première année observée,
  ce qui n'est pas une courbe de survie par cohorte.
- **Filtres segment / décennie / pays** et plusieurs tris (« se raréfient le plus vite / le
  moins vite », « parc le plus faible »). #12 n'avait ni décennie ni pays.
- **Pages des cibles non publiées, avec la raison** du non-calcul — c'est ce que demande
  SPEC §6 (« montrer le *pourquoi* »).
- Méthodologie rendue depuis `docs/methodology.md` **précédée des paramètres réels de
  `config/score.yaml`** : #12 ne montrait pas les paramètres.
- Python seul, pas de chaîne d'outils Node.

### Ce qu'il faut porter depuis #12
1. **Construire depuis le dernier `reports/<date>/gold/` committé, pas depuis `data/gold/`.**
   C'est le point important. Le workflow de #8 (`site.yml`) refait `fetch` + pipeline complet
   **à chaque push sur `main`** : ~190 Mo téléchargés, 20+ min, et le déploiement échoue si une
   source est momentanément indisponible ou si la gate de couverture casse. Conséquences du
   changement : un déploiement prend quelques secondes, ne demande ni réseau ni `data/`, et ce
   que le site affiche est toujours reproductible depuis le dépôt.
   Voir `site/src/lib/gold.ts` de la branche `claude/site-astro` pour la logique « dernier
   bundle contenant `gold/ranking.csv` ».
2. **Séparer déploiement et rafraîchissement en deux workflows.** Déployer et régénérer les
   données sont deux événements de fréquences différentes :
   - `pages.yml` — build + déploiement sur push touchant `site/`, `reports/` ou
     `docs/methodology.md`, plus `workflow_dispatch` ;
   - `refresh.yml` — cron trimestriel (20 janv./avr./juil./oct.) qui rejoue le pipeline,
     **relance `pytest` sur le nouveau bundle avant de le committer** (un relabellisage DfT ou
     une dérive de couverture doit échouer là, pas en production), puis pousse — ce qui
     déclenche le déploiement.
   Les deux existent sur `claude/site-astro`, à adapter.
3. **La date du bundle comme date de rafraîchissement affichée** (SPEC §6 : « sources citées
   avec date de refresh »), plutôt que la date de génération du site.
4. **Trois règles d'honnêteté des graphiques** — elles ne sont pas cosmétiques, le site prétend
   mesurer un déclin :
   - l'axe des stocks **démarre à zéro** (un axe tronqué exagère exactement ce qu'on mesure) ;
   - une série à **un seul point** (le RDW aujourd'hui) est **exclue** de la courbe de
     rétention, jamais normalisée à 100 — « 100 % » se lirait « rien n'a été perdu » ; nommer
     les séries écartées et la raison ;
   - une composante absente est **écrite comme absente** (« exclue, poids renormalisés »),
     jamais dessinée à 0.
5. Préciser sur la page modèle que la composante `sorn_ratio` **est** le ratio brut repris tel
   quel (déjà dans 0–1 et correctement orientée), sinon la carte « part SORN » et la barre de
   composante affichent le même nombre et donnent l'impression de deux mesures différentes.

### Points d'attention
- **#8 est antérieure à la PR #7** : ses chiffres et ses captures viennent de
  `reports/2026-09-08/`, le bundle buggé (Civic Type R EP3 à 2 exemplaires). La rebaser sur
  `main` à jour et **re-vérifier le rendu sur `reports/2026-09-12/`**.
- #8 charge Plotly depuis un CDN, avec un message de repli. À garder (l'interactivité a de la
  valeur) en connaissance de cause : c'est une dépendance réseau côté visiteur.
- Une fois la décision prise, **fermer #12** avec un commentaire expliquant ce qui en a été
  repris, et supprimer `site/src/`, `site/package*.json`, `site/astro.config.mjs` s'ils ont
  atterri quelque part.

## 3. Suites immédiates après fusion

1. **Activer GitHub Pages** : *Settings → Pages → Source : GitHub Actions*. Sans cet opt-in
   unique, `actions/deploy-pages` échoue. (Les deux PR le signalent.)
2. **Compléter le workflow de rafraîchissement** avec `uv run predcar compress nl` et
   `data/raw/nl_rdw/*/*.json.gz` dans son `git add` — sinon il committera un manifest RDW sans
   son payload, c'est-à-dire l'empreinte de données qu'on n'a plus. Dépend de #11.
3. **Sauver le snapshot RDW de septembre 2026** : il existe sur la machine de la session du
   2026-09-12 mais n'est committé dans aucune PR (son `MANIFEST.json` est dans #9, la règle
   `.gitignore` dans #11). Après fusion des deux : `make fetch-nl` (si le mois est encore
   septembre) puis `make compress-nl` et commit. Sinon le premier mois archivé sera octobre.
4. Supprimer ce fichier.

## 4. Phase 2 — prochaine étape de fond

`tasks/todo.md` : KBA (DE), immatriculations FR (SDES), STATS19, Google Trends, YouTube.

Commencer par **KBA en Source-First** (`CLAUDE.md` § Workflow Rules), dans cet ordre et pas un
autre : inventorier les URLs réelles des XLSX FZ 10 / FZ 17 2010–2026 par requête HTTP,
télécharger un échantillon dans `data/raw/`, documenter le schéma **observé** de chaque
millésime dans `docs/sources/kba_de.md` (les en-têtes multi-lignes et les libellés changent
d'une année à l'autre), écrire les tests de schéma, **puis** le parseur. La leçon du 2026-09-09
(« aucun schéma n'est présumé ») a coûté une réécriture complète du parseur VEH0124.

## 5. Notes d'environnement

La session du 2026-09-12 tournait sur une machine à **1,9 Go de RAM, 1 vCPU, 20 Go de disque** :
`ingest uk` a pris 21 min et `validate` 26 min, avec 8 Go de swap ajoutés à la main, parce que
tout le pipeline est *eager* (`pl.read_csv(infer_schema_length=0)` puis `unpivot`, puis
`pl.concat([pl.read_parquet(p) for p in files])` dans `normalize.py`). Sur une machine à 64 Go
ce n'est plus un sujet et **il n'y a rien à optimiser pour l'instant** — mais le point reste à
surveiller si le volume augmente en phase 2 (les XLSX KBA s'ajoutent au silver), et la CI
GitHub tourne sur des runners à 16 Go.

Vérifier l'accès réseau aux sources en début de session plutôt que de s'en remettre à la doc
(leçon du 2026-09-09) :

```bash
for u in https://www.gov.uk https://opendata.rdw.nl https://www.kba.de https://www.data.gouv.fr; do
  printf "%s -> " "$u"; curl -sS -m 10 -o /dev/null -w "%{http_code}\n" "$u"
done
```
