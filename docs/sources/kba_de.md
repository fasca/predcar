# DE — KBA, Fahrzeugzulassungen FZ 2 (parc au 1ᵉʳ janvier)

**Statut : schéma observé sur les 8 classeurs réels 2019 → 2026, le 2026-09-13.** Licence
[DL-DE/BY-2-0](https://www.govdata.de/dl-de/by-2-0). Toute divergence future lève
`KbaSchemaError` plutôt que de produire de faux chiffres.

## 1. Quelle table, et pourquoi pas celle de la spec

`docs/SPEC.md` §2.3 annonçait « FZ 10 / FZ 17 ». Vérifié par requête HTTP :

| Table | Réalité |
|---|---|
| **FZ 10** | **n'existe pas** — 404 sur les 17 millésimes testés |
| FZ 17 | existe, mais au niveau **marque** seulement (≤ 140 lignes) : inutilisable ici |
| **FZ 2**, feuille **FZ 2.2** | la bonne table : parc par **constructeur et nom commercial**, ~16 600 lignes |

FZ 2.2 = « Bestand an Personenkraftwagen nach Herstellern, Handelsnamen und ausgewählten
Merkmalen ». C'est l'équivalent allemand du couple `GenModel` / `Model` du DfT.

**Elle ne porte aucune année de première immatriculation** : ni cohortes, ni générations.
L'Allemagne est donc une série de **niveau modèle générique**, comme VEH0120.

## 2. URLs et millésimes

Le nom de fichier a changé de convention en cours de route ; les deux sont déclarés dans
`config/sources.yaml` et essayés dans l'ordre.

| Millésimes | Motif |
|---|---|
| 2021 → 2026 | `…/Fahrzeuge/FZ2/fz2_<AAAA>.xlsx?__blob=publicationFile` |
| 2019 → 2020 | `…/Fahrzeuge/FZ2/fz2_<AAAA>_xlsx.xlsx?__blob=publicationFile` |

Base : `https://www.kba.de/SharedDocs/Downloads/DE/Statistik/Fahrzeuge/FZ2`. Rien avant 2019
sous ces deux formes. Un classeur pèse ~4 à 5 Mo. La période d'une observation est le
**1ᵉʳ janvier** du millésime, pas la date de téléchargement.

## 3. Layout observé

Feuille `FZ 2.2`, huit colonnes utiles, données à partir de la 10ᵉ ligne du classeur :

`Hersteller | Handelsname | Typ-Schl.-Nr. | kW | Kraftstoffart | Allrad | Aufbauart | Insgesamt`

Puis un bloc « Und zwar » (dont : camping-cars, détenteurs privés, tranches d'âge des
détenteurs) que nous n'utilisons pas. `Insgesamt` est le comptage retenu.

Le parseur **ne présume aucune position** : il cherche les libellés `Hersteller`,
`Handelsname` et `Insgesamt` dans les 15 premières lignes, puis prend la première ligne dont
`Insgesamt` est un entier.

## 4. Les pièges, tous rencontrés sur les fichiers réels

1. **La ligne d'en-tête bouge et se scinde.** En 2019–2021, `Insgesamt` est une ligne
   **au-dessus** de `Hersteller` ; à partir de 2022, tout est sur la même ligne. Les libellés
   ont aussi été réécrits en écriture inclusive (`private Halter` → `private Halterinnen und
   Halter`). 2019 a 15 colonnes là où les autres en ont 14.
2. **`Hersteller` et `Handelsname` ne sont écrits qu'au premier rang de leur groupe.** Sans
   report en avant, 99 % des lignes perdent leur identité.
3. **Le report ne doit jamais franchir une frontière de constructeur.** Un constructeur peut
   s'ouvrir sur des lignes sans nom commercial : dans le fichier 2019, le bloc Audi commence
   ainsi juste après Aston Martin, et un report global créditait des Audi à une Aston Martin.
   Ces lignes sans nom deviennent `(MISSING)` — elles ne sont jamais supprimées.
4. **Deux niveaux de totaux, de forme variable.** `INSGESAMT` (parc entier) et `ZUSAMMEN`
   (sous-total par constructeur). Jusqu'en 2024 le sous-total est **collé au constructeur**
   (`VOLKSWAGEN (D) ZUSAMMEN`, nom commercial vide) ; en 2026 il est seul dans la colonne du
   nom commercial. Les garder **doublait le parc allemand** : ~96 M au lieu de ~49 M.
5. **L'orthographe des totaux n'est pas fiable** : le fichier 2019 contient
   `CITROEN (F) ZSAMMEN`, sans le `U`.
6. **Pied de page** : la feuille se termine par `© Kraftfahrt-Bundesamt, Flensburg`.
7. **`Hersteller` est un groupe industriel, pas une marque**, avec un suffixe pays :
   `VOLKSWAGEN (D)`, `MAZDA (B/J/USA/RC)`. Une marque apparaît sous plusieurs entrées, une par
   usine (`HYUNDAI MOTOR (CZ)`, `HYUNDAI (TR)`, `HYUNDAI MOTOR (ROK)`), et certains groupes
   couvrent plusieurs marques cibles : `FCA (I)` (Fiat, Alfa, Lancia), `STELLANTIS (F)` (Corsa,
   208 et C5 Aircross mélangés), `GENERAL MOTORS`, `JAGUAR LAND ROVER`, `MG ROVER`.
8. **Un nom commercial peut en contenir plusieurs**, séparés par une virgule :
   `COOPER,MINI`, `COOPER S CABRIO,COOPER S`.
9. **Modèle déclaré inconnu par la source** : `SONSTIGE/NICHT GETYPT` et
   `SONSTIGE HERSTELLER`, l'équivalent du `MODEL MISSING` du DfT.
10. **Marqueurs de suppression** — la feuille publie sa légende : `0` (plus que rien mais moins
    d'une demi-unité), `-` (rien), `.` (inconnu ou confidentiel), `/` (peu sûr), `( )` (portée
    limitée), `X` (sans objet), `r` (corrigé), `p` (provisoire). Ils n'apparaissent **pas** dans
    `Insgesamt` sur les millésimes observés, mais une ligne sans comptage entier est écartée et
    journalisée, jamais imputée à 0.

## 5. L'invariant de somme, et les millésimes qu'il refuse

La feuille publie son propre total. Les lignes de détail sont comparées à lui, de façon
**asymétrique** :

- **au-dessus** du total → `KbaSchemaError` : une ligne d'agrégat a été comptée deux fois,
  c'est toujours un défaut de parseur (tolérance 0,1 %) ;
- **en dessous** → attendu : le KBA supprime les petits comptages (`.`) tout en les additionnant
  dans le total. Journalisé, et refusé seulement au-delà de 2 %.

C'est ce contrôle qui a révélé les pièges 3, 4 et 5 — aucun n'était visible autrement.

| Millésime | Total déclaré | Écart après parsing |
|---|---|---|
| 2019 | 47 095 784 | +6 571 (+0,014 %) |
| 2020 | 47 715 977 | **0** |
| 2021 | 48 248 584 | −25 266 (−0,05 %) |
| 2022 | 48 540 878 | **0** |
| 2023 | 48 763 036 | **0** |
| 2024 | 49 098 685 | **0** |
| 2025 | 49 339 166 | **0** |
| 2026 | 49 486 487 | −152 799 (−0,31 %, comptages supprimés) |

**Les huit millésimes 2019 → 2026 sont exploitables**, dont cinq au véhicule près. La série
allemande est annuelle et **sans trou**.

Y arriver a demandé de comprendre deux formes d'agrégat que le contrôle de somme signalait
sans les nommer :

- **une ligne de sous-total publiée sans son libellé** (2019, 3 124 094 véhicules : le total
  d'Audi). Elle se reconnaît à ceci qu'elle porte un comptage mais **ni libellé ni colonne
  technique** — une vraie ligne de véhicule a toujours un Typ-Schl.-Nr., une puissance ou un
  carburant. Critère vérifié sur les huit millésimes : une seule ligne concernée, aucun faux
  positif ;
- **une deuxième orthographe fautive** : `HYUNDAI MOTOR (ROK) ZUSAMMEM`, avec un `M` final
  (2021 et 2022), après le `ZSAMMEN` sans `U` de 2019.

Aucune tolérance n'a été assouplie pour y parvenir.

## 6. Vers le silver

| Colonne silver | Source |
|---|---|
| `country` | `DE` |
| `period` | 1ᵉʳ janvier du millésime |
| `make_raw` | `Hersteller`, en majuscules, **jamais modifié** (le suffixe pays est traité par `mapping/makes.csv`) |
| `model_raw` | `Handelsname`, en majuscules, ou `(MISSING)` |
| `model_gen_raw` | null — la source n'a pas de niveau modèle générique |
| `year_first_reg`, `year_manufacture`, `status` | null — la source ne les porte pas |
| `count` | `Insgesamt`, sommé sur les variantes (Typ-Schl.-Nr. × kW × carburant × carrosserie) |

Une ligne par `(make_raw, model_raw)`.

## 7. Liste de vérification (observée le 2026-09-13)

- [x] URLs des 8 millésimes vérifiées par requête HTTP, deux conventions de nommage
- [x] FZ 10 confirmé inexistant, FZ 17 confirmé au niveau marque seulement
- [x] Ligne d'en-tête localisée dynamiquement, deux dispositions observées (2019–2021 / 2022+)
- [x] Report des libellés de groupe, borné au constructeur
- [x] Totaux `INSGESAMT` / `ZUSAMMEN` exclus dans leurs deux formes, coquille `ZSAMMEN` comprise
- [x] Pied de page `©` exclu
- [x] Somme des lignes vérifiée contre le total publié, sur les 8 millésimes, tous exploitables
- [x] Aucune donnée personnelle : la table est agrégée à la source
- [x] Mapping : alias de constructeurs, `SONSTIGE/NICHT GETYPT` déclaré « modèle inconnu »,
      fourre-tout étendus aux libellés allemands → **DE 98,9 %**, la gate commune s'applique
      de nouveau (plus d'exemption dans `config/mapping.yaml`)
- [x] MINI (sous BMW) et Smart (sous Daimler) : la colonne `model_regex` de `mapping/makes.csv`
      réassigne la marque depuis le nom commercial → 5,1 M de véhicules rendus à leur marque,
      **DE 98,9 %** (`docs/mapping.md`)
- [ ] Groupes multi-marques `FCA (I)` / `STELLANTIS (F)` / `GENERAL MOTORS` / `JAGUAR LAND ROVER` :
      même mécanisme, règles à écrire
