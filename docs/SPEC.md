# predcar — Spécification MVP v2

> Objectif : produire une **preuve statistique, sourcée et datée** de la raréfaction des modèles automobiles 1990–2015 en Europe, à partir de données publiques, et en dériver un score de potentiel « collector ».
> Périmètre MVP : **zéro scraping**, zéro compte utilisateur, zéro prix de marché. Un pipeline de données reproductible + un site statique.

## 1. Décisions structurantes

| Sujet | Décision | Pourquoi |
|---|---|---|
| Sources | Uniquement open data officiel (UK, NL, DE, FR) | Gratuit, licence claire, historique long, pas de risque juridique |
| Scraping marketplaces | **Hors MVP** (phase 3, optionnel) | Fragile, coûteux, risque légal (CGU, DataDome, RGPD) |
| Prix | Hors MVP | Le classement par raréfaction se tient sans ; réintroduire plus tard via résultats d'enchères publics |
| Sentiment forums | Remplacé par Google Trends + YouTube (phase 2) | Séries temporelles stables, pas de scraping |
| Stack | Python 3.12, Polars, DuckDB, Pydantic, Typer, uv ; site statique (Astro ou MkDocs + Plotly) | Léger, reproductible, hébergeable sur GitHub Pages |
| Orchestration | `make` + GitHub Actions (cron mensuel) | Suffisant pour des refresh trimestriels |
| Stockage | Fichiers Parquet versionnés dans `data/` (raw immuable, silver, gold) + DuckDB pour requêter | Pas de serveur à maintenir |

## 2. Sources de données

### 2.1 Royaume-Uni — DfT / DVLA (référence principale)

Page : https://www.gov.uk/government/statistical-data-sets/vehicle-licensing-statistics-data-files

| Fichier | Contenu | Historique | Usage |
|---|---|---|---|
| `df_VEH0120_GB` | Véhicules en fin de trimestre par statut (Licensed / SORN), carrosserie, marque, modèle générique, modèle, carburant. 1 colonne par trimestre. | 1994 Q4 → aujourd'hui | Courbe de stock trimestrielle ; ratio SORN/Licensed |
| `df_VEH0124_AM` / `df_VEH0124_NZ` | Idem + année de première mise en circulation + année de fabrication, annuel. Split A–M / N–Z. | 2014 → aujourd'hui | Survie par cohorte (millésime) |
| `df_VEH0160_GB` | Premières immatriculations par marque/modèle, trimestriel | 2001 → aujourd'hui | Dénominateur « ventes cumulées » |

Notes : CSV directs, ~60 Mo pour VEH0120. Les colonnes trimestrielles sont à *unpivoter*. Le champ `GenModel` regroupe les variantes (« 3 SERIES ») ; `Model` est la variante exacte (« 330I SE »). Le MVP travaille au niveau `GenModel` + regroupement manuel par génération (voir §4).

Concurrent/inspiration à étudier : howmanyleft.co.uk (UK seulement, pas de score, pas de cohortes multi-pays).

### 2.2 Pays-Bas — RDW Open Data (véhicule par véhicule)

