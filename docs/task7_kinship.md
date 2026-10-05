# Kinship & Cousin Relationship Engine

Notebook: `notebooks/03_kinship_engine.ipynb`

## How to run

Run after Task 6, because the notebook reads its cleaned files from `data/staging`:
`hf_persons_clean.parquet`, `hf_memberships_clean.parquet`, `openhalalan_winners_clean.parquet`, `roster_legislators_clean.parquet`.

Open the notebook and click **Run All**. It takes about 2 minutes and writes 7 parquet files to `data/staging`.

## Method

Filipino naming convention:

- **Last name** = father's family (for married women: the husband's family)
- **Middle name** = mother's maiden surname (for married women: their own birth family)

So two people with the same last **and** middle name are usually siblings, or a mother and her child. Someone whose middle name is another person's last name usually has a mother from that family. This is the same name logic used in the family-network study cited in the README (Cruz, Labonne & Querubin 2017, openICPSR 113048).

People are only compared within the same province (or historical province for old roster rows), because surnames repeat across the country.

## Steps

| Step | What it does |
|---|---|
| 1 | Name keys, suffixes (JR, SR, II, III, IV), and middle names. Fixes surname prefixes that OpenHalalan stored as middle names ("PENA, RENE DE LA" is really DE LA PENA, 440 rows), and keeps only the surname part of multi-word middle names ("THOMAS GONI" -> GONI, 6,490 rows) |
| 2 | Links HF membership rows to OpenHalalan rows of the same mandate (same year, position, province, name). One-to-one matches only. 77,828 of 86,234 HF rows (90.3%) |
| 3 | Gives every OpenHalalan row a person ID: the linked HF person, or the only HF person with the same name and province, or a new OH person |
| 4 | Links modern House members in the roster (2001+) to existing people; older legislators become new RL people. Builds the `politicians` and `politician_terms` tables |
| 5 | Keeps only middle names that are surnames. Removes first names (used as a first name as often as or more than as a surname, e.g. DOMINGO, FRANCISCO), job titles typed into the field (MAYOR, VICE-MAYOR), and two-letter initials that are not known surnames (UY, GO, TY are kept) |
| 6 | Chance test for common surnames (see below) |
| 7 | Kinship rules (see below) |
| 8 | One link per pair (strongest rule wins), and removes pairs that are probably one person under two IDs |
| 9 | Kinship network, clans, and alliances between clans |
| 10 | Spot-check of known families |
| 11 | Saves the outputs |

## Chance test (Step 6)

Two unrelated SANTOS councilors in Bulacan are normal, because SANTOS is common there. For every surname, the test asks whether it appears more often in a town (or province) than its share in the rest of the province (or region) would predict. The result is a Poisson p-value; below 0.01 means "more than chance".

Example: ABAD in Batanes (7 found, 0.6 expected) passes; ABAD in Isabela (5 found, 5.8 expected) does not.

## Kinship rules (Step 7)

| Rule | Condition | Likely relationship | Tier |
|---|---|---|---|
| `nuclear_family` | Same last and middle name, same province | Siblings, or mother and child | strong |
| `father_son` | Same full name with a suffix pair (SR/JR, JR/III, none/II, ...) | Father and son | strong |
| `paternal_kin` (town) | Same last name, same town, and passes the town chance test or held the same seat one election after the other | Same father's family | medium |
| `paternal_kin` (provincial office) | Same last name, same province, at least one held a provincial post (governor, vice governor, board member, House, senator), surname passes the province test and is at least 5x more common than expected | Same father's family | medium |
| `paternal_kin` (province) | Same last name, same province, passes the province chance test | Same father's family, less certain | weak |
| `maternal_kin` | A's middle name is B's last name (skipped when A's middle name equals A's own last name) | A's mother is from B's family | medium (same town) / weak (same province) |
| `maternal_cousin` | Same middle name, different last names, same town | Mothers from the same family; possible first cousins | weak |

Weights for network analysis: strong 1.0, medium 0.7, weak 0.4.

## Clans and alliances (Step 9)

