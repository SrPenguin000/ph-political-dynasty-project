# Town-Level Dynasty Stronghold % & Curated Partitioning

Notebook: `notebooks/04_dynasty_stronghold.ipynb`

## How to run

Run after Task 7, because the notebook reads its outputs from `data/staging`:
`politicians.parquet`, `politician_terms.parquet`, `kinship_edges.parquet`, `clans.parquet`, plus two Task 6 files: `hf_memberships_clean.parquet` (used to find cities) and `ateneo_province_shares_clean.parquet` (used for the Ateneo benchmark).

Open the notebook and click **Run All**. It takes under a minute and writes 3 partitioned tables to `data/curated`.

## Definitions

- **Official:** an elected winner in a primary term (`is_primary == True` in `politician_terms`), in the elections 1988, 1992, 1995, 1998, 2001, 2004, ..., 2025.
- **Dynastic official (in a given year):** has at least one strong or medium relative (from `kinship_edges`) who first held office **in that year or earlier**. A relative who enters politics later does not count yet.
- **Fat dynasty official (Ateneo's definition):** has a strong or medium relative in office **in the same province in the same year**. Stricter than "dynastic".
- **Dynasty stronghold % (town):** dynastic local officials (mayor, vice mayor, councilors) / all local officials in that town and election.
- **Fat dynasty town:** one clan holds 2 or more local seats in the same town at the same time.

Safety measures when counting:

1. Links between two people with the same first and last name and no conflicting middle name are skipped (4,678 links). These are most likely one person under two IDs.
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
| `official_terms_dynastic/` | 225,314 | official x election |

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
| 1988 | 16,623 | Ateneo | 8.1% | 6.9% |
| 1992 | 17,029 | Ateneo | 18.1% | 10.3% |
| 1995 | 17,273 | Ateneo | 24.1% | 12.3% |
| 1998 | 17,221 | Ateneo | 29.9% | 13.0% |
| 2001 | 17,490 | OpenHalalan | 35.5% | 14.8% |
| 2004 | 17,372 | HF | 41.2% | 17.7% |
| 2007 | 16,610 | HF | 46.4% | 19.9% |
| 2010 | 17,507 | HF | 50.8% | 23.3% |
| 2013 | 17,164 | HF | 52.6% | 23.5% |
| 2016 | 17,595 | HF | 53.5% | 23.3% |
| 2019 | 17,793 | OpenHalalan | 67.1% | 25.3% |
| 2022 | 17,818 | OpenHalalan | 68.2% | 25.5% |
| 2025 | 17,819 | OpenHalalan | 68.6% | 26.6% |

### Towns

| Year | Towns | Avg stronghold % | Dynastic mayors | Fat dynasty towns | Stronghold towns (75%+) |
|---|---|---|---|---|---|
| 1988 | 1,568 | 7.5% | 16.6% | 18.6% | 0.0% |
| 1992 | 1,577 | 17.4% | 30.1% | 27.7% | 0.1% |
| 1995 | 1,598 | 23.4% | 39.4% | 31.7% | 0.4% |
| 1998 | 1,585 | 29.0% | 47.8% | 29.6% | 1.2% |
| 2001 | 1,605 | 34.5% | 56.0% | 31.0% | 2.2% |
| 2004 | 1,591 | 40.2% | 62.6% | 34.5% | 3.0% |
| 2007 | 1,513 | 45.6% | 67.0% | 36.2% | 5.9% |
| 2010 | 1,627 | 50.3% | 71.9% | 44.8% | 11.4% |
| 2013 | 1,592 | 52.6% | 73.4% | 48.3% | 13.8% |
| 2016 | 1,603 | 54.7% | 73.8% | 47.4% | 15.5% |
| 2019 | 1,634 | 66.5% | 84.5% | 53.3% | 36.0% |
| 2022 | 1,634 | 67.8% | 86.4% | 57.2% | 35.3% |
| 2025 | 1,637 | 67.9% | 85.6% | 60.1% | 36.9% |

Most dynastic provinces in 2025 (average town stronghold %): Biliran (85.0%), Batanes (83.3%), Northern Samar (81.7%), Masbate (80.5%), Abra (78.9%), Cebu (75.8%, with 28 stronghold towns).

Highest single-clan control in 2025: 7 of 10 local seats held by one clan in Ampatuan, Shariff Aguak and Talayan (all Maguindanao del Sur).

## Benchmark checks

### PCIJ

| | Cities with a dynastic mayor | Provinces with a dynastic governor |
|---|---|---|
| 2013 | 76.2% | 85.0% |
| 2016 | 76.4% | 81.0% |
| 2019 | 87.9% | 72.8% |
| 2022 | 90.0% | 77.8% |
| 2025 | 89.9% | 79.3% |
| **PCIJ** | **75.8%** (113 of 149) | **86.6%** (71 of 82) |

Cities in 2013-2016 are within 1 percentage point of PCIJ, and provinces in 2013 within 2 points. PCIJ's method is not identical to ours, so ranges are compared, not one exact year.

### Ateneo Policy Center (fat dynasty share per province)

866 province-years compared (1992-2022). Overall correlation: **0.676**.

| Year | Provinces | Our average | Ateneo average | Correlation |
|---|---|---|---|---|
| 1992 | 74 | 9.9% | 19.7% | 0.650 |
| 1995 | 76 | 11.6% | 21.9% | 0.711 |
| 1998 | 78 | 12.7% | 21.1% | 0.669 |
| 2001 | 79 | 14.5% | 21.8% | 0.598 |
| 2004 | 79 | 16.8% | 22.2% | 0.678 |
| 2007 | 80 | 19.4% | 22.3% | 0.553 |
| 2010 | 78 | 22.2% | 24.9% | 0.690 |
| 2013 | 80 | 23.2% | 26.3% | 0.734 |
| 2016 | 80 | 23.1% | 26.9% | 0.727 |
| 2019 | 81 | 25.2% | 27.6% | 0.669 |
| 2022 | 81 | 25.1% | 28.7% | 0.764 |

The provinces rank in a similar order. Our shares are lower because Ateneo counts everyone with the same surname, while we skip common surnames that fail the chance test (see `docs/task7_kinship.md`, Step 12). The gap shrinks over time, as more of each family's history comes into view.

## Known limitations

- **Left-censoring:** the data starts in 1988 (only House members go back further, through the roster). Relatives who served before 1988 are invisible, so early years look less dynastic than they were. The rise over time is partly real and partly this effect.
- **Source changes:** Ateneo (1988-1998) has no middle names, so mother's-side relatives are only found for people who also appear in later years. OpenHalalan (2019-2025) often uses ballot nicknames (e.g. "PACOY" for Francisco), so some people are split into two IDs across the 2016 to 2019 change, which raises later shares. **Compare years within one source** (1988-1998, 2004-2016, or 2019-2025) for trends.
- **Towns without a location:** 1,601 HF local rows (2013, 2016) have no town after Task 6's backfill, so those officials are not in the town table.
- **Province splits:** towns and officials are counted under the province of that election. New provinces (e.g. Maguindanao del Norte and del Sur from 2022) start a new time series, and their families can form clans separate from the older province's clans (see Task 7 limitations).
- **Cities:** `is_city` finds 140 cities from HF labels (the official count is around 149).
- **Council size varies:** most towns have 10 local officials, large cities more, so a 75% share means different seat counts in different places.
- Kinship itself is name-based (see `docs/task7_kinship.md`), so "dynastic" means "has a likely relative in office".

