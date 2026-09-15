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
| KBA FZ 2.2 | DE | annuelle, au 1ᵉʳ janvier | **modèle générique uniquement** | parc allemand — **informatif, hors score** (§3 bis) |

VEH0120 et VEH0124 décrivent le même parc : ils ne sont **jamais additionnés**. Pour chaque
(génération cible, pays), le stock et l'attrition viennent de la série de niveau génération
quand elle existe (VEH0124, RDW), sinon de la série de niveau modèle générique (VEH0120,
sommée sur les générations) — **uniquement si la génération cible est la seule de son modèle
générique**, sinon tout le parc du modèle serait crédité à chaque génération et la cible
reste sans donnée. Le niveau utilisé est exposé (`level`).

Les séries infra-annuelles sont ramenées à une valeur par an : **dernière période de
l'année** (la date réelle est conservée pour le Δt de l'attrition).

**Génération d'un véhicule** : l'année qui place une voiture dans une génération est son
**année de fabrication** quand la source la donne (`YearManufacture` de VEH0124), sinon son
année de première immatriculation. Sans cela, une Skyline de 1999 importée et immatriculée
en GB en 2010 serait comptée dans la génération de 2010. Le libellé prime quand il porte
lui-même la génération (`LANCER EVO VI`, `M3 CSL`).

## 2. Indicateurs

Par (marque, modèle générique, génération, pays) — deux marques peuvent partager un libellé de modèle (SPIDER Alfa Romeo et Renault) et ne sont jamais fusionnées :

- **Stock(t)** : véhicules en circulation = tous statuts sauf `sorn`.
- **Ventes cumulées** : immatriculations neuves VEH0160 du modèle générique sur les années de
  production de la génération (`target_models.csv`). Indisponible avant 2001 et hors GB.
- **Survival(t)** = Stock(t) / max(ventes cumulées, stock maximal observé).
- **Attrition annuelle** a(t) = −(ln Stock(t) − ln Stock(t−1)) / Δt, Δt en années **réelles**
  entre les deux dates d'observation (un trimestre Q1 après un Q4 vaut 0,25 an, pas 1),
  puis moyenne glissante sur `attrition.smoothing_years` (3) valeurs ; définie à partir de la
  4e observation. Indisponible si moins de `attrition.min_history_years` (3) valeurs lissées.
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
- **Ratio SORN** (GB uniquement) = SORN / (SORN + Licensed) à la dernière période, au niveau
  génération quand VEH0124 porte le statut de la génération (cas général), sinon au niveau
  modèle générique (VEH0120, toutes générations confondues).
- **Rareté absolue** : stock courant ; étiquette `<20`, `<100`, `<500`, `>=500`
  (`rarity.thresholds`).

## 3 bis. L'Allemagne, publiée mais hors score

Le KBA publie le parc allemand par constructeur et **nom commercial**, sans aucune année de
première immatriculation. Un modèle ne peut donc pas être réparti entre ses générations.

La conséquence n'est pas une simple perte de précision, c'est un **biais de comparabilité**.
Seules les cibles qui sont l'unique génération cible de leur modèle pourraient recevoir un parc
allemand : **55 sur 243, soit 23 %**. Or la rareté — 35 % du score — se calcule en comparant les
cibles entre elles. Une Audi S3 gagnerait 100 686 véhicules allemands et paraîtrait bien moins
rare qu'une RS4 B5 qui n'en gagnerait aucun : non pas parce qu'elle l'est, mais parce que la
source nous en dit plus sur elle. Le classement serait faussé de façon systématique, en faveur
des modèles à une seule génération cible.

L'Allemagne est donc **publiée à côté du score, jamais dedans** : `gold/reference_stock.parquet`
donne la **série annuelle** du parc du **modèle** (toutes générations confondues, 2019 → 2026)
avec le nombre de générations cibles qu'il recouvre ; la page modèle affiche le dernier point,
son évolution depuis 2019, ce qu'il couvre et pourquoi il est exclu.

Ce qui la ferait entrer dans le score : une source allemande portant l'année de première
immatriculation, ou une répartition par génération vérifiable. Ni l'une ni l'autre n'existe
aujourd'hui dans les données ouvertes du KBA.

## 3. Agrégat Europe

