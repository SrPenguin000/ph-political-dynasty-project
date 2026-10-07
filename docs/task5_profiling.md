# Task 5: Source Profiling

Notebook: `notebooks/01_source_profiling.ipynb`
Supporting file: `src/utils/profiling.py` (`profile_table`, `source_summary`)
Next step: the cleaning rules in section 6 of the notebook, implemented in task 6 (`src/transform/clean_backfill.py`, see `docs/task6_cleaning.md`)

## How to run

Run after the ingest and parse steps. The notebook reads:

- `data/raw/hf_persons.parquet`, `data/raw/hf_memberships.parquet`, `data/raw/openhalalan_winners.csv`, `data/raw/ateneo_politicians_raw.parquet`, `data/raw/ateneo_provinces_raw.parquet` (from `ingest_raw.py`)
- `data/staging/psa_poverty.csv` (from `parse_psa_poverty.py`) and `data/staging/roster_legislators.csv` (from `parse_roster.py`)

Open the notebook and click **Run All**. It only reads files and writes nothing.

The outputs describe the data before cleaning. One cell in section 7 also uses task 6's town maps and cleaned files, so it needs task 6's outputs. It was run before the town review in notebook 07 and shows 4,481 Ateneo rows with an unknown town. Running it again now shows 3,152. Task 6's own check, which compares towns within province groups and skips provincial posts, leaves only 20 (notebook 07).

## Sources

| Source | File and format | Rows | Columns | Years | Duplicate rows | Missing cells |
|---|---|---|---|---|---|---|
| HF persons | `hf_persons.parquet` (Hugging Face) | 45,424 | 4 | n/a | 0 | 24.0% |
| HF memberships | `hf_memberships.parquet` (Hugging Face) | 86,234 | 8 | 2004–2016 | 0 | 4.0% |
| OpenHalalan winners | `openhalalan_winners.csv` | 157,333 | 14 | 2001–2025 | 0 | 10.6% |
| PSA poverty | `psa_poverty.csv` (parsed from a PDF) | 320 | 13 | 2018, 2021, 2023 | 0 | 0.8% |
| House roster | `roster_legislators.csv` (parsed from a PDF) | 5,118 | 15 | 1907–2019 | 0 | 9.6% |
| Ateneo politicians | `ateneo_politicians_raw.parquet` (from the Excel file) | 207,599 | 10 | 1987–2022 | 7 | 1.6% |
| Ateneo provinces | `ateneo_provinces_raw.parquet` (from the Excel file) | 81 | 12 | 1992–2022 | 0 | 2.1% |

Together the sources cover House members from 1907 and local officials from 1987 to 2025.

Most missing values are expected, not lost data: `name_suffix` (most people have no suffix), OpenHalalan `Title`, roster `notes`, and `congress_number` (older legislatures had no Congress numbers). The real gaps are in the town columns: HF `locality` (32.1% missing), Ateneo `municipality` (16.2%), and OpenHalalan `City` (8.6%).

## Findings by source

### HF persons and memberships (sections 1 and 2)

- `id` is unique, and every membership matches a person (0 orphans).
- **Town gaps:** 27,640 membership rows (32%) have no `locality`. 5,618 are expected (governors, vice governors, board members, and House members cover a province or district, not one town). The other 22,022 are real gaps in Mayor, Vice Mayor, and Councilor rows, almost all in 2013 (99% missing) and 2016 (38%, in an alphabetical block of provinces from ABRA to IFUGAO, plus NCR districts).
- 62% of the gaps can be filled from the same person's town in other years.
- **Names:** surname variants ("De La Cruz" / "Dela Cruz"), 6 suffixes inside `last_name`, odd suffixes ("XIV", "XVI"), and no middle names.
- Zero duplicate full names across 45,424 people is unusually clean. Task 6 later found people split into two IDs (e.g. Lissa / Lissa Marie Streegan).

### OpenHalalan winners (section 3)

- 9 elections from 2001 to 2025, about 17,000 rows each. Includes Senators, Presidents, and Vice Presidents.
- **Town (`City`) is 91% complete**, including HF's missing years (87% in 2013, 94% in 2016).
- **Middle names are 89% complete.** HF has none, and a middle name is usually the mother's surname, so it helps with kinship (task 7).
- **No person ID**, so rows must be matched to HF on name, province, year, and position. Row counts are almost identical to HF in shared years, so the two likely share an origin, and their agreement is not independent confirmation.
- 6 province names and about 100 town spellings differ from HF.
- Found later in task 6: in 2010 and 2013, most cities' officials are filed under the town listed just before them.

### PSA poverty (section 4)

- 320 rows: one per area, level, and year (2018, 2021, 2023). Every row records its PDF page.
- The smallest level is the province (plus NCR districts, Isabela City, and Cotabato City).
- No overlap with HF's years. The nearest elections are 2019, 2022, and 2025.
- 2023 has a combined Maguindanao row next to Maguindanao del Norte and del Sur, so using all three would count Maguindanao twice.
- Some estimates are imprecise (`cv` up to 49.2).

