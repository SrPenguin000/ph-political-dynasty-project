# Kinship & Cousin Relationship Engine

Notebook: `notebooks/03_kinship_engine.ipynb`

## How to run

Run after Task 6, because the notebook reads its cleaned files from `data/staging`:
`hf_persons_clean.parquet`, `hf_memberships_clean.parquet`, `openhalalan_winners_clean.parquet`, `roster_legislators_clean.parquet`, `ateneo_politicians_clean.parquet`.

Open the notebook and click **Run All**. It takes a few minutes and writes 7 parquet files to `data/staging`.

## Data sources

| Source | Years used | What it adds |
|---|---|---|
| HF (Humanitarian Data Exchange) | 2004-2016 | Local, provincial and House officials |
| OpenHalalan | 2001, 2019-2025 | Local, provincial, House and national officials |
| Roster of legislators | 1907-2025 | House members, including the old Congress |
| Ateneo Policy Center Political Dynasties Dataset 2022 (cleaned in Task 6) | 1988-1998 | Local and provincial officials before 2001 (House rows come from the roster instead) |

Ateneo also covers 2001-2022, but those years are already in HF and OpenHalalan, so we only take 1988-1998 from it. We use its 2001-2022 rows to check our results (Step 12).

## Method

Filipino naming convention:

- **Last name** = father's family (for married women: the husband's family)
- **Middle name** = mother's maiden surname (for married women: their own birth family)

So two people with the same last **and** middle name are usually siblings, or a mother and her child. Someone whose middle name is another person's last name usually has a mother from that family. This is the same name logic used in the family-network study cited in the README (Cruz, Labonne & Querubin 2017, openICPSR 113048).

People are only compared within the same province (or historical province for old roster rows), because surnames repeat across the country.

## Steps

| Step | What it does |
|---|---|
| 1 | Name keys, suffixes (JR, SR, II, III, IV), and middle names. Fixes surname prefixes that OpenHalalan stored as middle names ("PENA, RENE DE LA" is really DE LA PENA, 440 rows), and keeps only the surname part of multi-word middle names ("THOMAS GONI" -> GONI, 6,490 rows). Loads 67,484 Ateneo rows (1988-1998, local and provincial posts, without the rows Task 6 marked as duplicates) |
| 2 | Links HF membership rows to OpenHalalan rows of the same mandate (same year, position, province, name). One-to-one matches only. 77,829 of 86,234 HF rows (90.3%) |
| 3 | Gives every OpenHalalan row a person ID: the linked HF person, or the only HF person with the same name and province, or a new OH person |
| 4 | Links modern House members in the roster (2001+) to existing people; older legislators become new RL people. Links Ateneo rows to the only existing person with the same name in the same province group (24,180 rows); the rest become new AT people (43,304 rows). Builds the `politicians` and `politician_terms` tables |
| 5 | Keeps only middle names that are surnames. Removes first names (used as a first name as often as or more than as a surname, e.g. DOMINGO, FRANCISCO), job titles typed into the field (MAYOR, VICE-MAYOR), and two-letter initials that are not known surnames (UY, GO, TY are kept) |
| 6 | Chance test for common surnames (see below) |
| 7 | Kinship rules (see below) |
| 8 | One link per pair (strongest rule wins), and removes pairs that are probably one person under two IDs |
| 9 | Kinship network, clans, and alliances between clans |
| 10 | Spot-check of known families |
| 11 | Saves the outputs |
| 12 | Compares our results with Ateneo's "fat dynasty" labels |

The Ateneo linking in Step 4 uses `province_group` from Task 6, so a person is followed across a province split. For example, a mayor listed under LEYTE in 1988 and under BILIRAN (created in 1992) in 2004 gets one person ID.

## Chance test (Step 6)

Two unrelated SANTOS councilors in Bulacan are normal, because SANTOS is common there. For every surname, the test asks whether it appears more often in a town (or province) than its share in the rest of the province (or region) would predict. The result is a Poisson p-value; below 0.01 means "more than chance".

Example: ABAD in Batanes (7 found, 0.7 expected) passes; ABAD in Isabela (6 found, 5.7 expected) does not.

## Kinship rules (Step 7)

| Rule | Condition | Likely relationship | Tier |
|---|---|---|---|
| `nuclear_family` | Same last and middle name, same province | Siblings, or mother and child | strong |
| `father_son` | Same full name with a suffix pair (SR/JR, JR/III, none/II, ...) | Father and son | strong |
| `paternal_kin` (town) | Same last name, same town, and passes the town chance test or held the same seat one election after the other | Same father's family | medium |
| `paternal_kin` (provincial office) | Same last name, same province, at least one held a provincial post (governor, vice governor, board member, House, senator), surname passes the province test and is at least 7x more common than expected | Same father's family | medium |
| `paternal_kin` (province) | Same last name, same province, passes the province chance test | Same father's family, less certain | weak |
| `maternal_kin` | A's middle name is B's last name (skipped when A's middle name equals A's own last name) | A's mother is from B's family | medium (same town) / weak (same province) |
| `maternal_cousin` | Same middle name, different last names, same town | Mothers from the same family; possible first cousins | weak |

Weights for network analysis: strong 1.0, medium 0.7, weak 0.4.

The provincial-office rule uses 7x (it was 5x before the Ateneo data was added). With the extra 1988-1998 officials, CRUZ in Bulacan reached 5.1x and would have joined 75 unrelated Cruzes into one clan. At 7x, only surnames that are clearly concentrated in a province pass.

## Clans and alliances (Step 9)

- **Clan** = a paternal family: people connected by `nuclear_family`, `father_son`, or `paternal_kin` links of strong or medium tier.
- **Alliance** = a medium `maternal_kin` link between two different clans (intermarriage between families).
- Weak links stay in `kinship_edges` but do not form clans.
- Clan numbers are fixed: clans are sorted by size, then by their first member ID, so `CLAN-00001` is always the same clan on every run.