Une ligne `EU` par génération cible : stock sommé sur les pays ; attrition, attrition
relative et survie pondérées par le stock des pays où elles existent ; point d'inflexion =
le plus récent des pays ; ratio SORN = valeur GB. Une valeur absente partout reste absente
(null, jamais NaN ni 0).

## 3 ter. Projection Weibull à 5 et 10 ans (publiée, hors score)

Pour chaque (cible, pays, cohorte d'immatriculation), la courbe de rétention agrégée
`R(âge) = Stock(âge) / Stock maximal observé` est ajustée sur une loi de Weibull :

```
R(t) = exp(−(t/λ)^k)        linéarisée :  ln(−ln R) = k·ln t − k·ln λ
```

Moindres carrés sur les points `0 < R < 1` (le pic `R = 1` et `R = 0` sont indéfinis dans la
linéarisation). Sont **exclues, comptées et affichées** : les cohortes de moins de
`weibull.min_points` observations, et celles dont la rétention **remonte** de plus de 5 % entre
deux observations (imports, réimmatriculations — déjà journalisées comme anomalies). Une
cible n'a de projection que si `weibull.min_cohorts` cohortes ont pu être ajustées.

Projection d'une cohorte : `Stock_actuel × R(âge + h) / R(âge)`, sommée sur les cohortes
ajustées ; `stock_now` est le parc de **ces cohortes seulement**, pour que le ratio
projeté / actuel porte sur la même population. La fourchette reprend le calcul avec la
droite décalée de ±2 écarts-types résiduels : c'est **indicatif**, pas un intervalle de
confiance formel (pas d'événements individuels, cohortes ouvertes).

`k` et `λ` publiés sont les médianes sur les cohortes ajustées. `k < 1` : la disparition
ralentit avec l'âge (les survivantes sont gardées) ; `k > 1` : elle s'accélère. `λ` est l'âge
auquel 63 % d'une cohorte a disparu.

**Pourquoi hors score** : c'est une extrapolation de la tendance observée, pas une mesure. La
mettre dans le score reviendrait à noter deux fois la même attrition.

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
- La projection Weibull (§3 ter) prolonge une tendance ; elle ne sait rien d'un choc à venir (réglementation, carburant, mode).

## 7. Sorties (`data/gold/`)

| Fichier | Contenu |
|---|---|
| `stock_series.parquet` | série annuelle utilisée par (cible, pays) : stock, attrition lissée, niveau, tranche d'âge |
| `projection.parquet` | projection Weibull à 5 et 10 ans par (cible, pays) : parc actuel des cohortes ajustées, projeté, fourchette, `k` et `λ` médians, cohortes ajustées / totales — **jamais utilisé par le score** |
| `reference_stock.parquet` | parc national par **modèle** des séries non découpables par génération (Allemagne), avec le nombre de générations cibles couvertes — affiché sur le site, **jamais utilisé par le score** |
| `indicators.parquet` | indicateurs par (cible, pays) et ligne `EU` |
| `scores.parquet` | composantes brutes et normalisées, poids couverts, score, rang |
| `cohorts.parquet` | courbes de rétention par (cible, pays, cohorte d'immatriculation) : `retention = stock / stock maximal observé de la cohorte` (VEH0124, RDW), affichées sur la page modèle du site |
| `ranking.csv` | export du classement (SPEC §6) : **uniquement les cibles publiées** (score non nul) ; les lignes non publiées restent dans `scores.parquet` à titre de diagnostic |

## 8. Évolutions et flux

Le projet n'a ni compte ni liste de diffusion. Son alerte est un **diff** : à chaque refresh
trimestriel, un nouveau bundle de preuves est committé, le site est reconstruit depuis les
**deux derniers**, et la page « Évolutions » — reprise dans un flux Atom auquel on s'abonne
sans laisser d'adresse — liste ce qui a changé.

Est un changement : une cible **publiée** ou **sortie** du classement, un **palier de rareté**
franchi vers le bas (`>=500` → `<500` → `<100` → `<20`, seuils de `rarity.thresholds`), un
**point d'inflexion apparu**, une **entrée ou sortie du top N** (`alerts.top_n`).

N'en est pas un : **un mouvement de rang seul**. Dès qu'une cible s'ajoute, tous les rangs en
dessous se décalent — 169 mouvements de dix places ou plus le jour où 21 cibles sont entrées.
Le signaler noierait le reste.
