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
