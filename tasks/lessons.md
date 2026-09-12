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

### 2026-09-09 Une finition peut contenir le nom d'une version sportive
- **Erreur**: `\bST\b` acceptait `ST-LINE`, `.*16 ?V` acceptait `DYNAMIQUE 16V`, `VTR` était
  rangé avec `VTS` : des millions de véhicules ordinaires comptés comme sportifs, et
  inversement `TYPE-R` (tiret) raté → Civic Type R EP3 = 1 exemplaire.
- **Correction**: lookahead négatif sur les finitions (`(?!-?LINE)`), séparateur variable
  (`[- ]?`), versions inférieures rangées dans le fourre-tout ; test paramétré sur les libellés
  réels du premier export.
- **Règle**: pour chaque cible, lire les 5 plus gros libellés mappés **et** les libellés qui
  contiennent le mot-clé mais sont mappés ailleurs (`reports/<date>/silver/labels_target_makes.csv`)
  avant de considérer une règle comme juste ; l'année d'immatriculation n'est pas l'année
  de fabrication pour un import.

### 2026-09-12 Une sémantique documentée mais non implémentée
- **Erreur**: `docs/methodology.md` §1 affirmait « le libellé prime quand il porte lui-même la
  génération » (`M3 CSL`, `LANCER EVO VI`), mais `normalize.apply` traitait toutes les règles
  qui matchent à égalité. Résultat : `MappingError` sur 264 lignes au premier run post-PR #7.
  Les regex avaient tenté de compenser par un lookahead `(?!\s+(I|II|...))` que le backtracking
  de `.*` désamorce (`LANCER.*(EVO|EVOLUTION)` s'arrête sur `LANCER EVO`, le lookahead voit
  `LUTION V` et passe).
- **Correction**: implémenter la précédence une fois dans le code (règle sans plage d'années
  **portant une génération** > règle à plage), plutôt que de rustiner chaque regex.
- **Règle**: toute règle de priorité écrite dans la doc doit avoir un test qui la vérifie ; si
  elle n'est pas dans le code, elle n'existe pas. Et un lookahead placé après un `.*` ne protège
  de rien : ancrer ou restructurer, ne jamais compter sur l'ordre de matching.

### 2026-09-12 Une gate verte ne prouve pas que le run a tourné
- **Erreur**: la couverture annoncée par la PR #7 (GB 99,0 %) n'avait jamais été produite par un
  run complet ; le seul bundle committé datait d'avant la PR et portait encore ses bugs.
- **Correction**: ne considérer un correctif comme validé qu'après un `make export` dont le
  `manifest.json` porte le sha du commit corrigé.
- **Règle**: un `reports/<date>/` dont `git.sha` est antérieur au correctif n'est pas une preuve
  du correctif — c'est la preuve de ce qui le précède. Vérifier `git.sha` avant de s'en servir.

### 2026-09-12 Les branches ouvertes font partie de l'état initial
- **Erreur**: l'état du projet a été déduit de `tasks/todo.md` et de l'absence de `site/` sur
  disque. Conclusion tirée : « l'étape 5 reste à écrire », et une question posée à l'utilisateur
  pour *choisir un générateur de site*. En réalité quatre branches distantes non fusionnées
  portaient déjà les 4 items non cochés de la phase 1, dont **deux implémentations complètes**
  du site (Jinja2 et Astro) et un `tasks/handoff.md` où la décision de fusion était déjà prise
  avec l'utilisateur. Sans la vérification, la session aurait réécrit du travail relu et livré
  un troisième générateur.
- **Correction**: `git fetch --prune && git branch -r -v` et `gh pr list --state open` avant de
  planifier ; lire le dernier commit de chaque branche en avance sur `main` ; tester les
  conflits avec `git merge-tree --write-tree main origin/<branche>` (lecture seule) pour
  mesurer le coût réel d'une fusion au lieu de le supposer.
- **Règle**: une case non cochée dans `tasks/todo.md` signifie « pas sur `main` », **pas**
  « personne ne l'a fait ». L'état initial d'une session, c'est `main` **plus les branches
  distantes** — et un fichier de passation (`handoff.md`, `next.md`) peut contenir une décision
  déjà arrêtée qu'il serait absurde de reprendre à zéro. Corollaire : ne pas multiplier les
  fichiers de reprise, ils se périment et finissent par se contredire ; un seul `todo.md`.