Dataset `Gekentekende_voertuigen` : https://opendata.rdw.nl/Voertuigen/Open-Data-RDW-Gekentekende_voertuigen/m9d7-ebf2
API Socrata (SoQL) : https://opendata.rdw.nl/resource/m9d7-ebf2.json — doc : https://dev.socrata.com/foundry/opendata.rdw.nl/m9d7-ebf2
Licence CC0. Export CSV complet : `https://opendata.rdw.nl/api/views/m9d7-ebf2/rows.csv?accessType=DOWNLOAD` (plusieurs Go — préférer l'API avec `$select` agrégé).

Champs utiles : `merk`, `handelsbenaming`, `datum_eerste_toelating`, `datum_eerste_tenaamstelling_in_nederland`, `vervaldatum_apk`, `catalogusprijs`, `voertuigsoort`, `europese_voertuigcategorie`.

Requête d'agrégation type (compte de parc actuel par marque/modèle/année) :
```
$select=merk,handelsbenaming,substring(datum_eerste_toelating,1,4) as jaar,count(*) as n
&$where=voertuigsoort='Personenauto'
&$group=merk,handelsbenaming,jaar
&$limit=500000
```

Limite : le dataset est un **instantané** du parc actuel (pas d'historique). Stratégie : snapshot mensuel archivé dans `data/raw/rdw/YYYY-MM/` pour construire l'historique nous-mêmes à partir de maintenant. Tables annexes `brandstof` (8ys7-d773), `carrosserie` (vezc-m2t6).

### 2.3 Allemagne — KBA (Kraftfahrt-Bundesamt)

Portail : https://www.kba.de/DE/Statistik/Fahrzeuge/Bestand/bestand_node.html (Bestand = parc) et https://www.kba.de/DE/Statistik/Fahrzeuge/Neuzulassungen/neuzulassungen_node.html (immatriculations neuves).

| Série | Contenu | Format |
|---|---|---|
| FZ 10 (Bestand nach Herstellern und Typen) | Parc au 1er janvier par constructeur et type (codes HSN/TSN + libellé) | XLSX annuel |
| FZ 17 | Bestand par Marke/Modellreihe | XLSX annuel |
| FZ 10 (Neuzulassungen) | Immatriculations neuves mensuelles par Marke/Modell | XLSX mensuel |

Notes : pas d'API, fichiers Excel avec en-têtes multi-lignes → parseur dédié et tests de non-régression par millésime. **Tâche 1 pour Claude : inventorier les URLs exactes des XLSX 2010–2026 et documenter le schéma de chaque millésime** (les libellés changent).

### 2.4 France — SDES / data.gouv.fr

- Immatriculations de voitures neuves par marque et modèle (mensuel) : rechercher « immatriculations voitures particulières neuves modèle » sur https://www.data.gouv.fr — jeux SDES/AAA Data.
- Parc roulant (par âge, énergie, département, **pas par modèle**) : « parc automobile » SDES.

Usage MVP : dénominateur ventes pour les modèles vendus en France ; pas de stock par modèle. Documenter le manque.

### 2.5 Accidents / sinistralité (phase 2)

- **STATS19** (UK, DfT road casualty statistics) : https://www.data.gov.uk/dataset/cb7ae6f0-4be6-4935-9277-47e5ce24a11f/road-safety-data — table `vehicle` avec `generic_make_model`, âge et sexe du conducteur, gravité. Normaliser par le parc VEH0120 → taux d'accident par modèle et par tranche d'âge conducteur.
- **Euro NCAP** (https://www.euroncap.com) : notes de sécurité par modèle/année (pas d'API officielle ; à scraper léger ou saisir manuellement pour la liste cible).
- Group rating ABI/Thatcham (UK, 1–50) : proxy coût de réparation/vol.
- France BAAC (ONISR) : pas de modèle → exclu.

### 2.6 Attachement / sentiment (phase 2)

- Google Trends via `pytrends` : requêtes `"<modèle> à vendre"`, `"<modèle> for sale"`, `"<modèle> restauration"`, geo UK/FR/DE/NL.
- YouTube Data API : nombre de vidéos et vues cumulées pour `<marque> <modèle>` (quota gratuit suffisant).
- Effectifs de communautés : subreddits, groupes Facebook (saisie manuelle pour la liste cible, pas de scraping).

### 2.7 Prix (phase 3, optionnel)

Résultats d'enchères publics : Collecting Cars, Car & Classic, Catawiki, Bring a Trailer (US, référence), Aguttes/Artcurial/Bonhams. Ventes réelles, pas prix demandés. Marketplaces (AutoScout24, mobile.de, LeBonCoin) : uniquement si valeur démontrée, via Scrapling, avec respect robots.txt et rate limiting.

## 3. Modèle de données

```
data/
  raw/      # téléchargements immuables, nommés <source>/<YYYY-MM-DD>/<fichier>
  silver/   # parquet normalisés, un schéma commun
  gold/     # agrégats et scores
```

Schéma silver commun `fleet_stock` :

| colonne | type | note |
|---|---|---|
| country | str | GB, NL, DE, FR |
| period | date | fin de trimestre ou 1er janvier |
| make_raw, model_raw | str | tel que fourni |
| make, model_gen | str | normalisés (§4) |
| generation | str | ex. `E46`, `MK1` — via table de mapping manuel |
| year_first_reg | int | null si non fourni |
| status | enum | licensed, sorn, null |
| count | int | |
| source, source_file | str | traçabilité |

Schéma `fleet_new_reg` : country, period, make, model_gen, generation, count, source.

## 4. Normalisation marque/modèle (le vrai travail)

Chaque pays écrit « BMW 3 SERIES », « BMW 3ER », « BMW 320I », « BMW 3-SERIE ». Approche :

1. `mapping/makes.csv` : alias → marque canonique.
2. `mapping/models.csv` : (make, regex sur model_raw, plage d'années) → (model_gen, generation).
3. Couverture mesurée : le pipeline échoue si < 95 % du parc d'un pays est mappé pour les marques cibles.
4. Liste cible initiale : ~150 modèles 1990–2015 des segments coupé/sportive/GTI/roadster/berline premium, choisis à la main dans `mapping/target_models.csv`.

## 5. Indicateurs et score

Par (model_gen, generation, country) puis agrégé Europe :

- **Stock(t)** : véhicules en circulation.
- **Survival(t)** = Stock(t) / max(ventes cumulées, Stock max observé).
- **Attrition annuelle** = −Δln(Stock) / Δt, lissée sur 3 ans.
- **Attrition relative** = attrition du modèle − attrition médiane des modèles de même segment et même âge médian (le signal clé : un modèle qui disparaît *moins vite* que ses pairs est déjà conservé).
- **Ratio SORN** (UK) = SORN / (SORN + Licensed) : part déjà mise en collection.
- **Point d'inflexion** : année où l'attrition passe sous la médiane du segment (début de « collectorisation »).
- **Rareté absolue** : Stock actuel, seuils < 500 / < 100 / < 20 exemplaires.
- Phase 2 : taux d'accident normalisé (STATS19/VEH0120), tendance Google Trends 5 ans, volume YouTube.

Score composite v1 (pondérations explicites dans `config/score.yaml`, toutes révisables) :
`score = 0.35·rareté + 0.25·attrition_relative + 0.20·ratio_SORN + 0.20·point_inflexion_récent`.
Chaque composante est exposée individuellement : le site montre le *pourquoi*, pas seulement le rang.

Méthode statistique : courbes de survie Kaplan-Meier par cohorte (VEH0124, RDW) ; ajustement Weibull pour extrapoler le stock à 5/10 ans avec intervalle de confiance.

## 6. Livrables du site

Site statique généré depuis `gold/` :

- Page classement : top 50 « modèles qui se raréfient le plus vite / le moins vite », filtres segment/décennie/pays.
- Page modèle : courbe de stock par pays, courbe de survie par cohorte, ratio SORN, comparaison au segment, sources citées avec date de refresh.
- Page méthodologie : chaque formule, chaque source, chaque limite.
- Export CSV du classement.

## 7. Phases

**Phase 1 — MVP (cible : 3 mois de soirées)**
1. Ingestion UK (VEH0120, VEH0124, VEH0160) + tests.
2. Ingestion RDW (snapshot agrégé mensuel) + tests.
3. Mapping marques/modèles pour la liste cible, couverture ≥ 95 %.
4. Calcul stock/survie/attrition/SORN, score v1.
5. Site statique déployé sur GitHub Pages, refresh trimestriel par GitHub Actions.

**Phase 2** : KBA (DE), immatriculations FR, STATS19, Google Trends, YouTube.

**Phase 3** : enchères, extrapolation Weibull publiée, newsletter/alertes.

## 8. Qualité et contraintes

- Chaque fichier raw est archivé avec checksum ; les transformations sont pures et rejouables.
- Tests : schéma par millésime de source, invariants (stock ≥ 0, somme licensed+SORN cohérente, cohortes monotones), snapshot tests sur 5 modèles témoins (BMW E46 M3, Peugeot 205 GTI, Honda S2000, Renault Clio Williams, Audi RS2).
- Aucune donnée personnelle (RDW : jamais stocker `kenteken`, toujours agréger côté API).
- Licences des sources documentées dans `docs/SOURCES.md` (OGL v3 UK, CC0 RDW, DL-DE/BY-2-0 KBA, Licence Ouverte FR).

## 9. Instructions pour Claude Code

- Lire `CLAUDE.md` puis ce fichier. Travailler par PR, une phase-étape par PR.
- Avant tout code de parsing : télécharger un échantillon de chaque source dans `data/raw/`, documenter le schéma observé dans `docs/sources/<source>.md`, écrire les tests de schéma, **puis** le parseur.
- Ne jamais introduire de scraping de marketplace dans les phases 1–2.
- Tout paramètre de score dans `config/score.yaml`, jamais en dur.
- Quand une URL de source est incertaine (KBA, data.gouv), la vérifier par requête HTTP et consigner l'URL finale dans `docs/SOURCES.md`.
