# Sources de données — URLs vérifiées et licences

| Source | Pays | Licence | Point d'entrée | Vérifié le | Statut |
|---|---|---|---|---|---|
| DfT / DVLA vehicle licensing statistics (VEH0120, VEH0124, VEH0160) | GB | [OGL v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) | https://www.gov.uk/government/statistical-data-sets/vehicle-licensing-statistics-data-files | — | URL des CSV résolue à la volée depuis la page ; **à vérifier par HTTP** (gov.uk inaccessible depuis l'environnement de dev initial) |
| RDW Gekentekende voertuigen (`m9d7-ebf2`) | NL | CC0 1.0 | https://opendata.rdw.nl/resource/m9d7-ebf2.json | — | Phase 1 étape 2 |
| KBA FZ 10 / FZ 17 | DE | DL-DE/BY-2-0 | https://www.kba.de/DE/Statistik/Fahrzeuge/Bestand/bestand_node.html | — | Phase 2, URLs XLSX à inventorier |
| SDES / data.gouv.fr immatriculations neuves | FR | Licence Ouverte 2.0 | https://www.data.gouv.fr | — | Phase 2, jeu exact à identifier |

Règle (SPEC §9) : toute URL incertaine est vérifiée par requête HTTP et l'URL finale consignée
ici avec la date. Le schéma observé de chaque source est documenté dans `docs/sources/<source>.md`.