### House roster (section 5)

- 5,118 terms from the 1st Philippine Legislature (1907) to terms starting in 2019. Names have a middle initial only.
- `congress_number` is blank in 37% of rows. Most are older bodies without Congress numbers, but the parser also missed some written as words or with typos ("First Congress", "13th Congresss").
- 14 party-list rows were missed by `is_party_list` because the placeholder was misspelled.
- 64 rows have no province: 48 are explained in `notes` (Cabinet members, at-large representatives).
- 138 place names for district representatives since 2001, the messiest of all sources: cities listed as provinces, "CITY" variants, typos, old names, and shared districts (e.g. TAGUIG-PATEROS).

### Ateneo politicians and provinces (sections 7 and 8)

- 13 elections from 1987 to 2022: House members only in 1987, then about 17,000 rows per election, with a `fat_dynasty_indicator` for every official. No middle names.
- **New coverage:** 68,289 rows from 1987–1998. No other source has local officials for those years.
- **HF's 2004–2016 memberships are Ateneo's 2004–2016 rows:** the same counts, the same missing towns, and the same surnames except four typos HF fixed. So HF is not an independent source for those years, and Ateneo cannot fill the 2013 and 2016 town gaps.
- **Issues:** broken "Ñ" characters (363 rows), 58 Metro Manila rows under the wrong NCR district, towns listed under their old province before a province split (e.g. Ipil moves from Zamboanga del Sur to Zamboanga Sibugay in 2001), 4,481 town rows that match no known town, 91 names with scanning errors (mostly 1988), suffixes stuck to first names in 2019, and 13 duplicate rows.
- **`fat_dynasty_indicator`** follows one rule exactly for 1987–2016: another official with the same surname in the same province and election (99.92% agreement over all years; 2019 and 2022 differ slightly). It is a surname rule, not confirmed kinship.
- **The province sheet** is the share of "fat" officials per province and election, recomputed exactly from the politicians sheet (871 values). Its 20 blanks are provinces that did not exist yet.
- **Usage:** the file's Disclaimer sheet does not allow copying or distributing it without permission, so the raw file stays out of the repository. Cite it as "The Ateneo Policy Center Philippine Political Dynasties Dataset".

### All sources (section 9)

- Places must be matched on province and town together, because some town names exist in several provinces (e.g. ISABELA in Basilan and in Negros Occidental).
- Party names are not standardized in any source (1,956 distinct values in Ateneo, 421 in OpenHalalan, 368 in HF). The project does not analyze parties, so they are kept as reported.
- All value ranges are valid: poverty incidence 0.3–75.3%, fat dynasty shares 0–52.85%, and all years within each source's coverage.

## From findings to cleaning rules

Section 6 of the notebook turns the findings into cleaning rules A–H, each marked **Done**, **Changed**, or **Open**. Main results in task 6:

| Finding | Result in task 6 |
|---|---|
| 22,022 HF town gaps in 2013 and 2016 | Backfilled from each person's history and OpenHalalan: 20,421 filled (92.7%) |
| Different province names across sources | `province_std` in every cleaned table, plus `province_group` to compare places across province splits |
| Town spelling differences | `norm_town`, `TOWN_MAP`, and `PROVINCE_TOWN_MAP`, reviewed town by town |
| HF people split into two IDs | Merged: 45,424 → 44,106 people |
| Ateneo's 2004–2016 rows are HF's | Linked: 86,229 of 86,234 rows get HF's person ID |
| Broken characters, scanning errors, suffixes in names | Repaired, fixed, and moved to `name_suffix` |
| Roster congress numbers and party-list misses | `congress_number` 3,217 → 3,260 rows; `is_party_list` 273 → 287 rows |

## Open questions for the team

From sections 6 G and H of the notebook:

1. Analyze 2004–2016 only, or include OpenHalalan's 2001 and 2019–2025?
2. How should the Maguindanao split be handled? `province_group` already puts Maguindanao del Norte and del Sur in one group.
3. How should hyphenated surnames count in kinship? Ateneo's 2022 flag counts them for both families.
4. How should shared districts (e.g. Taguig-Pateros) be assigned?
5. Main source for 2001 (OpenHalalan is more complete) and for 2019 and 2022 (Ateneo is more complete, except for mayors)?

Answered: task 7 adds Ateneo's 1988–1998 officials to the combined people and terms tables.

## Not profiled

- OpenHalalan's `Sex` and `Sex Source` columns, and the meaning of the `self-prior` and `v8.5` middle name sources.
- In the PSA PDF: the meaning of the footnote flags, and whether poverty incidence counts families or individuals.
- The roster's `district` labels ("Lone", "Fourth", ...).
