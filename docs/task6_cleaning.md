# Task 6: Dataset Cleaning & Locality Backfilling

Script: `src/transform/clean_backfill.py`
Supporting files: `src/transform/mappings.py` (name and place mappings), `src/transform/normalize.py` (cleaning functions), `src/utils/town_review.py` (town review helpers)
Checks and validation: `notebooks/02_cleaning_checks.ipynb` (backfill), `notebooks/06_person_resolution.ipynb` (merging split person IDs), `notebooks/07_ateneo_cleaning.ipynb` (Ateneo cleaning and town review)
Unit tests: `tests/test_cleaning.py`
Profiling and cleaning rules: `notebooks/01_source_profiling.ipynb` (section 6, rules A–H)

## How to run

Run after the ingest and parse steps, because the script reads their outputs:

- `data/raw/hf_persons.parquet`, `data/raw/hf_memberships.parquet`, `data/raw/openhalalan_winners.csv`, `data/raw/ateneo_politicians_raw.parquet`, `data/raw/ateneo_provinces_raw.parquet` (from `ingest_raw.py`)
- `data/staging/psa_poverty.csv` (from `parse_psa_poverty.py`)
- `data/staging/roster_legislators.csv` (from `parse_roster.py`)

```
python src/transform/clean_backfill.py
```

An optional output folder can be given as an argument. The default is `data/staging`. If an input is missing, the script stops with a message naming the file.

Inside Docker (tested):

```
docker compose run --rm --no-deps --entrypoint python airflow-scheduler /opt/airflow/src/transform/clean_backfill.py
```

In Airflow, the DAG task `run_clean_backfill` runs this script before the kinship, stronghold, and network notebooks.

After re-running this step, re-run the later steps that read its outputs (kinship, stronghold, network notebooks, and the database loader). All 9 checks in `src/validation/quality_checks.py` pass on these outputs (see "Data quality checks" below).

### Logging

The script logs each input it reads, each output it writes (with row counts), and summary counts, each line with a time and a level (`INFO` or `WARNING`). It logs a `WARNING` when some Ateneo towns are not confirmed by any other source (currently 20 rows, reviewed in notebook 07).

### Rerun safety

Every run rebuilds all outputs from the inputs, with nothing random, so running it again gives byte-identical files. Each output is first written to a temporary file and then swapped in, so a run that fails halfway never leaves a half-written file. Check (PowerShell):

```
$before = Get-FileHash data\staging\*.parquet
python src\transform\clean_backfill.py
$after = Get-FileHash data\staging\*.parquet
if (Compare-Object $before $after -Property Hash, Path) { "some outputs changed" } else { "all outputs identical after a rerun" }
```

Result: `all outputs identical after a rerun`. The outputs also have the same values with pandas 2.2 and pandas 3.0. Inside Docker (Python 3.11.9, pandas 3.0.6), the script logs the same counts and all 9 checks pass.

### Tests

```
pip install -r requirements-dev.txt
python -m pytest tests
```

8 unit tests cover the text repair, the scanning-error fix, suffix splitting, town and name standardization, province-group town fixes, and the province sheet reshape.

### Data quality checks

`src/validation/quality_checks.py` runs in the DAG before the database load, and a failed check stops the pipeline there. DQ-1 to DQ-6 cover the HF, roster, and PSA tables. DQ-7 to DQ-9 cover the two Ateneo tables:

| Check | What it tests |
|---|---|
| DQ-7: Ateneo Keys and HF Links | Row ids are unique. Every HF link points to an existing HF row, no HF row is linked twice, and the linked row has HF's person ID. At least 99% of the 2004–2016 rows must be linked (currently 99.99%). |
| DQ-8: Ateneo Town Sources and Completeness | `town_source` has only known values, a row has a town exactly when its source found one, and every year is between 1987 and 2022. It also reports the 20 unconfirmed towns, without failing. |
| DQ-9: Ateneo Province Shares vs Recount | Shares are between 0 and 100, there is one row per province and year, and every share matches a recount from `ateneo_politicians_clean` (largest gap 0.000002). |

## Outputs

All outputs are parquet files in `data/staging`. Read them with `pd.read_parquet(...)`.

