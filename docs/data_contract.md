## 1. Pipeline Ownership & Service Level Agreement
* **Project:** Philippine Political Dynasty Analytics & Network Resilience Pipeline
* **Owner:** Team Alpha
* **Execution Engine:** Apache Airflow (`ph_dynasty_end_to_end_etl`)
* **Cadence:** Ad-hoc / Manual Trigger (Historical static datasets)
* **Target Destination:** PostgreSQL Database (`dynasty_db`)

## 2. Upstream Data Sources & Ingestion Guarantees
The pipeline depends on the following external sources. If a source API or endpoint fails, the pipeline will fall back to local cached `.parquet` or `.csv` stubs if `ALLOW_FALLBACK=1`.

| Source System | Format | Expected Volume | Owner / Provider |
| :--- | :--- | :--- | :--- |
| BetterGov.PH Dataset | Parquet | ~130,000 rows | Hugging Face Hub |
| Ateneo Policy Center Dataset (2022) | Excel (`.xlsx`) | ~207,000 rows | Ateneo School of Government |
| OpenHalalan Dataset | CSV | ~150,000 rows | GitHub Releases |
| PSA OpenSTAT Poverty | JSON | 82 Provincial records | PSA API Endpoint |

## 3. Staging Data Schema (Input to PostgreSQL Loader)
Before data is loaded into PostgreSQL, the transformation layer (`clean_backfill.py`) guarantees the following cleaned standard output structure in the curated `.parquet` files:

### Curated Politicians (`curated_politicians.parquet`)
| Column | Data Type | Constraint |
| :--- | :--- | :--- |
| `person_id` | STRING | NOT NULL, UNIQUE, Primary Key format (UUID) |
| `first_name` | STRING | NOT NULL, UPPERCASE |
| `last_name` | STRING | NOT NULL, UPPERCASE |

### Curated Memberships (`curated_memberships.parquet`)
| Column | Data Type | Constraint |
| :--- | :--- | :--- |
| `person_id` | STRING | NOT NULL, Foreign Key to `person_id` |
| `year` | INTEGER | NOT NULL, BETWEEN 1900 AND 2025 |
| `position` | STRING | NOT NULL, Standardized title (e.g., "MAYOR") |
| `province_std` | STRING | NOT NULL, UPPERCASE |
| `town_std` | STRING | NOT NULL, UPPERCASE, Defaults to "PROVINCIAL WIDE" |
| `source` | STRING | Enum: `HF`, `ATENEO_2022`, `OPENHALALAN` |

## 4. Quality Rules & Thresholds (`quality_checks.py`)
The pipeline will abort and log a failure if the following data assertions are not met post-transformation:
1. **Row Count Assertion:** Curated membership records must exceed 300,000 total rows after combining Ateneo, HF, and OpenHalalan data.
2. **Deduplication:** Overlapping election years (e.g., 2004–2016) must not produce duplicate `(person_id, position, year, town_std)` entries.
3. **Geographic Nulls:** `province_std` cannot contain nulls. Missing municipalities must be coerced to `PROVINCIAL WIDE`.
4. **Kinship Coverage:** At least 25% of unique individuals must successfully map to a `clan_id` via the network graph logic.