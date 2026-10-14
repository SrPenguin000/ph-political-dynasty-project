# Town-Level Dynasty Stronghold % & Curated Partitioning

Script (run by Airflow): `src/curate/04_dynasty_stronghold.py`
Notebook (same steps, for exploring and checking results): `notebooks/04_dynasty_stronghold.ipynb`

## How to run

Run after Task 7, because it reads Task 7's outputs from `data/staging`:
`politicians.parquet`, `politician_terms.parquet`, `kinship_edges.parquet`, `clans.parquet`, plus two Task 6 files: `hf_memberships_clean.parquet` (used to find cities) and `ateneo_province_shares_clean.parquet` (used for the Ateneo benchmark).

From the project folder:

```
python src/curate/04_dynasty_stronghold.py
```

It takes under a minute and writes 3 partitioned tables to `data/curated`. In Airflow, this is the task `run_dynasty_stronghold`, which runs after `run_kinship_engine`.

## Definitions

- **Official:** an elected winner in a primary term (`is_primary == True` in `politician_terms`), in the elections 1988, 1992, 1995, 1998, 2001, 2004, ..., 2025.
- **Dynastic official (in a given year):** has at least one strong or medium relative (from `kinship_edges`) who first held office **in that year or earlier**. A relative who enters politics later does not count yet.
- **Fat dynasty official (Ateneo's definition):** has a strong or medium relative in office **in the same province in the same year**. Stricter than "dynastic".
- **Dynasty stronghold % (town):** dynastic local officials (mayor, vice mayor, councilors) / all local officials in that town and election.
- **Fat dynasty town:** one clan holds 2 or more local seats in the same town at the same time.

Safety measures when counting:

1. Links between two people with the same first and last name and no conflicting middle name are skipped (2,885 links). These are most likely one person under two IDs.
2. A relative's start year uses primary terms only, so duplicate OpenHalalan copies of HF officials (2004-2016) do not count as relatives.
3. Each person is counted once per town (and once per province), even if their ID holds two posts in the same year.
4. When two clans hold the same number of seats in a town, the top clan is the one with the lower clan ID, so the result is the same on every run.

## Steps

| Step | What it does |
|---|---|
| 1 | Loads the Task 7 outputs |
| 2 | Marks each official as dynastic and fat dynasty or not, per election |
| 3 | Town table: stronghold %, dynastic mayor, top clan, fat dynasty town, city flag, stronghold level |
| 4 | Province table: provincial officials, governor, fat dynasty share, and a summary of the province's towns |
| 5 | Benchmark checks against PCIJ and the Ateneo Policy Center |
| 6 | Writes the curated tables, partitioned by election year |

## Curated outputs

All in `data/curated`, one folder per election year (`year=1988`, ..., `year=2025`, 13 folders). Each run deletes and rewrites the folders, so re-running never creates duplicates.

| Table | Rows | One row per |
|---|---|---|
| `town_dynasty_stronghold/` | 20,764 | town x election |
| `province_dynasty_stronghold/` | 1,021 | province x election |
| `official_terms_dynastic/` | 225,300 | official x election |

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
| `source` | `ateneo` (1988-1998), `hf` (2004-2016) or `openhalalan` (2001, 2019-2025) |

### province_dynasty_stronghold

| Column | Meaning |
|---|---|
| `year`, `province_std` | Election and province |
| `n_provincial_officials`, `n_dynastic`, `provincial_dynastic_share` | Governor, vice governor, board members |
| `governor_uid`, `governor_dynastic` | The governor, and whether they are dynastic |
| `n_towns`, `avg_town_dynastic_share`, `share_towns_dynastic_mayor`, `n_stronghold_towns` | Summary of the province's towns |
| `fat_dynasty_share` | Share of all the province's officials (local, provincial, House) who are fat dynasty officials |

### official_terms_dynastic

`person_uid`, `year`, `position`, `province_std`, `town_std`, `party`, `source`, `is_dynastic`, `is_fat_dynasty`, `first_relative_year`, `clan_id`. Join to `data/staging/politicians.parquet` on `person_uid` for names.

## Results

### All officials

| Year | Officials | Source | Dynastic | Fat dynasty |
|---|---|---|---|---|
| 1988 | 16,623 | Ateneo | 8.2% | 7.0% |
| 1992 | 17,028 | Ateneo | 18.3% | 10.5% |
| 1995 | 17,273 | Ateneo | 23.9% | 12.4% |
| 1998 | 17,221 | Ateneo | 29.9% | 13.2% |
| 2001 | 17,489 | OpenHalalan | 35.4% | 14.8% |
| 2004 | 17,371 | HF | 40.9% | 17.7% |
| 2007 | 16,609 | HF | 46.2% | 19.9% |
| 2010 | 17,506 | HF | 50.7% | 23.3% |
| 2013 | 17,161 | HF | 52.6% | 23.5% |
| 2016 | 17,593 | HF | 53.4% | 23.4% |
| 2019 | 17,792 | OpenHalalan | 67.0% | 25.3% |
| 2022 | 17,817 | OpenHalalan | 68.0% | 25.5% |
| 2025 | 17,817 | OpenHalalan | 68.8% | 26.6% |

### Towns

| Year | Towns | Avg stronghold % | Dynastic mayors | Fat dynasty towns | Stronghold towns (75%+) |
|---|---|---|---|---|---|
| 1988 | 1,568 | 7.6% | 17.0% | 18.6% | 0.0% |
| 1992 | 1,577 | 17.5% | 30.4% | 27.6% | 0.1% |
| 1995 | 1,598 | 23.2% | 39.3% | 31.5% | 0.3% |
| 1998 | 1,585 | 29.0% | 48.1% | 29.5% | 1.1% |
| 2001 | 1,605 | 34.4% | 56.0% | 31.0% | 2.4% |
| 2004 | 1,591 | 40.0% | 62.4% | 34.4% | 3.0% |
| 2007 | 1,513 | 45.4% | 66.9% | 36.2% | 5.8% |
| 2010 | 1,627 | 50.2% | 71.9% | 44.8% | 11.1% |
| 2013 | 1,592 | 52.5% | 73.3% | 48.3% | 13.6% |
| 2016 | 1,603 | 54.7% | 73.9% | 47.4% | 15.4% |
| 2019 | 1,634 | 66.4% | 84.4% | 53.2% | 35.7% |
| 2022 | 1,634 | 67.6% | 86.4% | 57.2% | 34.9% |
| 2025 | 1,637 | 68.1% | 85.7% | 60.0% | 36.7% |

Most dynastic provinces in 2025 (average town stronghold %): Biliran (85.0%), Northern Samar (81.7%), Batanes (81.7%), Masbate (80.5%), Abra (78.9%), Cebu (76.0%, with 28 stronghold towns).

Highest single-clan control in 2025: 6 of 10 local seats held by one clan in Picong (Balindong clan) and Tagoloan II (Capal clan), both in Lanao del Sur.

## Benchmark checks

### PCIJ

| | Cities with a dynastic mayor | Provinces with a dynastic governor |
|---|---|---|
| 2013 | 76.2% | 83.8% |
| 2016 | 77.2% | 79.7% |
| 2019 | 87.1% | 72.8% |
| 2022 | 89.3% | 79.0% |
| 2025 | 89.9% | 80.5% |
| **PCIJ** | **75.8%** (113 of 149) | **86.6%** (71 of 82) |

Cities in 2013-2016 are within 1.5 percentage points of PCIJ, and provinces in 2013 within 3 points. PCIJ's method is not identical to ours, so ranges are compared, not one exact year.

### Ateneo Policy Center (fat dynasty share per province)

866 province-years compared (1992-2022). Overall correlation: **0.676**.

| Year | Provinces | Our average | Ateneo average | Correlation |
|---|---|---|---|---|
| 1992 | 74 | 10.1% | 19.7% | 0.646 |
| 1995 | 76 | 11.7% | 21.9% | 0.694 |
| 1998 | 78 | 12.9% | 21.1% | 0.653 |
| 2001 | 79 | 14.6% | 21.8% | 0.592 |
| 2004 | 79 | 16.8% | 22.2% | 0.678 |
| 2007 | 80 | 19.4% | 22.3% | 0.552 |
| 2010 | 78 | 22.3% | 24.9% | 0.692 |
| 2013 | 80 | 23.3% | 26.3% | 0.745 |
| 2016 | 80 | 23.3% | 26.9% | 0.727 |
| 2019 | 81 | 25.2% | 27.6% | 0.669 |
| 2022 | 81 | 25.1% | 28.7% | 0.761 |

The provinces rank in a similar order. Our shares are lower because Ateneo counts everyone with the same surname, while we skip common surnames that fail the chance test (see `docs/task7_kinship.md`, Step 12). The gap shrinks over time, as more of each family's history comes into view.

## Known limitations

- **Left-censoring:** the data starts in 1988 (only House members go back further, through the roster). Relatives who served before 1988 are invisible, so early years look less dynastic than they were. The rise over time is partly real and partly this effect.
- **Source changes:** Ateneo (1988-1998) has no middle names, so mother's-side relatives are only found for people who also appear in later years. OpenHalalan (2019-2025) often uses ballot nicknames (e.g. "PACOY" for Francisco), so some people are split into two IDs across the 2016 to 2019 change, which raises later shares. **Compare years within one source** (1988-1998, 2004-2016, or 2019-2025) for trends.
- **Towns without a location:** 1,601 HF local rows (2013, 2016) have no town after Task 6's backfill, so those officials are not in the town table.
- **Province splits:** towns and officials are counted under the province of that election. New provinces (e.g. Maguindanao del Norte and del Sur from 2022) start a new time series, and their families can form clans separate from the older province's clans (see Task 7 limitations).
- **Cities:** `is_city` finds 140 cities from HF labels (the official count is around 149).
- **Council size varies:** most towns have 10 local officials, large cities more, so a 75% share means different seat counts in different places.
- Kinship itself is name-based (see `docs/task7_kinship.md`), so "dynastic" means "has a likely relative in office".