# Task 6: Dataset Cleaning & Locality Backfilling

Script: `src/transform/clean_backfill.py`
Supporting files: `src/transform/mappings.py` (name and place mappings), `src/transform/normalize.py` (cleaning functions)
Checks and validation: `notebooks/02_cleaning_checks.ipynb` (backfill), `notebooks/06_person_resolution.ipynb` (merging split person IDs)
Profiling and cleaning rules: `notebooks/01_source_profiling.ipynb` (section 6)

## How to run

Run after the ingest and parse steps, because the script reads their outputs:

- `data/raw/hf_persons.parquet`, `data/raw/hf_memberships.parquet`, `data/raw/openhalalan_winners.csv` (from `ingest_raw.py`)
- `data/staging/psa_poverty.csv` (from `parse_psa_poverty.py`)
- `data/staging/roster_legislators.csv` (from `parse_roster.py`)

```
python src/transform/clean_backfill.py
```

An optional output folder can be given as an argument. The default is `data/staging`.

Inside Docker (tested):

```
docker compose run --rm --no-deps --entrypoint python airflow-scheduler /opt/airflow/src/transform/clean_backfill.py
```

In the Airflow DAG, this step can be a task that runs `python /opt/airflow/src/transform/clean_backfill.py`, scheduled after the ingest and parse tasks.

After re-running this step, re-run the later steps that read its outputs (kinship, stronghold, network notebooks, and the database loader). All 6 checks in `src/validation/quality_checks.py` pass on these outputs.

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

### Shared columns for joining

- `province_std`: standard province name in every table (OpenHalalan's naming, e.g. `DAVAO DE ORO`, `NCR FIRST DISTRICT`).
- Towns: `locality_std` (memberships) and `town_std` (OpenHalalan, PSA cities, roster cities) use the same standardized names. Always join on province **and** town, since town names repeat across provinces (e.g. ISABELA in Basilan and in Negros Occidental).
- Names: `last_key` and `first_key` (persons, roster) are compact names: uppercase, no suffix, letters only. For OpenHalalan, compute them with `name_key()` from `src/transform/normalize.py`.
- People: `hf_memberships_clean.person_id` = `hf_persons_clean.id` = merged person ID.

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

`locality_source` values:

| Value | Rows | Meaning | Validated accuracy |
|---|---|---|---|
| `original` | 58,594 | Town recorded in the source | n/a |
| `history` | 13,795 | Same person (HF id), same province, exactly one known town in other years | 99.79% |
| `openhalalan_t1` | 5,067 | OpenHalalan, same year, position, province, last name, and first name | 97.96% |
| `openhalalan_t2` | 590 | Same as t1, but first names only share a word | 97.79% |
| `openhalalan_xyear` | 964 | Same person (by name and province) in reliable OpenHalalan years | 99.00% / 98.32% |
| `unfilled` | 1,318 | No reliable match; `locality_std` is empty | n/a |
| `shift_revoked` | 288 | Only match was in OpenHalalan's shifted 2013 data; `locality_std` is empty | n/a |
| `not_applicable` | 5,618 | Provincial or district position (Governor, Vice Governor, Board Member, House Representative); no town expected | n/a |

The backfill targeted 22,022 Mayor, Vice Mayor, and Councilor rows without a town (2013 and 2016) and filled 20,416 of them (92.7%). Matches were accepted only when all candidates pointed to one town. The backfill runs on the original HF IDs, before split IDs are merged.

### openhalalan_winners_clean

Original columns in snake_case (`last_name`, `middle_name`, `city`, …), plus:

| Column | Meaning |
|---|---|
| `town_std` | Standard town name (from `city`) |
| `province_std` | Standard province name (same as `province`) |
| `is_national` | True for Senator, President, Vice President (no province or town) |
| `town_shift_suspect` | True for 2010 and 2013 rows whose town is affected by the town-label shift (see warning) |

**Warning: town-label shift in 2010 and 2013.** In these two years, cities' officials are labeled with the municipality listed just before the city (e.g. Baguio's officials appear under Atok, Taguig's under Pateros), so 133 of 134 cities are missing. The likely cause is a forward-fill error in the source. Flagged rows include both the municipality's own officials and the misplaced city officials; they cannot be told apart. Do not use OpenHalalan towns for 2010 and 2013 rows where `town_shift_suspect` is True. Other years are not affected.

### psa_poverty_clean

Original columns, plus:

| Column | Meaning |
|---|---|
| `province_std` | Standard province name (empty for national and region rows) |
| `town_std` | Town, for the two city rows only |
| `is_city` | True for Cotabato City and Isabela City, which PSA reports like provinces |
| `is_combined_area` | True for the 2023 Maguindanao row, which overlaps Maguindanao del Norte and del Sur. Exclude it when summing or averaging 2023 provinces |

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

Notes:
- `is_party_list` now also catches misspelled placeholders ("PARTY LIST", "PART- LIST", "PATY-LIST"): 287 rows (was 273). Party-list and sectoral rows have no `province_std`.
- From 1987 onward, city districts are resolved to their province (e.g. QUEZON CITY → NCR SECOND DISTRICT). Before 1987, `province_std` is set only when the name matches a current province; historical names remain in `region_province`.
- Kalinga-Apayao (a former province, 3 rows from 1987 onward) has no `province_std`.

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

- 1,606 HF town-level rows remain without a town (`unfilled` + `shift_revoked`).
- About 7% of `name_only` person merges may join two different people (see above). HF may also merge two different people into one ID; this cannot be split from names alone.
- "Sta"/"Santa" and "Sto"/"Santo" surnames produce different name keys.
- HF and OpenHalalan likely share an origin, so their agreement is not fully independent confirmation.
- Not reviewed: the 193 extra OpenHalalan rows in 2016, the 5 roster `years_suspect` rows, roster `district` labels, and the meaning of PSA's footnote flags.

See section 6 of `notebooks/01_source_profiling.ipynb` for the full list of rules and their status, and section G there for open team questions.