- **Clan** = a paternal family: people connected by `nuclear_family`, `father_son`, or `paternal_kin` links of strong or medium tier.
- **Alliance** = a medium `maternal_kin` link between two different clans (intermarriage between families).
- Weak links stay in `kinship_edges` but do not form clans.

## Outputs

All in `data/staging`. Read with `pd.read_parquet(...)`.

| File | Rows | Contents |
|---|---|---|
| `politicians.parquet` | 86,849 | One row per person (HF 45,424 / OH 38,981 / RL 2,444), 1907-2025 |
| `politician_terms.parquet` | 248,685 | One row per term served, all sources |
| `kinship_edges.parquet` | 206,652 | One row per related pair |
| `person_duplicates.parquet` | 3,686 | Pairs that are probably one person under two IDs |
| `clans.parquet` | 16,481 | One row per clan |
| `clan_alliances.parquet` | 1,649 | Pairs of clans joined by maternal links |
| `surname_concentration.parquet` | 88,956 | Chance test result per province/town and surname |

### Key columns

**politicians**: `person_uid` (HF-, OH-, RL- prefix), `display_name`, `last_key`, `middle_key`, `middle_status`, `sex`, `home_place`, `home_town`, `first_year`, `last_year`, `positions`, `clan_id`, `clan_size`, `n_relatives`, `has_relative_in_office`

**politician_terms**: `person_uid`, `source`, `year`, `end_year` (roster only), `position`, `province_std`, `town_std`, `is_primary`

`is_primary` makes sure each mandate is counted once: HF for 2004-2016, OpenHalalan for 2001, 2019-2025 and national posts, roster for House terms before 2001. **Always filter `is_primary == True` when counting officials.**

**kinship_edges**: `person_a`, `person_b`, `relation`, `tier`, `weight`, `relation_hint`, `all_relations` (every rule that matched), `p_value`, `succession` (held the same seat one after the other), `place`, `same_town`, `year_gap` (0 = careers overlapped)

## Results

| | Count |
|---|---|
| Strong/medium links | 100,290 |
| Clans | 16,481 |
| People in a clan | 52,160 of 86,849 (60%) |
| People with at least one relative in office | 56,004 (64%) |
| Same-seat successions within a family | 3,802 |

Largest clans: AMPATUAN (Maguindanao, 98), SINSUAT (Maguindanao, 49), MIDTIMBANG (Maguindanao, 46), BALINDONG (Lanao del Sur, 43), SISON (Pangasinan, 39, since 1912).

## Validation

| Family | Province | People | In one clan? |
|---|---|---|---|
| AMPATUAN | Maguindanao | 98 | Yes |
| ORTEGA | La Union | 34 | Yes (since 1934) |
| ABAD | Batanes | 7 | Yes (since 1949) |
| MARCOS | Ilocos Norte | 17 | Yes |
| ECLEO | Dinagat Islands | 37 | Yes |
| SINGSON | Ilocos Sur | 32 | Yes |
| DY | Isabela | 28 | Yes |
| ROMUALDEZ | Leyte | 18 | Yes |

The duplicate check catches the split ID noted in Task 6 (Lissa / Lissa Marie Streegan) and spelling variants such as STO TOMAS / STO. TOMAS.

## Known limitations

- Names only: the engine finds **likely** relatives, not confirmed ones. `paternal_kin` cannot tell siblings, cousins, a parent, or a spouse apart.
- Married women carry their husband's surname, so they join the husband's clan; their birth family appears through `maternal_kin`.
- Middle names that are also common first names are dropped (6,855 people), so some real maternal links are missed. This avoids many false links.
- A father and son with the same name, no suffix, and no middle name can be flagged as one person (`person_duplicates`).
- Nicknames are not matched (e.g. HENEDINA / DINA ABAD stay two people, but both are in the Abad clan).
- HF sometimes merges two people into one ID (some IDs hold two different posts in the same year); this cannot be split from names alone.
- Senators and presidents with no provincial or local post have no province, so they are only linked if they held another post.
- Pre-1987 roster rows use historical province names when there is no current equivalent.
- Not yet validated against Wikidata family relations (`WIKIDATA_SPARQL_URL`); this could be added later.

