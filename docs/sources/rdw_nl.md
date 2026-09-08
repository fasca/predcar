# Source : NL RDW — Gekentekende voertuigen (`m9d7-ebf2`)

**Statut : schéma observé sur la réponse réelle du 2026-09-08** (`data/raw/nl_rdw/2026-09-08/`,
203 051 lignes agrégées en 5 pages, 10 799 397 voitures particulières). Le layout présumé était
correct ; deux cas non prévus ont été ajoutés (ligne sans `handelsbenaming`, ligne sans année).
Toute divergence future lève `RdwSchemaError` : corriger `predcar/ingest/rdw.py` **et** ce document.

- Dataset : https://opendata.rdw.nl/Voertuigen/Open-Data-RDW-Gekentekende_voertuigen/m9d7-ebf2
- API SoQL : https://opendata.rdw.nl/resource/m9d7-ebf2.json
- Licence : CC0 1.0.

## Ce que l'on interroge

Le dataset est un **instantané véhicule par véhicule** du parc actuel, sans historique. Nous ne
téléchargeons jamais de lignes individuelles : une seule requête agrégée côté serveur.

```
$select = merk, handelsbenaming, date_extract_y(datum_eerste_toelating_dt) as jaar, count(*) as n
$where  = voertuigsoort='Personenauto'
$group  = merk, handelsbenaming, jaar
$order  = merk, handelsbenaming, jaar        # pagination stable par $offset
$limit  = 50000 / $offset = k × 50000       # jusqu'à une page courte
```

`kenteken` (plaque) n'apparaît jamais dans la projection ; `build_query` refuse tout champ interdit.

## Champs supposés

| Champ | Type Socrata | Usage |
|---|---|---|
| `merk` | text | `make_raw` (majuscules) |
| `handelsbenaming` | text | `model_raw` (majuscules) ; pas de niveau « modèle générique » → `model_gen_raw` null |
| `datum_eerste_toelating_dt` | floating timestamp | `date_extract_y(…)` → `year_first_reg` (`datum_eerste_toelating` est un *Number* `YYYYMMDD`, incompatible avec `substring`) |
| `voertuigsoort` | text | filtre `Personenauto` |
| `n` (alias) | nombre sérialisé en texte | `count` |

Liste de vérification, cochée sur la réponse du 2026-09-08 :

- [x] `datum_eerste_toelating_dt` existe en floating timestamp et `date_extract_y` est accepté.
- [x] `count(*)` et `jaar` sont renvoyés en chaînes (`"n": "1"`, `"jaar": "2014"`).
- [x] `voertuigsoort = 'Personenauto'` est la valeur des voitures particulières.
- [x] `$limit` de 50 000 accepté (pages pleines de 50 000 lignes, dernière page de 3 051).
- [x] Volume réel : 203 051 lignes (bien plus que « quelques dizaines de milliers ») ; 44 lignes sans
      `handelsbenaming` (46 véhicules, clé absente du JSON) ; 510 lignes sans `jaar` (13 186 véhicules) ;
      années de 1887 à 2026.
- [x] Environ 22 % des véhicules des marques cibles ont un `handelsbenaming` préfixé par la marque
      (`TOYOTA AYGO`, `ALFA GIULIETTA`) : le préfixe est retiré avant le mapping (`docs/mapping.md`).
      BMW utilise des familles (`3ER REIHE`, `X REIHE`) sans finition.

## Règles de parsing

- **Période** : la date du snapshot (`data/raw/nl_rdw/<YYYY-MM-DD>/`), pas une date du dataset.
- **Année** hors `1900..année du snapshot` ou vide → `year_first_reg` null, comptes sommés dans
  le seau « année inconnue », nombre de lignes journalisé.
- **Modèle absent** : une ligne sans `handelsbenaming` reçoit `model_raw = (MISSING)` (jamais
  supprimée ni fusionnée avec le `ONBEKEND` du RDW), nombre journalisé.
- **Statut** : null (le RDW n'a pas d'équivalent SORN ; `vervaldatum_apk` pourrait servir de
  proxy en phase 2).
- **Réponse vide** → erreur **avant** toute écriture, jamais un snapshot vide.
- Le snapshot archive les lignes (`gekentekende_voertuigen_agg.json`) et la requête exacte
  (`query.json`), écrits atomiquement (`.part` puis rename) et tous deux exigés dans
  `MANIFEST.json` à l'ingestion. Snapshot immuable : refetch le même jour → erreur.

## Limites

Pas d'historique avant le premier snapshot : l'attrition NL ne sera calculable qu'après
`attrition.min_history_years` (3 ans) de snapshots mensuels, conformément à SPEC §5
(composantes manquantes exclues et poids renormalisés).
