# Sources de données — URLs vérifiées et licences

| Source | Pays | Licence | Point d'entrée | Vérifié le | Statut |
|---|---|---|---|---|---|
| DfT / DVLA vehicle licensing statistics (VEH0120, VEH0124, VEH0160) | GB | [OGL v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) | https://www.gov.uk/government/statistical-data-sets/vehicle-licensing-statistics-data-files | 2026-09-08 | Vérifié : page HTTP 200, 4 CSV résolus et archivés (`assets.publishing.service.gov.uk/media/<id>/df_VEH0120_GB.csv`, `…/df_VEH0124_AM.csv`, `…/df_VEH0124_NZ.csv`, `…/df_VEH0160_GB.csv`, `<id>` change à chaque publication ; la page liste aussi des variantes `_UK` non utilisées). Schéma observé : `docs/sources/dft_uk.md` |
| RDW Gekentekende voertuigen (`m9d7-ebf2`) | NL | CC0 1.0 | https://opendata.rdw.nl/resource/m9d7-ebf2.json | 2026-09-08 | Vérifié : requête agrégée SoQL acceptée, 203 051 lignes (`docs/sources/rdw_nl.md`) |
| KBA **FZ 2** (feuille FZ 2.2) | DE | [DL-DE/BY-2-0](https://www.govdata.de/dl-de/by-2-0) | https://www.kba.de/SharedDocs/Downloads/DE/Statistik/Fahrzeuge/FZ2/fz2_&lt;AAAA&gt;.xlsx?__blob=publicationFile | 2026-09-13 | Vérifié : 8 millésimes 2019–2026, deux conventions de nommage (`fz2_<AAAA>.xlsx` dès 2021, `fz2_<AAAA>_xlsx.xlsx` en 2019–2020). **FZ 10 n'existe pas** (404 sur 17 millésimes) et FZ 17 est au niveau marque seulement : la table utile est FZ 2.2, parc par constructeur et nom commercial. Schéma observé : `docs/sources/kba_de.md` |
| SDES / data.gouv.fr | FR | Licence Ouverte (`fr-lo`) | https://www.data.gouv.fr/datasets/immatriculations-de-vehicules-routiers | 2026-09-14 | **Vérifié : inexploitable ici.** Le seul jeu d'immatriculations du SDES est au niveau **communal** — en-tête réel `COMMUNE_CODE;COMMUNE_NOM;CARBURANT;STATUT_UTILISATEUR;GROUPE;CATEGORIE;IMMAT_2010…IMMAT_2025` : **ni marque, ni modèle**. Aucun autre jeu de data.gouv.fr ne descend au modèle (recherches « immatriculation », « marque modèle », « parc automobile » : seulement des flottes d'organisations). Les données par modèle sont commerciales (AAA Data), donc hors périmètre open data |

**Archivage.** Les payloads bruts ne sont pas versionnés (taille), à une exception : le RDW est
un *instantané sans historique amont*, donc un mois non conservé ici est définitivement perdu.
Ses snapshots sont committés gzippés (~1,2 Mo/mois) sous `data/raw/nl_rdw/<date>/` ; le manifest
enregistre le sha256 du contenu **décompressé**, donc compresser une archive ne change pas son
identité et `predcar.raw` la relit de façon transparente. Les CSV DfT, eux, restent
re-téléchargeables depuis gov.uk avec tout leur historique. Le workflow
`.github/workflows/rdw-snapshot.yml` fait ça tous les 1ᵉʳ du mois.

Règle (SPEC §9) : toute URL incertaine est vérifiée par requête HTTP et l'URL finale consignée
ici avec la date. Le schéma observé de chaque source est documenté dans `docs/sources/<source>.md`.

## Résultats d'enchères (phase 3) — vérifiés le 2026-09-14, écartés

La spec conditionne tout scraping au respect de `robots.txt` et prévient : « fragile, coûteux,
risque légal (CGU, DataDome, RGPD) ». Vérification par requêtes HTTP simples, sans
contournement :

| Site | `robots.txt` | Page de résultats | Constat |
|---|---|---|---|
| Collecting Cars | `Allow: /`, `Crawl-delay: 1`, GPTBot/CCBot interdits | `/for-sale?status=sold` → **403** | protection anti-robot sur les ventes |
| Car & Classic | **403 sur `robots.txt` lui-même** | `/auctions/sold` → 403 | accès automatisé refusé d'emblée |
| Catawiki | **403 sur `robots.txt`** | — | idem |
| Bring a Trailer | `Crawl-delay: 1`, `/search/` interdit | `/auctions/results/` → délai dépassé | injoignable en automatique |
| Aguttes | `User-agent: ClaudeBot → Disallow: /` (Amazonbot, CCBot, Bytespider idem) | — | interdit **nommément** aux robots d'IA |

Aucun de ces sites n'expose d'API ni de jeu de données ouvert. Passer outre un 403 ou une
interdiction explicite reviendrait à contourner une protection : **exclu**, quelle que soit la
valeur des données. La piste est fermée tant que ces sites ne publient pas leurs résultats
autrement.
