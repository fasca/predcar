# CarCollector Predictor — Lessons Learned

_Ce fichier est mis à jour après chaque correction. Claude doit le lire au début de chaque session._

## Format
```
### [DATE] Leçon courte
- **Erreur**: Ce qui s'est passé
- **Correction**: Ce qui aurait dû être fait
- **Règle**: Règle à suivre dorénavant
```

---

_Aucune leçon enregistrée pour le moment. Ce fichier sera enrichi au fil du développement._

### 2026-09-08 Règles de mapping fourre-tout en conflit avec des cibles
- **Erreur**: les fourre-tout `OTHER` de Honda et VW listaient `NSX`, `SCIROCCO` et
  `POLO ?[A-Z]`, en conflit avec les règles cibles → `MappingError` sur toute normalisation.
  Détecté par la review, pas par les tests (seuls 21 libellés témoins choisis à la main).
- **Correction**: test systématique qui passe le nom de **chaque** cible dans `apply` et exige
  une résolution sans conflit ; sorties écrites seulement après la gate de couverture.
- **Règle**: toute table de règles (mapping, config) a un test qui itère sur **toutes** ses
  entrées, jamais seulement sur des exemples choisis. Une commande qui écrit plusieurs
  fichiers les met en attente et n'écrit qu'après la dernière validation.

### 2026-09-08 Clé d'identité incomplète et sorties générées commises
- **Erreur**: les indicateurs étaient clés sur (model_gen, generation) sans la marque, alors que
  deux marques partagent des libellés (SPIDER) ; `data/gold/ranking.csv` a été commis car
  `.gitignore` n'excluait que les Parquet.
- **Correction**: `(make, model_gen, generation)` partout, `data/gold/*.csv` ignoré.
- **Règle**: la clé d'une entité est la clé complète de sa table source (ici `target_models.csv`),
  jamais un sous-ensemble « qui semble suffire ». Tout nouveau répertoire de sorties générées
  est ignoré par git **dans le même commit** que la commande qui l'écrit.

### 2026-09-09 Schéma « présumé » codé sans une seule ligne réelle
- **Erreur**: le parseur VEH0124 supposait `Fuel`, `YearOfManufacture` et l'absence de
  `LicenceStatus` ; le fichier réel n'a pas `Fuel`, s'appelle `YearManufacture` et porte
  Licensed/SORN. Fixtures et tests reproduisaient l'hypothèse fausse, donc étaient verts.
- **Correction**: lire l'en-tête réel par requête `Range` (2 Ko suffisent, même sur un CSV de
  60 Mo) avant d'écrire la moindre colonne dans un parseur ; profiler les valeurs distinctes des
  colonnes d'identification et les marqueurs sur le fichier complet avant l'ingestion.
- **Règle**: aucun schéma n'est « présumé » : s'il n'y a pas au moins l'en-tête réel dans
  `docs/sources/<source>.md`, on n'écrit pas le parseur. Une fixture de test est toujours
  dérivée d'un extrait réel, jamais imaginée.

### 2026-09-09 Blocage réseau supposé permanent
- **Erreur**: CLAUDE.md et README affirmaient que le proxy bloquait les sources ; la session a
  failli demander à l'utilisateur de lancer les fetch ailleurs alors que `curl` répondait 200.
- **Correction**: tester l'accès (`curl -sS -o /dev/null -w "%{http_code}"`) en début de session
  avant de suivre une consigne d'environnement.
- **Règle**: une contrainte d'environnement notée dans la doc est une observation datée, pas une
  loi : la revérifier à chaque session avant d'en déduire un plan de travail.

### 2026-09-09 Regex courtes sans frontière de mot
- **Erreur**: `^900` capturait `9000`, `^MX-? ?3` capturait `MX-30`, `^C2` capturait `C25`,
  `^ASTRA` capturait `ASTRAVAN` → `MappingError` sur 25 684 lignes réelles ; puis, en ajoutant
  des fourre-tout, `PUNTO`, `RX-7`, `CALIBRA`, `VX220` sont entrés en conflit avec des cibles —
  exactement la leçon du 2026-09-08.
- **Correction**: `\b` après tout libellé numérique ou court ; relire `target_models.csv` avant
  d'étendre un fourre-tout ; lancer `tests/test_normalize.py` (qui itère sur toutes les cibles)
  après chaque édition de `models.csv`.
- **Règle**: une règle de mapping se teste d'abord contre la liste réelle des libellés
  (`reports/<date>/silver/labels_target_makes.csv`), pas contre des exemples choisis.
