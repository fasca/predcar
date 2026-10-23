# Intervention ChatGPT — version 1.0.1

Date : 18 septembre 2026
Auteur de l'intervention : ChatGPT (Codex)

## Objet

Audit puis correction de l'application predcar, de son pipeline de données, de son site
statique et de ses workflows GitHub Actions.

## Corrections réalisées

- Le refresh trimestriel rejoue tous les snapshots RDW archivés au lieu de ne conserver que
  le dernier, et télécharge puis ingère tous les millésimes KBA déclarés dans la configuration.
- Chaque snapshot RDW versionne désormais son payload compressé et son `query.json`, tous deux
  requis pour reconstruire les données. Le manifeste RDW orphelin du 12 septembre 2026 a été
  retiré de `data/raw/` ; il reste consultable dans les anciens rapports et l'historique Git.
- Le déploiement GitHub Pages reçoit explicitement le SHA créé par le refresh, afin de publier
  le nouveau bundle plutôt que le commit qui avait initialement déclenché le workflow.
- Le ratio SORN conserve le niveau génération lorsqu'une série a déjà fourni ce statut, même
  si la dernière observation vaut zéro.
- L'âge d'un point d'inflexion est calculé avec l'année d'observation du même pays. Un snapshot
  néerlandais plus récent ne vieillit donc plus artificiellement une inflexion britannique.
- Les chiffres allemands sont décrits comme le parc du modèle complet, sans attribution à une
  génération précise.
- Le tableau des composantes du score reste contenu dans la fiche modèle sur petit écran.
- Un bundle de preuves corrigé a été produit dans `reports/2026-09-18/`.

## Tests et contrôles

- 294 tests Python réussis.
- Ruff : lint et formatage réussis.
- Pipeline de score : 261 cibles avec données, 249 scores publiés.
- Site statique : 264 pages générées, aucun lien interne cassé et flux Atom valide.
- Contrôle Chrome à 390 px : aucun débordement sur l'accueil ou la fiche modèle.
- Filtres, tri et trois graphiques Plotly vérifiés sans erreur JavaScript.

## Livraison

Ces changements constituent la version corrective `v1.0.1`. Le commit et le tag sont créés
localement ; leur envoi vers le dépôt distant reste une opération séparée.
