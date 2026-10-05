# Town-Level Dynasty Stronghold % & Curated Partitioning

Notebook: `notebooks/04_dynasty_stronghold.ipynb`

## How to run

Run after Task 7, because the notebook reads its outputs from `data/staging`:
`politicians.parquet`, `politician_terms.parquet`, `kinship_edges.parquet`, `clans.parquet`, plus `hf_memberships_clean.parquet` (Task 6, used to find cities).

Open the notebook and click **Run All**. It takes under a minute and writes 3 partitioned tables to `data/curated`.

## Definitions

- **Official:** an elected winner in a primary term (`is_primary == True` in `politician_terms`), in the elections 2001, 2004, ..., 2025.
- **Dynastic official (in a given year):** has at least one strong or medium relative (from `kinship_edges`) who first held office **in that year or earlier**. A relative who enters politics later does not count yet.
- **Dynasty stronghold % (town):** dynastic local officials (mayor, vice mayor, councilors) / all local officials in that town and election.
- **Fat dynasty:** one clan holds 2 or more local seats in the same town at the same time.

Two safety measures when counting relatives:

1. Links between two people with the same first and last name and no conflicting middle name are skipped (3,963 links). These are most likely one person under two IDs.
2. A relative's start year uses primary terms only, so duplicate OpenHalalan copies of HF officials (2004-2016) do not count as relatives.

## Steps

| Step | What it does |
|---|---|
| 1 | Loads the Task 7 outputs |
| 2 | Marks each official as dynastic or not, per election |
| 3 | Town table: stronghold %, dynastic mayor, top clan, fat dynasty, city flag, stronghold level |
| 4 | Province table: provincial officials, governor, and a summary of the province's towns |
| 5 | Benchmark check against PCIJ |
| 6 | Writes the curated tables, partitioned by election year |

## Curated outputs

All in `data/curated`, one folder per election year (`year=2001`, ..., `year=2025`). Each run deletes and rewrites the folders, so re-running never creates duplicates.

| Table | Rows | One row per |
|---|---|---|
| `town_dynasty_stronghold/` | 14,437 | town x election |
| `province_dynasty_stronghold/` | 720 | province x election |
| `official_terms_dynastic/` | 157,168 | official x election |

Read one year only (reads just that folder):

```python
pd.read_parquet("data/curated/town_dynasty_stronghold", filters=[("year", "=", 2025)])
```

### town_dynasty_stronghold

| Column | Meaning |
|---|---|
| `year`, `province_std`, `town_std` | Election and town (join on province **and** town) |
| `n_officials`, `n_dynastic` | Local officials, and how many are dynastic |
| `dynastic_share` | **Stronghold %** (0 to 1) |
| `stronghold_level` | low (0-25%), moderate (25-50%), high (50-75%), stronghold (75-100%) |
| `mayor_uid`, `mayor_dynastic` | The mayor, and whether they are dynastic (empty if no mayor recorded) |
| `top_clan_id`, `top_clan_label`, `top_clan_seats`, `top_clan_share` | The clan with the most seats in the town |
| `fat_dynasty` | True if one clan holds 2+ seats at once |
| `is_city` | True for cities (from HF "CITY OF ..." labels) |
| `source` | `hf` (2004-2016) or `openhalalan` (2001, 2019-2025) |

### province_dynasty_stronghold

| Column | Meaning |
|---|---|
| `year`, `province_std` | Election and province |
| `n_provincial_officials`, `n_dynastic`, `provincial_dynastic_share` | Governor, vice governor, board members |
| `governor_uid`, `governor_dynastic` | The governor, and whether they are dynastic |
| `n_towns`, `avg_town_dynastic_share`, `share_towns_dynastic_mayor`, `n_stronghold_towns` | Summary of the province's towns |

### official_terms_dynastic

`person_uid`, `year`, `position`, `province_std`, `town_std`, `party`, `source`, `is_dynastic`, `first_relative_year`, `clan_id`. Join to `data/staging/politicians.parquet` on `person_uid` for names.

## Results

| Year | Towns | Avg stronghold % | Dynastic mayors | Fat dynasty towns | Stronghold towns (75%+) |
|---|---|---|---|---|---|
| 2001 | 1,605 | 14.8% | 30.8% | 31.4% | 0.2% |
| 2004 | 1,591 | 25.2% | 46.0% | 34.4% | 0.6% |
| 2007 | 1,513 | 32.8% | 56.3% | 36.5% | 1.8% |
| 2010 | 1,627 | 40.4% | 64.3% | 45.2% | 5.0% |
| 2013 | 1,593 | 44.8% | 67.6% | 48.5% | 6.6% |
| 2016 | 1,603 | 48.3% | 69.9% | 47.5% | 8.7% |
| 2019 | 1,634 | 62.2% | 81.8% | 53.4% | 27.5% |
| 2022 | 1,634 | 64.2% | 84.3% | 57.2% | 28.0% |
| 2025 | 1,637 | 64.9% | 84.1% | 60.0% | 31.7% |

Most dynastic provinces in 2025 (average town stronghold %): Biliran (80.0%), Northern Samar (77.1%), Masbate (75.7%), Batanes (75.0%), Cebu (72.6%, with 27 stronghold towns).

Highest single-clan control in 2025: 7 of 10 local seats held by one clan in Ampatuan, Shariff Aguak and Talayan (all Maguindanao del Sur).

## Benchmark check (PCIJ)

| | Cities with a dynastic mayor | Provinces with a dynastic governor |
|---|---|---|
| 2013 | 74.2% | 81.2% |
| 2016 | 74.6% | 79.7% |
| 2019 | 87.6% | 79.0% |
| 2022 | 89.9% | 86.4% |
| 2025 | 89.1% | 84.1% |
| **PCIJ** | **75.8%** (113 of 149) | **86.6%** (71 of 82) |

Cities in 2013-2016 and provinces in 2022 are within about 1 percentage point of PCIJ. PCIJ's method is not identical to ours, so ranges are compared, not one exact year.

## Known limitations

- **Left-censoring:** the data starts in 2001 (only House members go back further, through the roster). Relatives who served before 2001 are invisible, so early years look less dynastic than they were. The rise over time is partly real and partly this effect.
- **Source change in 2019:** HF (2004-2016) uses full names; OpenHalalan (2019-2025) often uses ballot nicknames (e.g. "PACOY" for Francisco). Some people are split into two IDs across the change, which raises later shares. **Compare years within one source** (2004-2016, or 2019-2025) for trends.
- **Towns without a location:** 1,606 HF local rows (2013, 2016) have no town after Task 6's backfill, so those officials are not in the town table.
- **Town name variants:** about 30 towns are spelled differently in OpenHalalan than in HF (e.g. KALOOCAN / KALOOKAN, mostly in 2001), which splits their time series. New towns from the Maguindanao split and the Special Geographic Area appear only in recent years.
- **Cities:** `is_city` finds 140 cities from HF labels (the official count is around 149).
- **Council size varies:** most towns have 10 local officials, large cities more, so a 75% share means different seat counts in different places.
- Kinship itself is name-based (see `docs/task7_kinship.md`), so "dynastic" means "has a likely relative in office".

