# Méthodologie — indicateurs et score v1

Cette page est la source de la page « Méthodologie » du site (SPEC §6). Chaque formule,
chaque source, chaque limite. Paramètres dans `config/score.yaml`, jamais en dur.

## 1. Données d'entrée

| Série | Pays | Granularité | Niveau | Ce qu'elle apporte |
|---|---|---|---|---|
| VEH0120 (DfT) | GB | trimestrielle, 1994 → | modèle générique (`model_gen`) | stock long historique, **SORN** |
| VEH0124 (DfT) | GB | annuelle, 2014 → | génération (via année de 1re immatriculation) | stock par génération, cohortes (Licensed et SORN distingués ; le ratio SORN publié reste celui de VEH0120) |
| VEH0160 (DfT) | GB | trimestrielle, 2001 → | modèle générique | immatriculations neuves (ventes) |
| RDW `m9d7-ebf2` | NL | snapshot mensuel, depuis notre 1er snapshot | génération (via année de 1re admission) | stock par génération |

VEH0120 et VEH0124 décrivent le même parc : ils ne sont **jamais additionnés**. Pour chaque
(génération cible, pays), le stock et l'attrition viennent de la série de niveau génération
quand elle existe (VEH0124, RDW), sinon de la série de niveau modèle générique (VEH0120,
sommée sur les générations) — **uniquement si la génération cible est la seule de son modèle
générique**, sinon tout le parc du modèle serait crédité à chaque génération et la cible
reste sans donnée. Le niveau utilisé est exposé (`level`).

Les séries infra-annuelles sont ramenées à une valeur par an : **dernière période de
l'année**.

## 2. Indicateurs

Par (marque, modèle générique, génération, pays) — deux marques peuvent partager un libellé de modèle (SPIDER Alfa Romeo et Renault) et ne sont jamais fusionnées :

- **Stock(t)** : véhicules en circulation = tous statuts sauf `sorn`.
- **Ventes cumulées** : immatriculations neuves VEH0160 du modèle générique sur les années de
  production de la génération (`target_models.csv`). Indisponible avant 2001 et hors GB.
- **Survival(t)** = Stock(t) / max(ventes cumulées, stock maximal observé).
- **Attrition annuelle** a(t) = −(ln Stock(t) − ln Stock(t−1)) / Δt, puis moyenne glissante
  sur `attrition.smoothing_years` (3) valeurs ; définie à partir de la 4e année observée.
  Indisponible si moins de `attrition.min_history_years` (3) valeurs lissées.
- **Pairs** : modèles du même pays, même segment et même tranche d'âge
  (`peers.age_bucket_years` = 5 ans ; âge = année − milieu de production de la génération),
  observations poolées sur les années. Il faut au moins `peers.min_peers` (3) **modèles
  distincts** ; un modèle seul dans son segment n'a pas de pairs.
- **Attrition relative** = a(t) − médiane des pairs. Négatif = disparaît moins vite que ses
  pairs = déjà conservé.
- **Point d'inflexion** : première année de la série finale d'années **consécutives** où
  l'attrition lissée est sous la médiane des pairs au même âge ; une année manquante dans la
  série réinitialise la run. Null si la dernière année n'est pas sous la médiane (pas de
  « collectorisation » en cours).
- **Ratio SORN** (GB uniquement) = SORN / (SORN + Licensed) à la dernière période de VEH0120,
  niveau modèle générique.
- **Rareté absolue** : stock courant ; étiquette `<20`, `<100`, `<500`, `>=500`
  (`rarity.thresholds`).

## 3. Agrégat Europe

Une ligne `EU` par génération cible : stock sommé sur les pays ; attrition, attrition
relative et survie pondérées par le stock des pays où elles existent ; point d'inflexion =
le plus récent des pays ; ratio SORN = valeur GB. Une valeur absente partout reste absente
(null, jamais NaN ni 0).

## 4. Composantes du score (0–1, « plus haut = plus collector »)

| Composante | Calcul | Absente quand |
|---|---|---|
| `rarity` | min-max de −ln(stock) sur la population scorée : 1 = stock le plus faible | jamais (si un stock existe) |
| `conservation` | rang de −attrition_relative sur la population, ramené à 0–1 | pas d'historique ou pas de pairs |
| `sorn_ratio` | ratio SORN tel quel | hors GB |
| `recent_inflection_point` | 1 si (dernière année − année d'inflexion) < `inflection.recent_years` (5), sinon 0 | pas d'historique ou pas de pairs |

## 5. Score composite

```
score = Σ w_i · c_i / Σ w_i   sur les composantes disponibles
w = rarity 0.35, conservation 0.25, sorn_ratio 0.20, recent_inflection_point 0.20
```

Une composante manquante est **exclue et les poids restants renormalisés** ; jamais imputée
à 0. Le score n'est publié que si Σ w_i disponibles ≥ `min_weight_coverage` (0.60). Chaque
ligne expose `components_available`, `weight_coverage`, et chaque composante brute et
normalisée : le site montre le *pourquoi*.

Conséquence concrète : tant que NL n'a qu'un snapshot, un modèle absent de GB n'a que
`rarity` (0.35) et n'est pas publié. Les modèles GB sans pairs (segment trop peu peuplé)
ont `rarity` + `sorn_ratio` = 0.55 et ne sont pas publiés non plus.

## 6. Limites connues

- Les courbes de survie sont des **courbes de rétention agrégées**, pas du Kaplan-Meier :
  pas d'événements individuels, cohortes ouvertes aux imports et réimmatriculations. Une
  hausse de stock d'une cohorte est journalisée comme anomalie, pas rejetée.
- VEH0124 commence en 2014 : au niveau génération, l'historique GB est ≤ 12 ans.
- Le RDW n'a pas d'historique : attrition et inflexion NL après 3 ans de snapshots.
- `rarity` et `conservation` sont relatives à la population cible : ajouter des modèles
  déplace les valeurs.
- Extrapolation Weibull à 5/10 ans : phase 3.

## 7. Sorties (`data/gold/`)

| Fichier | Contenu |
|---|---|
| `stock_series.parquet` | série annuelle utilisée par (cible, pays) : stock, attrition lissée, niveau, tranche d'âge |
| `indicators.parquet` | indicateurs par (cible, pays) et ligne `EU` |
| `scores.parquet` | composantes brutes et normalisées, poids couverts, score, rang |
| `ranking.csv` | export du classement (SPEC §6) : **uniquement les cibles publiées** (score non nul) ; les lignes non publiées restent dans `scores.parquet` à titre de diagnostic |