## Outputs

All in `data/staging`. Read with `pd.read_parquet(...)`.

| File | Rows | Contents |
|---|---|---|
| `politicians.parquet` | 115,954 | One row per person (HF 44,106 / OH 39,107 / AT 30,298 / RL 2,443), 1907-2025 |
| `politician_terms.parquet` | 316,169 | One row per term served, all sources |
| `kinship_edges.parquet` | 288,180 | One row per related pair |
| `person_duplicates.parquet` | 4,724 | Pairs that are probably one person under two IDs |
| `clans.parquet` | 20,394 | One row per clan |
| `clan_alliances.parquet` | 2,274 | Pairs of clans joined by maternal links |
| `surname_concentration.parquet` | 121,666 | Chance test result per province/town and surname |

### Key columns

**politicians**: `person_uid` (HF-, OH-, AT-, RL- prefix), `display_name`, `last_key`, `middle_key`, `middle_status`, `sex`, `home_place`, `home_town`, `first_year`, `last_year`, `positions`, `clan_id`, `clan_size`, `n_relatives`, `has_relative_in_office`

**politician_terms**: `person_uid`, `source`, `source_row_id` (for Ateneo rows, the `ateneo_row_id` from Task 6), `year`, `end_year` (roster only), `position`, `province_std`, `town_std`, `is_primary`

`is_primary` makes sure each mandate is counted once: Ateneo for local and provincial posts 1988-1998, HF for 2004-2016, OpenHalalan for 2001, 2019-2025 and national posts, roster for House terms before 2001. **Always filter `is_primary == True` when counting officials.**

**kinship_edges**: `person_a`, `person_b`, `relation`, `tier`, `weight`, `relation_hint`, `all_relations` (every rule that matched), `p_value`, `succession` (held the same seat one after the other), `place`, `same_town`, `year_gap` (0 = careers overlapped)

## Results

| | Count |
|---|---|
| Strong/medium links | 132,940 |
| Clans | 20,394 |
| People in a clan | 65,988 of 115,954 (57%) |
| People with at least one relative in office | 70,497 (61%) |
| Same-seat successions within a family | 3,887 |
| Alliances between clans | 2,274 |

Largest clans: AMPATUAN (Maguindanao, 103, since 1992), SINSUAT (Maguindanao, 58, since 1988), BALINDONG (Lanao del Sur, 55), MIDTIMBANG (Maguindanao, 52), SISON (Pangasinan, 49, since 1912).

## Validation

### Known families

| Family | Province | People | In one clan? |
|---|---|---|---|
| AMPATUAN | Maguindanao | 103 | Yes |
| ORTEGA | La Union | 37 | Yes (since 1934) |
| ABAD | Batanes | 7 | Yes (since 1949) |
| MARCOS | Ilocos Norte | 19 | Yes |
| ECLEO | Dinagat Islands | 37 | Yes |
| SINGSON | Ilocos Sur | 35 | Yes |
| DY | Isabela | 32 | Yes |
| ROMUALDEZ | Leyte | 18 | Yes |

The duplicate check catches the split ID noted in Task 6 (Lissa / Lissa Marie Streegan) and spelling variants such as STO TOMAS / STO. TOMAS.

### Ateneo fat dynasty labels (Step 12)

Ateneo marks an official as a "fat dynasty" when someone with the **same surname** holds office in the same province in the same year. We mark it when someone our engine links as a **relative** (strong or medium) holds office in the same province in the same year.

| | Result |
|---|---|
| Ateneo rows matched to our terms | 201,546 of 207,599 |
| Agreement | 85.2% (between 84% and 87% every year from 1988 to 2022) |
| Ateneo's fat officials that we also flag | 55.9% |
| Our fat officials that Ateneo also flags | 79.1% |
| Flagged by us only | 7,461 (98.6% have a relative with a different surname, from the mother's side or by marriage) |
| Flagged by Ateneo only | 22,349 (mostly the most common surnames: REYES, GARCIA, TAN, DELA CRUZ, MENDOZA, RAMOS) |

The two methods differ in opposite, explainable directions: we are stricter on common surnames (two Reyeses in one province are often not related), and we see more family ties through the mother's line, which a surname-only rule cannot see.

## Known limitations

- Names only: the engine finds **likely** relatives, not confirmed ones. `paternal_kin` cannot tell siblings, cousins, a parent, or a spouse apart.
- Married women carry their husband's surname, so they join the husband's clan; their birth family appears through `maternal_kin`.
- Middle names that are also common first names are dropped (7,372 people), so some real maternal links are missed. This avoids many false links.
- Ateneo rows have no middle names, so officials who only appear in 1988-1998 can only be linked through their last name (paternal rules), not through the mother's side.
- Only the Ateneo linking (Step 4) follows province splits. The kinship rules still compare people within one province, so a family split across new provinces can form two clans. For example, Maguindanao's officials from 2022 onward are listed under Maguindanao del Norte or del Sur, so they form clans separate from the older Maguindanao clans.
- A father and son with the same name, no suffix, and no middle name can be flagged as one person (`person_duplicates`).
- Nicknames are not matched (e.g. HENEDINA / DINA ABAD stay two people, but both are in the Abad clan).
- HF sometimes merges two people into one ID (some IDs hold two different posts in the same year); this cannot be split from names alone.
- Senators and presidents with no provincial or local post have no province, so they are only linked if they held another post.
- Pre-1987 roster rows use historical province names when there is no current equivalent.
- Not yet validated against Wikidata family relations (`WIKIDATA_SPARQL_URL`); this could be added later.

