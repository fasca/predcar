# Changelog

Toutes les évolutions notables de predcar, par pull request fusionnée. Format inspiré de
[Keep a Changelog](https://keepachangelog.com/fr/1.1.0/). La version 1.0.0 (2026-09-15) clôt
les trois phases de la spec ; les entrées suivantes iront dans une section « Non publié »
au-dessus d'elle.

Chaque entrée signale aussi ce qui reste **non validé sur données réelles**. L'accès aux
sources dépend de l'environnement et se revérifie à chaque session (leçon du 2026-09-09) :
il fonctionne depuis le WSL2 de l'utilisateur et, au 2026-09-12, depuis l'environnement
Claude Code. Voir `docs/ARCHITECTURE.md` §7.

## [1.0.1] — 2026-09-18

### 2026-09-18 — Correctifs après audit de production

**Corrigé** — le refresh trimestriel rejoue désormais tous les snapshots RDW versionnés et
ingère les huit millésimes KBA avant le score. Chaque snapshot RDW conserve aussi `query.json` ;
le manifeste orphelin du 2026-09-12 a été retiré de `data/raw/` (sa trace reste dans les bundles
de preuves). Le déploiement Pages reçoit le SHA exact créé par le refresh, afin de ne pas
reconstruire le bundle précédent.

**Corrigé** — le ratio SORN reste au niveau génération même lorsque sa dernière valeur est
zéro. L'âge d'une inflexion européenne est calculé dans le calendrier du pays qui l'observe :
un snapshot NL plus récent ne pénalise plus une inflexion GB. Le tableau de score défile dans
sa carte sur mobile et le parc allemand est toujours présenté comme celui du modèle complet,
jamais comme celui d'une génération.

## [1.0.0] — 2026-09-15

Première version publiée. Tout ce que `docs/SPEC.md` prévoyait a soit été livré, soit été
vérifié et écarté avec preuve : score v1 sur GB + NL (262 cibles, 249 classées), Allemagne
publiée à côté du score, projection Weibull, outil de candidats, page « Évolutions » et flux
Atom, refresh trimestriel automatique ; France, enchères, STATS19, Google Trends et YouTube
écartés (`docs/SOURCES.md`). Site : https://fasca.github.io/predcar/

### 2026-09-15 — PR : signaux phase 2 (STATS19, Google Trends, YouTube) vérifiés et écartés
**Ajouté** — `docs/sources/stats19_uk.md` : schéma observé de la table `vehicle` STATS19
(fichier complet 2021–2025, 937 265 lignes) et la raison de l'écarter : `generic_make_model`
est une liste fermée de 593 modèles courants, hors liste → `-1` ; aucun Ferrari, Aston Martin,
Lotus, TVR ; **35 des 200 modèles cibles seulement ont un véhicule accidenté**, les plus
courants. Un taux d'accident ne couvrirait que 17 % des cibles, les moins rares — biais orienté
contre le score. Section « Signaux phase 2 » dans `docs/SOURCES.md` : Google Trends (429, pas
d'API, `pytrends` = scraping) et YouTube Data API (403 sans clé, signal de notoriété) écartés.

**Modifié** — `docs/SPEC.md` §2.5, §2.6, §5, §7, `docs/methodology.md` §6, `CLAUDE.md`,
`tasks/todo.md` : le score v1 reste le score ; toutes les pistes de la spec ont une réponse
vérifiée. Aucun changement de code.

### 2026-09-15 — PR : page « Évolutions » et flux Atom (alertes sans compte)
**Ajouté** — `predcar/changes.py` compare les `ranking.csv` des deux derniers bundles committés
et le site publie le résultat : `evolutions.html` (un bloc par type de changement, lien vers la
page modèle) et `feed.xml` (Atom, une entrée par refresh, découvrable via `<link rel="alternate">`).
Six types de changement : cible publiée / sortie du classement, palier de rareté franchi,
point d'inflexion apparu, entrée / sortie du top N (`alerts.top_n: 50` dans `config/score.yaml`).
**Un mouvement de rang seul n'est pas signalé** : dès qu'une cible s'ajoute, tous les rangs bougent
(169 mouvements ≥ 10 places le 14/09 pour 21 entrées). `export.report_dirs()` liste les bundles.
Vérifié sur 13/09 → 14/09 : 21 publiées, 1 palier (106 Rallye S2, 233 → 86), 5 inflexions,
3 entrées et 10 sorties du top 50. `docs/methodology.md` §8, README, ARCHITECTURE.

**Corrigé** — `rarity_tier` était calculé par pays mais mis à null sur la ligne Europe, donc
absent de `ranking.csv` alors que c'est un livrable de la spec §5. Il est désormais calculé
depuis le parc européen (`metrics.rarity_tier_expr`) et exporté. Bundle `reports/2026-09-15/`
identique au 14/09 à cette colonne près (vérifié : 249 lignes, rangs et parcs inchangés).

**Revue des 33 candidats restants** : aucun second lot (modèles de base dont la version sportive
est déjà cible ; Audi A2, BMW 7 Series, allroad C5, Delta hors Integrale, Saab 900 examinés et
écartés). Détail dans `tasks/todo.md`.

### 2026-09-15 — PR : premier lot de cibles issu de `candidates.csv` (243 → 262)
**Ajouté** — 19 générations choisies parmi les 41 candidats pour leur intérêt collector avéré
ou probable : Audi Coupé B3 et Cabriolet B4, Citroën C6, Fiat Punto HGT, Ford Escort RS Turbo,
RS2000 et XR3i (deux générations), Sierra XR4i et XR4x4, Lancia Thema, Mazda MX-6, Mercedes
190 W201 et 190E 2.3-16, Opel Carlton GSi et Corsa GSi (B et C), Peugeot 106 GTI, Volvo 850 T5.
Les modèles de base restants (306, 406, Escort, Sierra, Sunny, Renault 19…) ne sont pas
retenus : ce qui est recherché est leur version sportive, et elle est désormais une cible.

**Corrigé — quatre versions recherchées étaient avalées par la règle du modèle de base**, et
c'est la liste des candidats qui l'a révélé (leur « perte » gonflait celle du modèle de base) :
- `COUPE S2 4WD TURBO` → Coupé, au lieu de **S2** (39 378 véhicule-trimestres) ;
- `INTEGRA R` — l'appellation britannique de la **Type R DC2** — → Integra (133 669) ;
- `106 GTI` → **106 Rallye**, alors que la GTI 1.6 16v n'en est pas une (213 517) ;
- `ESCORT RS TURBO`, `RS2000`, `XR3I`, `SIERRA XR4X4`, `CARLTON GSI`, `850 T5`,
  `190E 2.3-16`, `190 E-16 EVOLUTION II` → modèle de base.
Conséquences visibles : **quatre cibles existantes deviennent publiées** — Audi S2 (73), Integra
Type R DC2 (294) et DC5 (254), Thema 8.32 (70, qui trouve enfin un pair dans son segment) ; la
106 Rallye S2 passe de 233 à **86** véhicules ; la 190E 2.5-16 gagne son Evolution II.

**Repli ajouté** pour `INTEGRA TYPE R` hors 1995–2006 : 12 véhicules démappés depuis toujours.

**Effet** — 261 cibles avec données, **249 publiées** (228 avant). GB **+12 véhicules** mappés
(les 12 ci-dessus), NL −1, DE inchangé. Les 5 témoins gardent leur parc au véhicule près. 224
rangs bougent : 21 nouvelles lignes s'intercalent, rien d'autre. En tête des nouvelles : Corsa
GSi B (102 véhicules, rang 3), Audi S2 (73, rang 6), Escort XR3i MK3/4 (512, rang 10).

**Ce que les tests ont attrapé** : une Corsa GSi immatriculée en 2001 est une **C**, pas une B —
mon attente était fausse, le test paramétré sur les libellés réels l'a corrigée. 33 candidats
restent dans `reports/<date>/candidates.csv`.

### 2026-09-14 — PR : `predcar candidates`, et les enchères écartées après vérification
**Ajouté**
- `predcar candidates` / `make candidates` (`predcar/candidates.py`) →
  `reports/<date>/candidates.csv` : les modèles **mappés mais absents de la liste des cibles**
  dont le parc GB (VEH0120, hors SORN) a perdu au moins la moitié de son **maximum
  historique**, avec le parc au pic et son année, le parc actuel, la perte, et les cibles que
  la marque a déjà — pour repérer une `306` à côté d'une `306 S16 MK1`. Seuils dans
  `config/mapping.yaml: candidates` (`stock_peak_min`, `stock_now_max`, `loss_min`,
  `exclude_model_gen`). 5 tests.
- **L'outil propose, il n'écrit jamais dans `target_models.csv`** : une cible est une
  génération avec ses années de production, ce que la donnée ne porte pas. La liste reste une
  décision éditoriale.

**Sur données réelles** — 41 candidats. En tête : Renault 19 (116 325 au pic en 1997, **48**
aujourd'hui), Opel Carlton (187 896 → 102), Peugeot 309 (186 845 → 137), Ford Sierra
(1 044 602 → 1 030), Nissan Sunny, Peugeot 306 / 406 / 106, Ford Escort, Opel Omega. Mesurer la
perte depuis le pic réel plutôt que depuis 2014 en révèle dix de plus que l'estimation
initiale — des modèles déjà presque disparus en 2014.

**Enchères : vérifiées et écartées** — `docs/SOURCES.md`, `docs/SPEC.md` §2.7. Les cinq sites
ferment l'accès automatisé : 403 dès `robots.txt` chez Car & Classic et Catawiki, 403 sur les
ventes chez Collecting Cars, Bring a Trailer injoignable, et Aguttes interdit **nommément**
`ClaudeBot`. Aucune API, aucun jeu ouvert. La spec conditionnait le scraping au respect de
`robots.txt` : contourner un 403 ou une interdiction explicite est exclu, quelle que soit la
valeur des données. Aucun code écrit.

**`ranking.csv` identique au bit près.** 283 tests.

### 2026-09-14 — PR : projection Weibull à 5 et 10 ans (phase 3, publiée hors score)
**Ajouté**
- `metrics.fit_weibull()` et `metrics.weibull_projection()` : chaque cohorte d'immatriculation
  est ajustée sur `R(t) = exp(−(t/λ)^k)` puis prolongée ; le parc projeté d'une cible est la
  somme de ses cohortes ajustées, avec une fourchette (ajustement décalé de ±2 écarts-types,
  **indicative**). Python pur, aucune dépendance nouvelle.
- `config/score.yaml` → bloc `weibull` (`horizons: [5, 10]`, `min_points: 5`, `min_cohorts: 3`).
- `gold/projection.parquet`, écrit par `make score`, exporté dans le bundle.
- Page modèle : section « Projection à 5 et 10 ans » (parc actuel → projeté, fourchette,
  `k`, `λ`, cohortes ajustées / totales) avec la phrase « ni une prédiction de valeur, ni une
  composante du score » ; et, quand rien n'a pu être projeté, **pourquoi**.
- `docs/methodology.md` §3 ter. 12 tests (266 → 278).

**Le modèle qu'il a fallu corriger** — un premier fit non conditionnel donnait `k ≈ 4` pour
tous les modèles et faisait perdre 98 % à une M3 E46 en dix ans. Cause : les registres
commencent en 2014, quand une cohorte de 2004 a déjà dix ans et a perdu une partie de son
parc ; la rétention est donc relative à la **première observation**, pas au nombre construit.
Le modèle juste est la survie **conditionnelle** `R(t)/R(t₀) = exp(−((t/λ)^k − (t₀/λ)^k))`,
ajustée par grille sur `k` et forme fermée sur `λ`. Un test génère une cohorte observée
seulement à partir de dix ans et exige que `k = 1,5, λ = 20` soient retrouvés.

**Garde-fous** — fit refusé s'il tombe sur la borne de la grille ou si `λ` sort de 2–150 ans ;
cohorte exclue si son parc **remonte** de plus de 5 % après sa deuxième observation (imports,
réimmatriculations) ; cible sans projection sous `min_cohorts`, et la page dit alors combien
de cohortes manquaient et pourquoi.

**Sur données réelles** — 109 cibles projetées, `k` médian 1,8 (q10–q90 : 1,1–2,85),
`λ` médian 20 ans (12–30), perte médiane à dix ans 64 %, fourchette contenant la projection
sur 218/218 lignes. M3 E46 : 3 556 → 2 368 à 5 ans, 1 582 à 10 ans (`k` 1,05, `λ` 14).
**Trois témoins sur cinq n'ont pas de projection** — RS2, 205 GTI, Clio Williams : 11 des 17
cohortes de la 205 GTI *remontent*, ce sont des classiques que l'on importe. C'est la limite
documentée des cohortes ouvertes, pas un défaut du fit.

**`ranking.csv` identique au bit près** — la projection ne touche pas au score.

### 2026-09-14 — PR : inventaire des 9 tables de la page DfT (Source-First)
Les 12 CSV de la page inventoriés, en-têtes lus par requête `Range`, table par table dans
`docs/sources/dft_uk.md`. **Aucune table ne donne les sorties du parc** (casse, export) — la
question posée. VEH0220 et VEH0270 sont les jumelles annuelles de VEH0120 et VEH0160 avec la
**cylindrée** en plus (seul gain possible, marginal : le mapping GB est à 99,0 %) ; VEH0125,
VEH0135, VEH0145 sont géographiques sans modèle ; VEH0520 concerne les poids lourds. Édition
vérifiée **identique** à l'archive (tailles au byte près), seules les URLs ont tourné. Rien à
ingérer, aucun parseur écrit.

### 2026-09-14 — PR : la France écartée après vérification (Source-First)
**Vérifié, puis écarté** — `docs/SPEC.md` §2.4 donnait une piste : « immatriculations de
voitures neuves par marque et modèle » sur data.gouv.fr. Elle ne donne rien.

Le seul jeu d'immatriculations du SDES (« Immatriculations de véhicules routiers », Licence
Ouverte) est ventilé **par commune**. En-tête réel, lu par requête `Range` :

```
"COMMUNE_CODE";"COMMUNE_NOM";"CARBURANT";"STATUT_UTILISATEUR";"GROUPE";"CATEGORIE";"IMMAT_2010";…
```

**Ni marque, ni modèle.** Les recherches « immatriculation », « marque modèle véhicule »,
« parc automobile » sur l'API data.gouv.fr ne ramènent rien d'autre au niveau modèle — les
jeux « parc automobile » sont des flottes d'organisations. Les données par modèle sont
commerciales (AAA Data), donc hors du périmètre open data du projet.

**Aucun parseur n'a été écrit** : c'est précisément ce que le Source-First doit produire.
`docs/SOURCES.md` et `docs/SPEC.md` §2.4 sont corrigés et datés.

**Sur les trois sources restantes de la phase 2** (STATS19, Google Trends, YouTube) —
`tasks/todo.md` porte maintenant le point de fond : chacune ajouterait un indicateur qui
**n'existe pas dans le score v1** (`config/score.yaml` : rareté, conservation, SORN,
inflexion). Les ingérer sans décider d'un score v2 produirait des données que rien n'utilise.
Ce qu'il faut arbitrer d'abord : quel indicateur, quel poids, au détriment de quoi.

### 2026-09-14 — PR : groupes multi-marques du KBA (10 marques cibles rendues visibles)
**Ajouté** — 20 règles dans `mapping/makes.csv` qui résolvent les constructeurs couvrant
plusieurs marques, avec le mécanisme `model_regex` posé pour MINI et Smart :
`FCA (I)` et `STELLANTIS (I)` → Fiat, Alfa Romeo, Lancia, Abarth, Jeep ; `STELLANTIS (F)` et
`GENERAL MOTORS (E)` → Opel, Peugeot, Citroën ; `GENERAL MOTORS (USA)` → Chevrolet, Cadillac ;
`JAGUAR LAND ROVER (UK)` → Jaguar, Land Rover ; `MG ROVER (UK)` → Rover, MG, MINI, Land Rover.

Une ligne **sans** regex porte la marque dominante du groupe, les lignes conditionnelles les
autres. Les regex d'un même groupe sont tenues **disjointes** pour que l'ordre de déclaration
n'ait aucun effet.

**Effet** — 11,1 M de véhicules-années entrent dans le périmètre des marques cibles, et **dix
marques cibles deviennent visibles en Allemagne** : Fiat 1 341 938, Opel 3 805 672,
Peugeot 960 493, Citroën 771 473, MINI 587 900, Jaguar 81 081, Alfa Romeo 78 002, Abarth
20 244, Lancia 9 342, MG 4 431. La table de référence passe de **81 à 97 modèles** — Alfa 156,
GTV, Fiat Coupé, Jaguar XJS y entrent.

La couverture DE passe de 98,9 % à **98,5 %** : le dénominateur grandit de 11,1 M, pas le
numérateur d'autant. Toujours très au-dessus du seuil commun de 95 %.

**GB et NL inchangés**, **`ranking.csv` inchangé** (l'Allemagne reste hors score), 266 tests,
bundle à 0 erreur. Un test vérifie sur les libellés réels que chaque groupe atteint bien ses
marques et n'en laisse aucune sur le label du groupe.

### 2026-09-14 — PR : les 8 millésimes allemands, et la série de référence
**Corrigé** — deux formes d'agrégat que le contrôle de somme signalait sans les nommer :
- une **ligne de sous-total publiée sans son libellé** (2019, 3 124 094 véhicules : le total
  d'Audi). Elle se reconnaît à ceci qu'elle porte un comptage mais **ni libellé ni colonne
  technique** — une vraie ligne de véhicule a toujours un Typ-Schl.-Nr., une puissance ou un
  carburant. Critère vérifié sur les huit millésimes : une seule ligne concernée, **aucun faux
  positif** ;
- une **deuxième orthographe fautive** du sous-total : `HYUNDAI MOTOR (ROK) ZUSAMMEM`, avec un
  `M` final (2021 et 2022), après le `ZSAMMEN` sans `U` de 2019.

**Les 8 millésimes 2019 → 2026 sont désormais exploitables** (contre 5), dont cinq à l'écart
**exactement nul** ; les trois autres à +0,014 %, −0,05 % et −0,31 %. **Aucune tolérance n'a
été assouplie** — les deux correctifs sont vérifiés par mutation.

**Ajouté** — `metrics.reference_stock()` publie la **série annuelle** et non plus le seul
dernier point : 595 lignes, 81 modèles, 2019 → 2026 sans trou. La page modèle affiche
l'évolution : « Allemagne · KBA FZ 2.2 · 2026 · 166 013 · **+24,9 % depuis 2019** · les 5
générations cibles de ce modèle, confondues ».

**Ce que cela ne change pas** — l'Allemagne **reste hors du score**. J'avais annoncé que
récupérer ces millésimes débloquerait l'attrition allemande : c'est faux. Le blocage n'a jamais
été le nombre de points mais l'**absence d'année de première immatriculation**, qui empêche de
répartir un modèle entre ses générations (`docs/methodology.md` §3 bis). Huit points au lieu de
cinq enrichissent la donnée publiée, pas le score.

Couverture DE **98,9 %** sur les 8 millésimes (312,7 M de véhicules-années), GB et NL
inchangés, `ranking.csv` **inchangé**, 265 tests, bundle à 0 erreur.

### 2026-09-14 — PR : l'Allemagne publiée à côté du score, pas dedans
**Décision** — après mesure, l'Allemagne **n'entre pas** dans le score, contrairement à ce qui
était envisagé. Le KBA publie le parc par nom commercial **sans année de première
immatriculation** : un modèle ne peut pas être réparti entre ses générations. Seules **55 des
243 cibles (23 %)** pourraient recevoir un parc allemand — celles qui sont l'unique génération
cible de leur modèle. Or la rareté pèse 35 % du score et se calcule en **comparant les cibles
entre elles** : une Audi S3 gagnerait 100 686 véhicules et paraîtrait bien moins rare qu'une
RS4 B5 qui n'en gagnerait aucun, non parce qu'elle l'est, mais parce que la source en dit plus
sur elle. Le classement serait faussé en faveur des modèles à une seule génération cible.

**Ajouté**
- `metrics.reference_stock()` et `metrics.REFERENCE_SERIES` : parc national par **modèle** des
  séries non découpables par génération, avec le **nombre de générations cibles couvertes**.
  `FZ2` y figure et reste absente de `GEN_LEVEL_SERIES` et `MODEL_LEVEL_SERIES` — un test
  verrouille cette exclusion.
- `data/gold/reference_stock.parquet`, écrit par `make score`.
- Page modèle : section « **Parc national, hors score** » qui affiche le chiffre, la série, son
  année, et dit ce qu'il couvre (« les 5 générations cibles de ce modèle, confondues ») **et**
  pourquoi il est exclu. `docs/methodology.md` §3 bis explique le biais en détail.
- Libellés manquants : `DE` → « Allemagne », et la fiche source `KBA FZ 2.2`.
- 5 tests (257 → 262), dont un qui vérifie qu'aucune section n'apparaît sans la table.

**`ranking.csv` est identique au bit près** : 228 cibles publiées, aucun rang ni parc modifié.
Bundle `reports/2026-09-14/` à 0 erreur.

**Ce qui ferait entrer l'Allemagne dans le score** : une source allemande portant l'année de
première immatriculation, ou une répartition par génération vérifiable. Ni l'une ni l'autre
n'existe aujourd'hui dans les données ouvertes du KBA.

### 2026-09-13 — PR : marques filles vendues sous leur maison mère (DE 96,6 % → 98,9 %)
**Ajouté**
- `mapping/makes.csv` accepte une troisième colonne **optionnelle**, `model_regex` : la marque
  devient conditionnelle au libellé du modèle. `normalize.MakeOverride`,
  `normalize.load_make_overrides()` et un paramètre `make_overrides` sur `normalize.apply()`,
  appliqué sur `make_raw` **avant** toute règle de modèle.
- Trois surcharges : MINI sous `BMW`, Smart sous `DAIMLER (D)` et sous `MERCEDES-BENZ (E)`.
- 7 tests unitaires + 1 test sur les libellés réels du bundle, qui échoue si une surcharge
  cesse de matcher.

**Pourquoi** — un constructeur n'est pas toujours une marque. Le KBA publie les MINI sous BMW
et les Smart sous Daimler, or **MINI et Smart sont des marques cibles**. Un fourre-tout aurait
été faux : il aurait crédité **5,1 M de véhicules** à BMW et Mercedes-Benz, gonflé ces deux
marques, et laissé les cibles MINI Cooper S et Smart Roadster **sans aucun parc allemand** —
donc artificiellement rares, et surévaluées dès que l'Allemagne entrera dans le score.

**Deux cas trouvés par le test sur les libellés réels**, pas par relecture :
- `JOHN COOPER WORKS` est la ligne sportive de MINI et ne commence pas par `COOPER` ;
- `EQ FORTWO` est la Smart électrique, préfixée par la marque électrique de Mercedes.

**Rétro-compatible** : un `makes.csv` à deux colonnes reste valide, et `apply()` sans
surcharges se comporte exactement comme avant — les deux sont testés.

**Effet mesuré** : DE **96,6 % → 98,9 %**, GB **identique au véhicule près**
(2 710 536 642), NL +72 véhicules (des MINI que le RDW publie aussi sous « BMW »),
228 cibles publiées, **aucun rang modifié**. Seules les deux MINI Cooper S gagnent 1 et 11
véhicules. 257 tests, bundle `reports/2026-09-13/` à 0 erreur.

**Reste** — les groupes multi-marques `FCA (I)`, `STELLANTIS (F)`, `GENERAL MOTORS`,
`JAGUAR LAND ROVER` relèvent du même mécanisme : leur marque est dans le nom commercial. Les
règles sont à écrire.

### 2026-09-13 — PR : mapping allemand, 1re passe (DE 93,1 % → 96,6 %)
**Corrigé**
- `config/mapping.yaml` : `SONSTIGE/NICHT GETYPT` et `SONSTIGE HERSTELLER` rejoignent
  `unknown_labels`. Le parseur KBA les déclarait déjà « modèle inconnu » (`kba.UNKNOWN_MODELS`)
  mais la config ne les listait pas : 4,6 M de véhicules que la source elle-même dit non typés
  étaient comptés comme *non mappés*. **À eux seuls : 93,1 % → 95,3 %.**
- `mapping/models.csv` : la règle Volvo `^(S60|V70).*\bR\b` ne reconnaissait pas les libellés
  espacés ; `S 60 R` et `V 70 R` étaient perdus (+3 véhicules sur la cible S60 R P2).

**Ajouté** — fourre-tout étendus aux libellés allemands, ~2,5 M de véhicules :
- marques filles **non cibles** vendues sous leur maison mère : Dacia sous Renault
  (`DUSTER`, `SANDERO`…), Cupra sous Seat (`CUPRA LEON`, `FORMENTOR`, `BORN`) ;
- libellés multi-noms séparés par une virgule ou un point-virgule : `8D,AUDI A4,S4`,
  `BUSINESS;MULTIVAN`, `VW 1600,KAEFER 1303 LS` ;
- gammes écrites avec un espace : `V 70`, `S 60`, `S 70` (Volvo) ;
- Coccinelle et camping-cars VW, `BIG NUGGET` (Ford), `VIVARO` (Peugeot), `5ER` (BMW).

**Deux pièges d'inversion** documentés dans `docs/mapping.md` : `CUPRA LEON` (marque Cupra,
après 2018) n'est **pas** la cible `LEON CUPRA` (Seat, 1999–2012), et `AMG C 43` n'est pas la
cible `C43 AMG`. Les règles ancrées les séparent ; une regex non ancrée les confondrait.
Une regex ne peut pas non plus contenir de virgule — le fichier est un CSV.

**L'exemption de la gate est retirée.** `min_coverage_by_country` redevient vide : l'Allemagne
passe le seuil commun de 95 % avec de la marge. La mécanique reste en place pour la prochaine
source.

**GB et NL inchangés** : GB 99,0 % au véhicule près (2 710 536 642), NL 98,4 %, 228 cibles
publiées, **aucun rang modifié**. Seule la Volvo S60 R gagne 3 véhicules, effet du correctif
ci-dessus. Bundle `reports/2026-09-13/` à 0 erreur, 250 tests verts.

**Non fait, et c'est une décision d'architecture** — MINI (sous BMW) et Smart (sous Daimler)
sont des marques **cibles** vendues sous leur maison mère : 4,6 M de véhicules, ~2,3 points de
couverture. Un fourre-tout les attribuerait à BMW et Mercedes, ce qui serait faux. Il faut
pouvoir réassigner la marque depuis le nom commercial — ce qui réglerait aussi les groupes
`FCA` / `STELLANTIS` / `GENERAL MOTORS` / `JAGUAR LAND ROVER`. Voir `tasks/todo.md`.

### 2026-09-13 — PR : rendre le classement lisible (aide à la lecture)
**Ajouté**
- Bloc « Comment lire ce tableau » en tête du classement, ouvert par défaut : ce que
  représente une ligne, puis **chaque colonne** (rang, années, pays, parc, attrition, score,
  composantes) et la **légende des quatre barres**, qui reprend exactement les mêmes étiquettes
  courtes que le tableau (`R`, `C`, `SORN`, `Infl.`) et le motif hachuré d'une composante absente.
- Infobulle sur **tous** les en-têtes de colonne du classement sauf « Modèle », et sur les dix
  colonnes de la table par pays de la page modèle.
- Page modèle : une phrase dit à quoi sert la colonne « Médiane des pairs » — l'attrition d'une
  génération ne veut rien dire seule, elle se lit contre celle des modèles du même segment et
  du même âge.
- 4 tests : chaque colonne est documentée, chaque en-tête porte une infobulle, les étiquettes
  de la légende couvrent celles des barres, et la page modèle explique la comparaison.

**Pourquoi** — retour d'usage sur le site publié : le tableau n'indiquait ni le sens ni
l'échelle de ses colonnes. Rien ne disait qu'une attrition **négative** signifie un parc qui
augmente, que le score va de 0 à 1, ni ce que valaient `R`, `C`, `SORN`, `Infl.`. La page
affirme aussi désormais ce que ces chiffres **ne sont pas** : ni une cote, ni un prix, ni une
prédiction de valeur — et qu'une composante manquante est exclue, jamais comptée 0.

**Corrigé**
- `test_unpublished_target_has_page_but_no_rank` découpait l'index sur `<details` en supposant
  qu'il n'y en avait qu'un ; il cible maintenant `<details class="unpublished"`.

### 2026-09-13 — PR : ingestion KBA (Allemagne), phase 2 étape 1
**Ajouté**
- `predcar/ingest/kba.py`, `predcar fetch de --year` / `ingest de`, `make fetch-de` /
  `make ingest-de` : parc allemand au 1ᵉʳ janvier par constructeur et nom commercial
  (KBA **FZ 2**, feuille FZ 2.2) → `data/silver/fleet_stock_de_kba_<année>.parquet`.
- `docs/sources/kba_de.md` : schéma observé sur les 8 classeurs réels, dix pièges documentés,
  tableau des millésimes avec leur écart au total publié, liste de vérification cochée.
- 33 alias de constructeurs allemands dans `mapping/makes.csv` (`VOLKSWAGEN (D)` →
  `VOLKSWAGEN`, `DAIMLER (D)` → `MERCEDES-BENZ`…). Les libellés bruts ne sont jamais modifiés.
- `min_coverage_by_country` (`config/mapping.yaml`) : seuil de couverture par pays. La gate
  était globale — ingérer l'Allemagne aurait fait échouer `make normalize` pour GB et NL, et
  avec lui le refresh trimestriel. DE est exempté et daté, sa couverture reste publiée.
- Dépendances : `fastexcel` (lecture XLSX), `openpyxl` en dev (fabrication des fixtures).
- 27 tests (219 → 246), fixtures **découpées dans les vrais classeurs** 2024 et 2020 pour
  couvrir les deux dispositions d'en-tête.

**La spec se trompait de table** — vérifié par requête HTTP : **FZ 10 n'existe pas** (404 sur
17 millésimes) et FZ 17 est au niveau marque seulement (≤ 140 lignes). La table utilisable est
FZ 2.2, ~16 600 lignes au niveau nom commercial. `docs/SPEC.md` §2.3, `CLAUDE.md` et
`docs/SOURCES.md` sont corrigés et datés.

**L'invariant de somme, et ce qu'il a trouvé** — la feuille publie son propre total ; les
lignes de détail sont comparées à lui, de façon asymétrique : au-dessus = une ligne d'agrégat
comptée deux fois, erreur ; en dessous = comptages supprimés par le KBA, attendu et journalisé.
Ce seul contrôle a révélé trois défauts qu'aucun test sur un schéma supposé n'aurait vus :
- les sous-totaux `ZUSAMMEN` changent de colonne selon le millésime (collés au constructeur
  jusqu'en 2024, seuls dans la colonne du nom commercial en 2026) — les garder **doublait le
  parc allemand**, 96 M au lieu de 49 M ;
- leur orthographe n'est pas fiable : le fichier 2019 contient `CITROEN (F) ZSAMMEN` ;
- le report des libellés de groupe franchissait les frontières de constructeur : le bloc Audi
  2019 s'ouvre sans nom commercial, juste après Aston Martin, et ses lignes étaient créditées
  à un modèle Aston Martin. Ces lignes deviennent `(MISSING)`, jamais supprimées.

**Cinq millésimes sur huit sont exploitables** : 2020, 2023, 2024, 2025, 2026 — quatre au
véhicule près, 2026 à −0,31 % (comptages supprimés par la source). 2019, 2021 et 2022 portent
des lignes d'agrégat non identifiables (dans 2019, une ligne de 3 124 094 véhicules dont les
trois libellés sont vides) : **refusés** plutôt que devinés. La série allemande a donc un trou
en 2021–2022, à traiter avant d'en tirer une attrition.

**Non fait, volontairement** — le mapping allemand. Le `Hersteller` du KBA est un groupe
industriel (`FCA (I)`, `STELLANTIS (F)` mélange Corsa, 208 et C5 Aircross) et les MINI sont
vendues sous BMW : la couverture DE est à **93,1 %**. C'est du travail de règles, pas de
parsing, et il se fera sur le rapport de couverture réel. `metrics.series_of` reconnaît `FZ2`
pour que les lignes allemandes coexistent dans le silver, mais la série est **absente de
`MODEL_LEVEL_SERIES`** : `ranking.csv` est **identique au bit près** après cette PR, GB 99,0 %
et NL 98,4 % inchangés.

### 2026-09-12 — PR : site statique (phase 1, étape 5)
**Ajouté**
- `predcar site` / `make site` (`predcar/site.py`, gabarits Jinja2 dans `site/templates/`,
  CSS/JS dans `site/static/`) : site statique en français rendu vers `site/dist/` (non versionné).
  - Classement des cibles publiées avec filtres segment / décennie / pays et tri (score,
    « se raréfient le plus vite / le moins vite », parc le plus faible), top 50 par défaut,
    barres des quatre composantes, liste repliée des cibles à score non publié et pourquoi.
  - Une page par génération cible : rang et score, tableau des composantes (valeur, poids,
    part du score, explication), parc par pays, attrition lissée, rétention par cohorte,
    comparaison au segment (médiane des pairs, nombre de pairs, inflexion, ratio SORN),
    sources citées avec dernière observation et licence, date des données.
  - Page méthodologie rendue depuis `docs/methodology.md`, précédée des paramètres réels de
    `config/score.yaml` ; classement téléchargeable (`ranking.csv` et une copie datée
    `predcar-classement-<date>.csv`).
  - Graphiques Plotly.js chargés depuis le CDN, données embarquées dans chaque page ; message
    de repli si le CDN est inaccessible ; axe des parcs à zéro.
- `data/gold/cohorts.parquet` (`metrics.cohort_retention`) : courbes de rétention agrégées par
  (cible, pays, cohorte d'immatriculation), `retention = stock / stock maximal observé`.
- `.github/workflows/pages.yml` : build et déploiement GitHub Pages sur push touchant `site/`,
  `reports/`, `predcar/site.py`, `docs/methodology.md` ou `config/score.yaml`, `workflow_call`
  et déclenchement manuel. Aucun accès réseau aux sources, aucun run de pipeline.
- `.github/workflows/refresh.yml` : cron trimestriel (20 janvier / avril / juillet / octobre),
  pipeline complet, export, **tests rejoués sur le nouveau bundle avant tout commit** (un
  relabellisage DfT ou une dérive de couverture échoue là, pas en production), compression du
  snapshot RDW, commit, puis appel explicite du déploiement.
- Tests (13 → 14 sur le site, 220 au total) : rendu complet sur la population synthétique,
  formats français, JSON embarqué qui ne peut pas fermer la balise `<script>`, **égalité
  stricte entre un build depuis le Parquet d'un run et depuis le CSV d'un bundle**, bundle
  incomplet ignoré, absence de chemin absolu dans les pages, cohorte à une seule observation
  nommée et non dessinée.

**Le site lit le dernier bundle committé, pas `data/gold/`**
`site.resolve_gold_dir()` prend le `gold/` du plus récent `reports/<date>/` contenant
`gold/ranking.csv` (un export dont l'étape `score` a échoué est sauté, pas une erreur), et la
**date affichée est celle du bundle**, pas celle du rendu. Conséquences : un déploiement prend
quelques secondes au lieu de ~190 Mo et 20 minutes, ne casse pas si gov.uk est momentanément
indisponible ou si la gate de couverture échoue, et ce que le site affiche est reproductible
depuis le dépôt seul. `--gold-dir data/gold` rend un run local frais. `export.latest_report()`
accepte un critère de complétude plutôt que de dupliquer la recherche du dernier bundle.

**Honnêteté des graphiques** — le site prétend mesurer un déclin :
- l'axe des parcs démarre à zéro (un axe tronqué exagère exactement ce qu'on mesure) ;
- une cohorte observée **une seule fois** (toutes les cohortes RDW tant que les snapshots
  mensuels ne se sont pas accumulés) est **exclue** de la courbe de rétention et **nommée** sous
  le graphique avec la raison : normalisée par elle-même elle afficherait 100 %, ce qui se
  lirait « rien n'a encore disparu » ;
- une composante absente est signalée absente (poids renormalisés), jamais dessinée à 0 ;
- la page dit que `sorn_ratio` est le ratio brut repris *tel quel* comme composante, sinon la
  carte « part SORN » et la barre de composante semblent mesurer deux choses différentes.

**Modifié**
- `metrics.COHORTS_SCHEMA` rendu public (il était lu comme membre privé depuis `site.py`).
- `score.py` : suppression de `is_finite()`, morte depuis son introduction. `pyproject.toml` :
  `duckdb` documenté comme outil de requêtes ad-hoc, non importé par le paquet.
- Suppression de `tasks/next.md` : `tasks/todo.md` (le plan) et `tasks/lessons.md` (les règles)
  suffisent — trois fichiers de reprise concurrents finissent par se contredire, voir la leçon
  du 2026-09-12 sur les branches ouvertes.
- `docs/ARCHITECTURE.md`, `README.md` §7, `CLAUDE.md`, `docs/methodology.md` §7 alignés.

**Vérifié sur données réelles** — rendu depuis `reports/2026-09-12/` : 242 cibles, 228 classées,
aucun lien interne cassé, et les 5 témoins conformes au bundle (parc et rang) : M3 E46 4 863
(rang 72), S2000 3 801 (64), 205 GTI 1 989 (43), Clio Williams 142 (100), RS2 34 (4) — les
parcs à −1 viennent du snapshot RDW du 2026-09-08 rejoué à la place de celui du 12, jamais
committé (voir l'entrée du run réel).
**Restent à observer sur GitHub** : le premier déploiement Pages (opt-in *Settings → Pages →
Source : GitHub Actions* requis) et les deux crons. La courbe de rétention par cohorte
n'apparaîtra qu'au premier bundle exporté après cette PR, `cohorts.csv` n'existant dans aucun
bundle antérieur.

### 2026-09-12 — PR : cron mensuel RDW et archives brutes compressées
**Ajouté**
- `.github/workflows/rdw-snapshot.yml` : tous les 1ᵉʳ du mois (03h17 UTC) + `workflow_dispatch`.
  Il archive un snapshot agrégé, **vérifie qu'il est exploitable** (`ingest nl` avant tout
  commit, pour ne jamais versionner une réponse tronquée), le compresse et committe
  `MANIFEST.json` + `*.json.gz` sur `main`.
- `predcar compress nl` / `make compress-nl` et `raw.compress()`, `raw.resolve()`,
  `raw.read_bytes()` : une archive brute peut être stockée gzippée. Le manifest garde le
  sha256 du contenu **décompressé**, donc compresser ne change pas l'identité d'un fichier —
  `raw.verify()` et `rdw.ingest()` relisent l'un ou l'autre de façon transparente.
- `.gitignore` : les snapshots RDW gzippés sont versionnés (exception documentée).

**Pourquoi versionner ce payload-là** — le RDW est un instantané *sans historique amont* : un
mois qui n'est pas conservé est perdu pour toujours, et c'est précisément l'historique que le
projet cherche à construire. Un cron qui ne committerait que le `MANIFEST.json` archiverait
l'empreinte de données qu'on n'a plus. Gzippé, un mois pèse 1,2 Mo (contre 16,7 Mo brut) — soit
~14 Mo/an, acceptable. Les CSV DfT restent hors de git : 66 Mo et re-téléchargeables depuis
gov.uk avec tout leur historique.

**Modifié**
- `export.py` retrouve un payload archivé qu'il soit compressé ou non (`raw.resolve`), et
  profile la version décompressée ; la branche CSV/JSON suit le nom du manifest, pas le
  suffixe du fichier stocké.

### 2026-09-12 — PR : snapshot tests des 5 témoins et filet anti-régression
**Ajouté**
- `tests/witnesses.py` : les 5 modèles témoins de SPEC §8 (BMW M3 E46, Peugeot 205 GTI,
  Honda S2000, Renault Clio Williams, Audi RS2) avec leurs libellés réels, leurs libellés
  pièges et des bornes de stock larges (≈ ×5/÷5 autour du run de référence).
- `tests/test_witnesses.py` (45 cas) : deux couches indépendantes — *mapping* (les libellés
  réels du bundle rejoués dans les règles **courantes**, les finitions ne doivent pas tomber
  sur la cible) et *gold* (bornes de stock, invariant **EU = GB + NL**, série de niveau
  génération, 4 composantes de score, stock GB décroissant).
- `tests/test_real_labels.py` (13 cas) : filet générique sur **tous** les libellés réels —
  aucun conflit de règle, couverture ≥ 95 % par pays rejouée hors code de production, toute
  cible atteignable depuis un libellé réel (allowlist documentée : `FORD / RACING PUMA`), et
  une table `KEYWORD_RULES` qui encode chaque bug déjà survenu (ST-LINE, TYPE-R, 16V, VTR,
  XSI, Evo).
- `predcar.export.latest_report()` et `paths.REPORTS_DIR` : accès au bundle le plus récent.
- Fixtures de session partagées dans `tests/conftest.py` (`report`, `real_labels`,
  `real_labels_mapped`, `gold`, `stock_frame`) ; `tests/test_normalize.py` réutilise
  `stock_frame` au lieu de sa copie locale.

**Conception** — aucune nouvelle fixture figée : `reports/<date>/` est déjà versionné, donc la
CI y a accès sans réseau ni `data/`. Le bundle sert de **corpus d'entrée** (`model_raw`), jamais
d'oracle de mapping : ses colonnes `model_gen` / `generation` datent des règles du jour de
l'export. Seuls `gold/*.csv` servent d'oracle, en bornes larges insensibles à une republication
trimestrielle. Les tests tournent dans la CI existante, sans marqueur ni `skipif`.

**Vérifié par mutation** — en réintroduisant chaque bug historique, les tests échouent bien :
`TYPE[- ]?R` → `TYPE R` (2 échecs), lookahead `(?!-?LINE)` retiré (2 échecs), `year_manufacture`
ignoré (2 échecs), précédence des libellés retirée (1 échec). 142 → 200 tests.

**Limite assumée** — `labels_target_makes.csv` ne porte pas d'année : le filet générique ne peut
pas couvrir le bug « année d'immatriculation au lieu d'année de fabrication ». Il est couvert par
`test_witnesses.py::test_generation_uses_build_year` (seule la M3 est discriminée par l'année,
les 4 autres témoins portent leur génération dans le libellé — le contraste est asserté) et par
`test_normalize.py::test_generation_uses_build_year_before_first_registration_year`.

### 2026-09-12 — PR : re-run réel post-PR #7 et précédence des règles de libellé
**Corrigé**
- `normalize.apply` : une règle dont le **libellé porte lui-même la génération** (pas de plage
  d'années) l'emporte désormais sur une règle à plage d'années, comme `docs/methodology.md` §1
  le décrit déjà. Sans cette précédence, `M3 CSL` (année enregistrée 2012) et
  `LANCER EVOLUTION IX GT` / `EVO VIII GSR` faisaient échouer toute la normalisation
  (`MappingError`, 264 lignes, 168 véhicules, 0 conflit de `model_gen`). Les fourre-tout sans
  génération (`^PUMA(?!.*RACING)`) restent des replis et ne prennent pas le dessus — deux tests
  verrouillent les deux sens. Le bug était invisible avant #7 : c'est la priorité donnée à
  `year_manufacture` qui a déplacé les années de référence et créé les recouvrements.

**Ajouté**
- `reports/2026-09-12/` : premier bundle de preuves produit **après** la PR #7. Les 4 CSV DfT
  sont bit-à-bit identiques à ceux du 2026-09-08 (mêmes sha256), donc tout écart mesuré vient
  des corrections, pas d'un nouveau millésime.

**Résultats mesurés (2026-09-08 → 2026-09-12, stock Europe)**
| Cible | Avant | Après |
|---|---|---|
| HONDA CIVIC TYPE R EP3 | 2 (rang 31) | 4 139 (rang 48) |
| HONDA CIVIC TYPE R FN2 / EK9 | 1 978 / 2 | 7 174 / 38 (EK9 rang 5) |
| NISSAN SKYLINE GT-R R32 / R33 / R34 | 16 / 34 / 24 | 162 / 206 / 117 |
| MITSUBISHI LANCER EVOLUTION V_VI / VII_IX | 38 / 528 | 256 / 651 |
| RENAULT CLIO 16V MK1 | 148 | 264 |
| FORD FIESTA ST MK7 | 36 784 | 21 997 (ST-LINE retirées) |
| Couverture GB / NL (stock) | 0,9788 / 0,9820 | **0,9899 / 0,9840** |
| Anomalies | 1 123 (935 `cohort_rise` VEH0120) | **82**, toutes VEH0124 |
| Cibles avec données / publiées | 241 / 225 | 242 / 228 |

Témoins stables et cohérents (invariant EU = GB + NL vérifié, 4 composantes, couverture de
poids 1,0) : M3 E46 4 864, S2000 3 801, 205 GTI 1 990, Clio Williams 142, RS2 34.

**Connu, non corrigé**
- `predcar export` parcourt tous les dossiers `data/raw/<source>/<date>/` : sur un clone frais,
  les snapshots anciens n'ont que leur `MANIFEST.json` et produisent une erreur par payload
  absent (6 ici). Les trois étapes restent `ok` ; à traiter à part.

### 2026-09-09 — PR #7 : corrections d'après le premier export réel
**Corrigé (diagnostic de `reports/2026-09-08/`)**
- Mapping : `FIESTA ST-LINE` / `FOCUS ST-LINE` ne sont plus des ST (1,3 M et 1,0 M véhicules
  mal classés) ; `CIVIC TYPE-R` (tiret) rejoint la Civic Type R (2,8 M véhicules ratés, EP3
  comptée à 1 exemplaire) ; `CLIO DYNAMIQUE 16V` et consorts ne sont plus des Clio 16V MK1
  (12 M véhicules) ; `SAXO VTR`, `XSARA VTR`, `C2 VTR` ne sont plus des VTS ; `306 XSI` n'est
  plus une S16 ; `PUNTO HGT` n'est plus une Punto GT ; `CORSA GSI` n'est plus une VXR ; les
  Lancer Evo prennent leur génération du numéro dans le libellé (`EVO VI`) et non de l'année
  d'immatriculation en GB ; libellés RDW et DfT exotiques (`09-MAR` = 9-3, `380 SL`, `AMG A 35`,
  `8D AUDI A4`, `2CV6`, campers) ; repli sans génération pour les années hors plage (Puma).
  Couverture recalculée sur les libellés réels : GB 99,0 %, NL 98,5 %.
- Génération des imports : `year_manufacture` (VEH0124 `YearManufacture`) conservé dans le
  schéma silver et utilisé avant l'année de première immatriculation pour placer une voiture
  dans sa génération (une Skyline de 1999 immatriculée en GB en 2010 restait une R34).
- Attrition : Δt en années réelles entre dates d'observation (le trimestre Q1 2026 après le
  Q4 2025 comptait pour une année entière de pertes).
- Ratio SORN au niveau génération (VEH0124 porte le statut), repli modèle générique.
- Anomalies : seulement les vraies cohortes (VEH0124, RDW) après la fin de production ; les
  montées en charge d'un modèle neuf et les générations déduites du libellé (VEH0120) ne sont
  plus signalées (1 123 « anomalies » dont l'immense majorité était du bruit).
- Couverture : les libellés `MODEL MISSING` / `(MISSING)` / `ONBEKEND` sont comptés à part et
  exclus du dénominateur (`config/mapping.yaml: unknown_labels`).
- Export : `manifest.json.stages` (`ok` / `absent` / `failed`) ; `uv run` dans le cycle documenté.

**Ajouté**
- `CHANGELOG.md`, `docs/ARCHITECTURE.md`, liens dans le README, règle « une entrée par PR ».

### 2026-09-09 — commit direct sur `main` (session Claude Code locale) : premier run réel
**Modifié**
- VEH0124 : schéma réel (pas de `Fuel`, `YearManufacture`, `LicenceStatus` Licensed/SORN
  présent), marqueur `[z]` massif, `[x]` dans les années → seau « année inconnue ».
- RDW : lignes sans `handelsbenaming` → `(MISSING)`, lignes sans année ; préfixe marque
  retiré des libellés (`TOYOTA AYGO` → `AYGO`), familles BMW (`3ER REIHE`).
- `models.csv` : 11 familles de regex trop larges corrigées (`\b`), règles ajoutées ; couverture
  GB 97,9 %, NL 98,2 % ; 241 cibles avec données, 225 publiées.
- Docs des sources cochées sur les fichiers réels, `docs/SOURCES.md` avec URLs vérifiées,
  `reports/2026-09-08/` committé, leçons dans `tasks/lessons.md`.

### 2026-09-08 — PR #6 : export des résultats pour analyse à distance
**Ajouté**
- `predcar export` / `make export` : dossier de preuves `reports/<date>/` léger et
  versionnable — manifest (commit git, versions, config, comptes, erreurs par étape),
  60 premières lignes verbatim et profil de chaque CSV brut, profil du JSON RDW, résumé
  silver, tous les libellés bruts des marques cibles avec mapping et volume, non-mappés
  complets, couverture, anomalies (cohortes en hausse, sauts de stock), gold en CSV.
- Best-effort : `manifest.json` consigne l'état de chaque étape (`stages` : `ok`, `absent`
  quand il n'y avait rien à exporter, `failed` avec le détail dans `errors`) et le reste est
  écrit quand même.
- README §6 (commandes à lancer et à committer), `CLAUDE.md` : lire le dernier export en
  début de session.

### 2026-09-08 — PR #5 : indicateurs et score v1 (phase 1, étape 4)
**Ajouté**
- `predcar/metrics.py` : séries annuelles par famille de source (VEH0120, VEH0124, RDW,
  jamais additionnées), niveau génération ou modèle générique, attrition −Δln(Stock)/Δt
  lissée sur 3 ans, pairs (même pays, segment, tranche d'âge de 5 ans, ≥ 3 modèles
  distincts), attrition relative, point d'inflexion, ratio SORN, ventes cumulées, survie,
  étiquette de rareté, agrégat Europe.
- `predcar/score.py` : composantes 0–1, poids renormalisés sur les composantes disponibles,
  gate `min_weight_coverage`, `components_available`, rang ; `predcar score` / `make score`
  → `data/gold/` + `ranking.csv`.
- `config/score.yaml` : `peers.age_bucket_years`, `peers.min_peers`.
- `docs/methodology.md` : chaque formule, chaque source, chaque limite.

**Corrigé (review)**
- Identité des cibles `(marque, modèle, génération)` : SPIDER Alfa Romeo et SPIDER Renault
  ne sont plus fusionnées.
- Repli sur le stock du modèle générique seulement si la génération est la seule de son
  modèle ; un modèle seul dans son segment n'est pas son propre pair ; somme Europe nulle
  si nulle partout ; run d'inflexion réinitialisée sur année manquante ; `ranking.csv`
  limité aux cibles publiées ; `data/gold/*.csv` hors git.

### 2026-09-08 — PR #4 : mapping marques/modèles et `normalize` (phase 1, étape 3)
**Ajouté**
- `mapping/target_models.csv` (~240 générations cibles 1990–2015), `makes.csv` (alias),
  `models.csv` (règles regex + plages d'années disjointes, fourre-tout par marque).
- `predcar/normalize.py` et `predcar normalize` / `make normalize` : application des règles,
  détection des règles contradictoires, couverture par pays, rapport des non-mappés,
  `CoverageError` sous `config/mapping.yaml:min_coverage` (0.95), `--min-coverage 0` pour
  explorer.
- README « Récupérer les données (à faire depuis votre machine) », `docs/mapping.md`.

**Corrigé (review)**
- Conflits `NSX`, `POLO GTI`, `SCIROCCO` entre fourre-tout et règles cibles ; sorties
  écrites seulement après la gate de couverture ; test systématique sur toutes les cibles.

### 2026-09-08 — PR #3 : ingestion RDW (phase 1, étape 2)
**Ajouté**
- `predcar/ingest/rdw.py` : requête SoQL agrégée côté serveur (marque × modèle × année de
  première admission), garde-fou contre tout champ personnel (`kenteken`), pagination
  stable, archive immuable lignes + requête, parse → `fleet_stock` NL (période = date du
  snapshot). `predcar fetch nl` / `ingest nl`, `make fetch-nl` / `ingest-nl`.
- `docs/sources/rdw_nl.md` (schéma présumé + liste de vérification).

**Corrigé (review)**
- `date_extract_y(datum_eerste_toelating_dt)` au lieu de `substring` sur un champ Number ;
  réponse vide refusée avant écriture ; écriture atomique ; `query.json` exigé.

### 2026-09-08 — PR #2 : bootstrap v2 et ingestion UK DfT (phase 1, étape 1)
**Ajouté**
- Projet uv / Python 3.12 / Polars / DuckDB / Pydantic / Typer, Makefile, ruff, pytest, CI
  GitHub Actions ; `config/score.yaml`, `config/sources.yaml` ; archive raw immuable avec
  `MANIFEST.json` (sha256) ; schémas silver `fleet_stock` / `fleet_new_reg` et invariants.
- `predcar/ingest/dft.py` : résolution des URLs sur la page gov.uk, unpivot des tables
  VEH0120 / VEH0124 / VEH0160, voitures uniquement, marqueurs de suppression rejetés,
  `Total` vérifié = Licensed + SORN. `predcar fetch uk` / `ingest uk` / `validate`.
- `docs/sources/dft_uk.md`, `docs/SOURCES.md`, README v2 ; `requirements.txt` supprimé.

**Corrigé (review)**
- Snapshot incomplet refusé ; totaux vérifiés seulement si les deux statuts sont visibles ;
  téléchargement atomique et refus d'écraser un snapshot.

### 2026-09-08 — PR #1 : spécification v2
**Modifié**
- `docs/SPEC.md` remplacé par la spec MVP v2 (open data uniquement, zéro scraping, zéro
  prix) ; `CLAUDE.md` aligné ; `CLAUDE_CODE_PROMPT.md` supprimé.

**Corrigé (review)**
- Composante d'attrition orientée (`conservation = −attrition_relative`) ; règle de
  composantes manquantes (exclusion + renormalisation) ; génération attribuée depuis
  l'année de première immatriculation uniquement ; courbes de rétention agrégées à la place
  de Kaplan-Meier.

### Validé sur données réelles (dernier état : 2026-09-12)
- Validé au 2026-09-08 : layout des CSV DfT, réponse de l'API RDW, couverture du mapping,
  241 cibles scorées avec les quatre composantes.
- Vérifié depuis, par le re-run du 2026-09-12 (`reports/2026-09-12/`) : l'effet de
  `year_manufacture` sur les générations des imports (Skyline R32/R33/R34 séparées, Evo par le
  numéro du libellé), la distribution des composantes après correction des règles, et le stock
  des cibles témoins — Civic Type R EP3 à 4 139 exemplaires au lieu de 1.
- Reste à observer sur GitHub : le premier déploiement Pages et les crons (mensuel RDW,
  trimestriel de rafraîchissement).
