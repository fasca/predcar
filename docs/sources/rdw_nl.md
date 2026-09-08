# Source : NL RDW — Gekentekende voertuigen (`m9d7-ebf2`)

**Statut : schéma *présumé*, à valider contre une réponse réelle de l'API.**
`opendata.rdw.nl` était inaccessible depuis l'environnement de développement (proxy sortant).
Le layout ci-dessous suit la documentation Socrata du dataset ; il doit être confirmé par
`make fetch-nl` puis `make ingest-nl` sur une machine connectée. Toute divergence lève
`RdwSchemaError` avec le détail : corriger `predcar/ingest/rdw.py` **et** ce document.

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

Points à vérifier sur la réponse réelle (cases à cocher) :

- [ ] `datum_eerste_toelating_dt` existe bien en floating timestamp et `date_extract_y` est accepté
      (repli : `datum_eerste_toelating` en Number, `floor(datum_eerste_toelating / 10000)`).
- [ ] `count(*)` et `jaar` renvoyés en chaîne ou en nombre JSON : les deux sont acceptés.
- [ ] Valeur exacte de `voertuigsoort` pour les voitures particulières (`Personenauto`).
- [ ] `$limit` de 50 000 accepté par l'endpoint (sinon réduire `PAGE_SIZE`).
- [ ] Volume de la réponse agrégée (attendu : quelques dizaines de milliers de lignes).

## Règles de parsing

- **Période** : la date du snapshot (`data/raw/nl_rdw/<YYYY-MM-DD>/`), pas une date du dataset.
- **Année** hors `1900..année du snapshot` ou vide → `year_first_reg` null, comptes sommés dans
  le seau « année inconnue », nombre de lignes journalisé.
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
