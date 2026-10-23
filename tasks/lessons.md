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

### 2026-09-13 Les tests se relancent *après* `make export`, pas avant
- **Erreur**: la suite était verte en local, la CI rouge. `tests/test_real_labels.py` rejoue la
  gate de couverture sur les libellés du **dernier bundle** : tant que `make export` n'avait pas
  tourné, il lisait le bundle de la veille, sans l'Allemagne. L'export a ajouté 110 044 libellés
  dont les allemands à 93,1 %, et le test — qui codait le seuil 0,95 en dur — a échoué, alors que
  `config/mapping.yaml` exempte explicitement DE.
- **Correction**: relancer `pytest` **après** `make export`, dans cet ordre (c'est déjà ce que
  fait `.github/workflows/refresh.yml`) ; et faire lire aux tests le seuil réel
  (`cfg.coverage_threshold(country)`) au lieu d'une constante.
- **Règle**: quand un bundle versionné est une **entrée** de la suite de tests, modifier le
  bundle est une modification du code sous test. Séquence : pipeline → `export` → `pytest` →
  commit. Corollaire : un seuil qui existe dans la config ne doit jamais être réécrit en dur
  dans un test, sinon les deux divergent au premier cas particulier — et c'est le test qui a
  raison contre le code, ou l'inverse, sans qu'on sache lequel.

### 2026-09-13 Étendre un fourre-tout, c'est risquer d'en retirer une alternative
- **Erreur**: en ajoutant les variantes espacées de la gamme Volvo (`V 70`, `S 60`) au fourre-tout,
  j'ai réécrit son alternance `(40|50|70|80|90)` en `(40|50|90)` et **perdu `S70`** au passage.
  Résultat invisible côté allemand — la couverture DE montait quand même — mais **255 861
  véhicules britanniques** cessaient d'être mappés. Repéré en comparant le compte GB au
  véhicule près avant/après, pas par les tests : la couverture GB restait à « 99,0 % » arrondie.
- **Correction**: comparer les **comptes absolus** de chaque pays avant et après toute édition de
  `mapping/models.csv`, pas seulement le pourcentage affiché ; et préférer *ajouter* une
  alternative à *réécrire* une alternance existante.
- **Règle**: une modification de mapping destinée à un pays doit laisser les autres **identiques
  au véhicule près**. Un pourcentage arrondi cache une régression de plusieurs centaines de
  milliers de lignes. Corollaire : quand un modèle a déjà sa règle propre (`^S60`, `^V70`, parce
  qu'il existe une version `R`), c'est **cette** règle qu'on étend — un fourre-tout concurrent
  lèverait `MappingError` ou, pire, changerait silencieusement le `model_gen`.

### 2026-09-15 La règle d'un modèle de base avale ses versions recherchées
- **Erreur**: `^ESCORT(?!.*COSWORTH)` envoyait `ESCORT RS TURBO`, `RS2000` et `XR3I` dans
  « Escort » ; `^INTEGRA(?!.*TYPE R)` ratait `INTEGRA R`, l'appellation britannique de la DC2 ;
  `^106.*(RALLYE|GTI)` faisait de la 106 GTI une Rallye ; `^COUPE` avalait la `COUPE S2`. Quatre
  cibles existantes en étaient invisibles ou fausses depuis le premier run. Rien ne l'a
  signalé : la couverture était à 99 % et chaque libellé était « mappé » — à un mauvais modèle.
- **Correction**: c'est `predcar candidates` qui l'a révélé, à l'envers : la « perte » d'un modèle
  de base était gonflée par ses versions sportives. Lire les libellés réels sous chaque
  candidat avant de l'ajouter, et chercher les versions connues (RS, GTI, Turbo, 16V, XR, GSi,
  T5) sous les règles de base des marques cibles.
- **Règle**: une règle de modèle de base doit **exclure explicitement chaque mot-clé de
  version** que le libellé peut porter, et chaque version exclue doit avoir sa règle — sinon
  elle disparaît sans erreur. Corollaire : une cible dont le parc est anormalement bas (S2 à 0,
  DC2 à 2) n'est pas « rare », elle est **mal mappée** ; vérifier ses libellés avant de croire
  le chiffre. Et l'inverse d'une finition sportive (leçon du 2026-09-09) existe aussi : un
  libellé peut porter un mot-clé sans le mot « TYPE » (`INTEGRA R`).

### 2026-09-18 Un refresh doit repartir uniquement des entrées versionnées
- **Erreur**: le refresh trimestriel ne relisait que le snapshot RDW du jour et omettait KBA ;
  `query.json`, pourtant requis à l'ingestion, n'était pas committé. Le workflow Pages appelé
  après le push pouvait en plus reconstruire le SHA initial du run.
- **Correction**: archiver les deux entrées RDW, rejouer tous les mois disponibles, télécharger
  et ingérer tous les millésimes KBA, puis transmettre explicitement le SHA créé à Pages.
- **Règle**: tester un workflow de reconstruction depuis un checkout propre. Tout fichier exigé
  par un parseur doit être versionné ou retéléchargeable ; tout workflow qui committe puis en
  appelle un autre lui transmet explicitement le commit produit.

### 2026-09-18 Un bundle rejoué sans nouvelles données produit un diff de méthode, pas une alerte
- **Erreur**: le bundle 2026-09-18 (mêmes CSV DfT, même snapshot RDW, âge d'inflexion corrigé)
  a fait publier sur « Évolutions » et dans le flux Atom cinq entrées et cinq sorties du top 50
  comme si le parc avait bougé. Chaque manifest portait pourtant la version et la config.
- **Correction**: `site.method_change` compare version et `score.yaml` / `mapping.yaml` des
  deux manifests ; la page et le flux annoncent un changement de méthode.
- **Règle**: toute sortie qui compare deux runs doit dire si la *méthode* a changé entre eux
  avant de qualifier les écarts. Et un chiffre affiché à côté d'un jugement (« récente »)
  doit permettre de le refaire : l'âge, le seuil et le calendrier vont avec l'année.