| File | Rows | Contents |
|---|---|---|
| `hf_persons_clean.parquet` | 44,106 | One row per person (HF), after merging split IDs |
| `hf_person_id_map.parquet` | 45,424 | One row per original HF person ID, with the merged ID it became |
| `hf_memberships_clean.parquet` | 86,234 | One row per person, position, and election (HF), with backfilled towns |
| `openhalalan_winners_clean.parquet` | 157,333 | Election winners 2001–2025 (OpenHalalan) |
| `psa_poverty_clean.parquet` | 320 | PSA poverty statistics 2018, 2021, 2023 |
| `roster_legislators_clean.parquet` | 5,118 | Historical House roster |
| `ateneo_politicians_clean.parquet` | 207,599 | One row per official, position, and election (Ateneo, 1987–2022), with standard places and names, flags, and the link to HF |
| `ateneo_province_shares_clean.parquet` | 891 | Ateneo's fat-dynasty share per province and election (1992–2022) |

### Shared columns for joining

- `province_std`: standard province name in every table (OpenHalalan's naming, e.g. `DAVAO DE ORO`, `NCR FIRST DISTRICT`).
- `province_group`: in every table. Provinces created by a split share the group of the province they came from (e.g. DAVAO DE ORO → DAVAO DEL NORTE, APAYAO → KALINGA, MAGUINDANAO DEL NORTE → MAGUINDANAO). Join on it to follow people and towns across splits.
- Towns: `locality_std` (memberships) and `town_std` (OpenHalalan, Ateneo, PSA cities, roster cities) use the same standardized names, with HF's spelling as the standard. Always join on province (or province group) **and** town, since town names repeat across provinces (e.g. ISABELA in Basilan and in Negros Occidental).
- Names: `last_key` and `first_key` (persons, roster, Ateneo) are compact names: uppercase, no suffix, letters only. For OpenHalalan, compute them with `name_key()` from `src/transform/normalize.py`.
- People: `hf_memberships_clean.person_id` = `hf_persons_clean.id` = `ateneo_politicians_clean.person_id` (2004–2016) = merged person ID.

### hf_persons_clean

One row per person. `id` is the merged person ID (one of the person's original HF IDs: the one with the most terms). `first_name` and `last_name` are the display names: the most complete first name, and the surname spelling with ñ when available.

Columns added to the original ones:

| Column | Meaning |
|---|---|
| `suffix_suspect` | True for implausible suffixes ("XIV", "XVI") |
| `last_key`, `first_key` | Compact names for matching |
| `n_ids` | Number of original HF IDs merged into this person (1 = not merged) |
| `merge_evidence` | `middle_name_agree`, `name_only`, or empty when not merged (see "Merging split person IDs") |
| `name_variants` | Every spelling merged into this person, e.g. "Herbert Bautista \| Herbert C Bautista \| Herbert Constantine Bautista" |

Other changes: suffixes found inside `last_name` were moved to `name_suffix` (6 rows). "Jr"/"Sr" standardized to "Jr."/"Sr.".

### hf_person_id_map

| Column | Meaning |
|---|---|
| `person_id_raw` | Original HF person ID |
| `person_uid` | Merged person ID (`id` in `hf_persons_clean`, `person_id` in memberships) |
| `n_ids` | Number of original IDs in the merged person |
| `merge_evidence` | Same as in `hf_persons_clean` |

Use this file to trace or undo any merge.

### hf_memberships_clean

Original columns (including the raw `province` and `locality`), plus:

| Column | Meaning |
|---|---|
| `person_id` | **Merged** person ID (links to `hf_persons_clean.id`) |
| `person_id_raw` | Original HF person ID |
| `province_std` | Standard province name |
| `locality_std` | Standard town name, original or backfilled |
| `locality_source` | How `locality_std` was obtained (see below) |
| `province_group` | Province group (see "Shared columns for joining") |

`locality_source` values:

| Value | Rows | Meaning | Validated accuracy |
|---|---|---|---|
| `original` | 58,594 | Town recorded in the source | n/a |
| `history` | 13,797 | Same person (HF id), same province, exactly one known town in other years | 99.79% |
| `openhalalan_t1` | 5,067 | OpenHalalan, same year, position, province, last name, and first name | 97.96% |
| `openhalalan_t2` | 590 | Same as t1, but first names only share a word | 97.79% |
| `openhalalan_xyear` | 967 | Same person (by name and province) in reliable OpenHalalan years | 99.00% / 98.32% |
| `unfilled` | 1,316 | No reliable match; `locality_std` is empty | n/a |
| `shift_revoked` | 285 | Only match was in OpenHalalan's shifted 2013 data; `locality_std` is empty | n/a |
| `not_applicable` | 5,618 | Provincial or district position (Governor, Vice Governor, Board Member, House Representative); no town expected | n/a |

The backfill targeted 22,022 Mayor, Vice Mayor, and Councilor rows without a town (2013 and 2016) and filled 20,421 of them (92.7%). Matches were accepted only when all candidates pointed to one town. The backfill runs on the original HF IDs, before split IDs are merged. The accuracy figures were measured before the town name review (October 2026).

The town name review (notebook 07) changed 60 rows: KALOOKAN → CALOOCAN (42), BANNA ESPIRITU → BANNA (13), and 5 rows newly filled because OpenHalalan's spellings now match HF's.

### openhalalan_winners_clean

Original columns in snake_case (`last_name`, `middle_name`, `city`, …), plus:

| Column | Meaning |
|---|---|
| `town_std` | Standard town name (from `city`) |
| `province_std` | Standard province name (same as `province`) |
| `is_national` | True for Senator, President, Vice President (no province or town) |
| `town_shift_suspect` | True for 2010 and 2013 rows whose town is affected by the town-label shift (see warning) |
| `province_group` | Province group (see "Shared columns for joining") |

Town names follow HF's spelling: 48 OpenHalalan variants and BANNA ESPIRITU were mapped (1,519 rows), e.g. SALCEDO BAUGEN → SALCEDO, JOLO CAPITAL → JOLO, KALOOCAN → CALOOCAN, GETAFE → JETAFE. The 8 towns first elected in 2025 (Special Geographic Area) keep their names.

**Warning: town-label shift in 2010 and 2013.** In these two years, cities' officials are labeled with the municipality listed just before the city (e.g. Baguio's officials appear under Atok, Taguig's under Pateros), so 133 of 134 cities are missing. The likely cause is a forward-fill error in the source. Flagged rows include both the municipality's own officials and the misplaced city officials; they cannot be told apart. Do not use OpenHalalan towns for 2010 and 2013 rows where `town_shift_suspect` is True. The agreement check with Ateneo (notebook 07, section 5) found 12 more town-years, outside the flagged rows, where OpenHalalan appears to put a town's officials under the town next to it alphabetically (e.g. CARAGA's officials under BOSTON in 2001, 2004, and 2007). These are not flagged.

### psa_poverty_clean

Original columns, plus:

| Column | Meaning |
|---|---|
| `province_std` | Standard province name (empty for national and region rows) |
| `town_std` | Town, for the two city rows only |
| `is_city` | True for Cotabato City and Isabela City, which PSA reports like provinces |
| `is_combined_area` | True for the 2023 Maguindanao row, which overlaps Maguindanao del Norte and del Sur. Exclude it when summing or averaging 2023 provinces |
| `province_group` | Province group (see "Shared columns for joining") |

Cotabato City's province is MAGUINDANAO (2018, 2021) and MAGUINDANAO DEL NORTE (2023). Isabela City's is BASILAN.

### roster_legislators_clean

Original columns, plus:

| Column | Meaning |
|---|---|
| `period_std` | Standardized legislative body name (34 distinct values) |
| `congress_number` | Recomputed from `period_std` (now filled in 3,260 rows, was 3,217) |
| `province_std` | Standard province name (see notes) |
| `town_std` | City, when the district belongs to a city (from 1987 onward) |
| `first_name`, `middle_initial`, `name_suffix` | Split from `name` ("SURNAME, FIRST JR. M.") |
| `last_key`, `first_key` | Compact names for matching |
| `province_group` | Province group (see "Shared columns for joining") |

Notes:
- `is_party_list` now also catches misspelled placeholders ("PARTY LIST", "PART- LIST", "PATY-LIST"): 287 rows (was 273). Party-list and sectoral rows have no `province_std`.
- From 1987 onward, city districts are resolved to their province (e.g. QUEZON CITY → NCR SECOND DISTRICT). Before 1987, `province_std` is set only when the name matches a current province; historical names remain in `region_province`.
- Kalinga-Apayao (a former province, 3 rows from 1987 onward) has no `province_std` or `province_group`.

### ateneo_politicians_clean

All 207,599 rows of the Ateneo politicians sheet (1987–2022: Mayor, Vice Mayor, Councilor, Governor, Vice Governor, Provincial Board Member, and House Representative), with lowercase column names. No row is deleted: problems are fixed in new columns or flagged. `first_name`, `last_name`, `party`, and `municipality` keep the source text, with broken characters repaired ("PARAÃ‘AQUE" → "PARAÑAQUE").

| Column | Meaning |
|---|---|
| `ateneo_row_id` | Row ID (`AT-000000`, in source order) |
| `province_std` | Standard province name, after moving rows filed under the wrong place (see "Ateneo cleaning") |
| `province_group` | Province group (see "Shared columns for joining") |
| `town_std` | Standard town name, for Mayor, Vice Mayor, and Councilor rows |
| `town_verified` | True if HF or OpenHalalan record the same town in the same province group, or it is a historical town. False for 20 rows. Empty when there is no town |
| `town_source` | How `town_std` was obtained (see below) |
| `first_name_std`, `last_name_std` | Uppercase names, with suffixes moved out and scanning errors fixed |
| `name_suffix` | Jr., Sr., II, III, ... (3,184 rows) |
| `name_suspect` | True when the source name has digits or symbols from scanning (91 rows) |
| `first_key`, `last_key` | Compact names for matching |
| `is_duplicate` | True for the second copy of a repeated row (13 rows) |
| `is_fat_dynasty` | Ateneo's own flag (`fat_dynasty_indicator == "fat"`), unchanged (52,932 rows) |
| `hf_membership_id` | The HF membership row copied from this row (2004–2016) |
| `person_id` | Merged person ID (`hf_persons_clean.id`) for rows linked to HF; empty in other years |

`town_source` values:

| Value | Rows | Meaning |
|---|---|---|
| `original` | 172,336 | Town from Ateneo's `municipality` |
| `history`, `openhalalan_t1`, `openhalalan_t2`, `openhalalan_xyear` | 13,797 / 5,107 / 590 / 967 | Town copied from HF's backfill through the HF link (2013 and 2016). 40 of the `openhalalan_t1` rows are the 2001 doubled towns (see "Ateneo cleaning") |
| `unfilled` | 1,611 | No town: 1,601 in 2013 and 2016 that HF could not fill either, and 10 written "---" in 1988 |
| `not_applicable` | 13,191 | Provincial or House position; no town expected |

Notes:
- `is_fat_dynasty` is Ateneo's surname rule (same surname, same province, same year, all positions). Duplicate rows inflate it slightly, and in 2022 hyphenated surnames count for both families.
- `party` is kept as reported (not standardized).
- Person IDs exist only for 2004–2016. Other years can be matched to people with `last_key`, `first_key`, `name_suffix`, and `province_group`.

### ateneo_province_shares_clean

| Column | Meaning |
|---|---|
| `province`, `province_std`, `province_group` | Province as written, standard name, and group |
| `year` | Election year (1992–2022) |
| `fat_dynasty_share_pct` | Percentage of the province's officials flagged as fat dynasty. Empty when the province did not exist yet (20 rows) |

Recounting the share from `ateneo_politicians_clean` matches every value (largest gap 0.000002). NCR and 1987–1988 are not in this sheet.

## Ateneo cleaning

Rules H in `notebooks/01_source_profiling.ipynb`; results in `notebooks/07_ateneo_cleaning.ipynb`.

1. **Text and names:** broken characters repaired (363 municipality and 31 party values). Scanning digits in names fixed (0 → O next to a letter, 1 → I before a letter). Suffixes moved to `name_suffix`, including "111" (→ III) and suffixes stuck to the name (with a period in any year, without one only in 2019, where spaces were lost). 91 names with scanning errors and 13 duplicate rows flagged.
2. **Places:** standard province names. Each Metro Manila city moved to its own NCR district (58 rows), and Manila's districts (TONDO, BINONDO, ...) → MANILA. `province_group` added.
3. **Town names:** every town is checked against HF and OpenHalalan. Unknown names were reviewed with two clues from `suggest_town_fixes`: a known town of the same province with a similar spelling, and the known town where the same surnames held office within the next 10 years. Decisions are kept in `mappings.py`:
   - `TOWN_MAP`: 48 OpenHalalan spellings and BANNA ESPIRITU → HF's spelling, and KALOOKAN/KALOOCAN → CALOOCAN.
   - `PROVINCE_TOWN_MAP`: 108 Ateneo 1988–1998 names, e.g. TAGIG → TAGUIG, MAUTA → MALITA (8 of 10 surnames shared), MUNOZ → SCIENCE CITY OF MUNOZ.
   - `HISTORICAL_TOWNS`: BABAK, KAPUTIAN, and SAMAL (merged into Island Garden City of Samal in 1998) and BACON (merged into Sorsogon City in 2000) keep their names.

   Unconfirmed town rows went from 1,511 to 20.
4. **Town labels:** `label_suspects` flags town-years whose officials share almost no surnames with their own town in the next election, but several with another town of the same province. Fixes:
   - `ATENEO_PLACE_FIXES` (7 entries): swapped labels in 1988 (SAN ROQUE and SAN VICENTE in Northern Samar, ROXAS and SAN VICENTE in Palawan), LAUR → LUPAO (1988), BRAULIO E DUJALI → BABAK (1995; Braulio E. Dujali was created in 1998), and Marawi filed under Maguindanao (1995).
   - `split_doubled_towns`: in 2001, the officials of BULACAN, BILIRAN, LEYTE, and QUEZON (towns named like their province) were listed under the town before them, which then had 20 officials instead of 10. These 40 officials take their town from OpenHalalan's 2001 results.
5. **Link to HF:** HF copied Ateneo's 2004–2016 rows. `link_ateneo_to_hf` matches each Ateneo row to its HF twin on year, position, original province, place text, and name letters. 86,229 of 86,234 rows are linked (the other 5 are names HF wrote differently), no HF row is used twice, and both sources give the same town for all 58,548 rows where both have one. Linked rows get the merged `person_id` and HF's backfilled towns.

**Validation:** for officials found in both Ateneo and OpenHalalan in the same election, the two put them in the same town 99.5–100% of the time in every year from 2001 to 2022. The 12 town-years that disagree look like OpenHalalan's one-town shifts: each pair is two towns next to each other alphabetically, and for CARAGA, CATARMAN, and SOUTH UPI, Ateneo's families stay in the same town across years while OpenHalalan moves them for one or a few elections.

## Merging split person IDs

HF sometimes gives one person a new ID when their name is written differently in a later election. Example: Herbert Bautista appears as "Herbert C" (2004–2010), "Herbert" (2013), and "Herbert Constantine" (2016), with three IDs. Left unmerged, one person counts as several people with the same surname, which inflates family and dynasty measures.

Two IDs are merged when **all** of these hold:
1. Same province, same surname key, and same suffix
2. Compatible first names: one fits inside the other, and single letters count as initials ("Herbert C" fits "Herbert Constantine")
3. Never in office in the same year
4. No conflicting OpenHalalan middle names. Middle names that are empty, single letters, job titles, or words from either first name are ignored. Typos and extensions count as agreeing (GEIRRAN / GIERRAN, ABELLA / ABELLACUCUHAN)

Merged pairs are combined into groups (one group per person). A group is **not** merged if any two of its members overlap in years or have conflicting middle names (11 groups).

| Result | Count |
|---|---|
| People before / after | 45,424 → 44,106 |
| Original IDs merged | 2,595, into 1,277 people |
| IDs merged with middle names agreeing (`middle_name_agree`) | 654 |
| IDs merged on names alone (`name_only`) | 1,941 |

**Uncertainty:** among candidate pairs where both IDs have a middle name, 7.4% conflicted (29 of 391), meaning they were different people. `name_only` merges may contain a similar share of wrong merges (about 75 of 1,022 pairs), most likely family members with similar names who held the same seat one after the other (e.g. a father and son). For strict analyses, treat `name_only` merges with caution; `hf_person_id_map` can undo any merge.

## Known limitations

- 1,601 HF town-level rows remain without a town (`unfilled` + `shift_revoked`).
- Ateneo: 20 rows have a town that no other source confirms (SAN AGUSTIN, Camarines Sur, and SULTAN SA MAROMATA, Maguindanao, both 1988). The label check only finds errors that show in the next election, so similar 1988–1998 errors may remain.
- Ateneo: person IDs exist only for 2004–2016 (through HF), and 5 rows in those years are not linked. Ateneo's 1988–1998 officials are added to the combined people tables (`politicians`, `politician_terms`) in task 7, not here.
- OpenHalalan has one-town shifts beyond the flagged 2010 and 2013 rows (12 town-years found, see the warning above).
- About 7% of `name_only` person merges may join two different people (see above). HF may also merge two different people into one ID; this cannot be split from names alone.
- "Sta"/"Santa" and "Sto"/"Santo" surnames produce different name keys.
- HF and OpenHalalan likely share an origin, so their agreement is not fully independent confirmation.
- Not reviewed: the 193 extra OpenHalalan rows in 2016, the 5 roster `years_suspect` rows, roster `district` labels, and the meaning of PSA's footnote flags.

See section 6 of `notebooks/01_source_profiling.ipynb` for the full list of rules and their status, and sections G and H there for open team questions.
