# Sources de données — URLs vérifiées et licences

| Source | Pays | Licence | Point d'entrée | Vérifié le | Statut |
|---|---|---|---|---|---|
| DfT / DVLA vehicle licensing statistics (VEH0120, VEH0124, VEH0160) | GB | [OGL v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) | https://www.gov.uk/government/statistical-data-sets/vehicle-licensing-statistics-data-files | 2026-09-08 | Vérifié : page HTTP 200, 4 CSV résolus et archivés (`assets.publishing.service.gov.uk/media/<id>/df_VEH0120_GB.csv`, `…/df_VEH0124_AM.csv`, `…/df_VEH0124_NZ.csv`, `…/df_VEH0160_GB.csv`, `<id>` change à chaque publication ; la page liste aussi des variantes `_UK` non utilisées). Schéma observé : `docs/sources/dft_uk.md` |
| RDW Gekentekende voertuigen (`m9d7-ebf2`) | NL | CC0 1.0 | https://opendata.rdw.nl/resource/m9d7-ebf2.json | 2026-09-08 | Vérifié : requête agrégée SoQL acceptée, 203 051 lignes (`docs/sources/rdw_nl.md`) |
| KBA FZ 10 / FZ 17 | DE | DL-DE/BY-2-0 | https://www.kba.de/DE/Statistik/Fahrzeuge/Bestand/bestand_node.html | — | Phase 2, URLs XLSX à inventorier |
| SDES / data.gouv.fr immatriculations neuves | FR | Licence Ouverte 2.0 | https://www.data.gouv.fr | — | Phase 2, jeu exact à identifier |

**Archivage.** Les payloads bruts ne sont pas versionnés (taille), à une exception : le RDW est
un *instantané sans historique amont*, donc un mois non conservé ici est définitivement perdu.
Ses snapshots sont committés gzippés (~1,2 Mo/mois) sous `data/raw/nl_rdw/<date>/` ; le manifest
enregistre le sha256 du contenu **décompressé**, donc compresser une archive ne change pas son
identité et `predcar.raw` la relit de façon transparente. Les CSV DfT, eux, restent
re-téléchargeables depuis gov.uk avec tout leur historique. Le workflow
`.github/workflows/rdw-snapshot.yml` fait ça tous les 1ᵉʳ du mois.

Règle (SPEC §9) : toute URL incertaine est vérifiée par requête HTTP et l'URL finale consignée
ici avec la date. Le schéma observé de chaque source est documenté dans `docs/sources/<source>.md`.
