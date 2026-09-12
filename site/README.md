# site/ — le site statique predcar

Astro, sans framework client ni bibliothèque de graphiques : les courbes sont du SVG généré au
build, donc le site est lisible sans JavaScript (seuls les filtres du classement en utilisent).

## Construire

```bash
make site        # depuis la racine du dépôt
make site-dev    # serveur local
```

Node 22+. `PREDCAR_SITE` et `PREDCAR_BASE` permettent de construire pour un autre hôte que
GitHub Pages.

## D'où viennent les données

Du **dernier `reports/<date>/gold/` committé** (`src/lib/gold.ts`), jamais de `data/gold/`,
qui est ignoré par git. Conséquences :

- un build ne demande ni réseau, ni `data/`, ni run de pipeline ;
- ce que le site affiche est toujours reproductible depuis le dépôt ;
- la date du bundle est la date de rafraîchissement affichée en pied de page.

Pour publier des chiffres plus récents : `make export`, committer `reports/<date>/`, pousser —
le workflow Pages se déclenche tout seul.

La page méthodologie est rendue depuis `docs/methodology.md` : une seule source de vérité.
