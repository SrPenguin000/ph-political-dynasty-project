# Data Contract

This contract defines the strict SLA and data quality constraints enforced by `src/validation/quality_checks.py` prior to the PostgreSQL `load_data_warehouse` execution.

## 1. Delivery & Cadence

* **Trigger:** Apache Airflow DAG (`ph_dynasty_end_to_end_etl`).
* **Schedule:** `@monthly` execution to capture asynchronous API updates, COMELEC dispute resolutions, and special election results.
* **Idempotency Guarantee:** Upstream pipelines must write to local storage using Parquet partitions (`partition_cols=["year"]`). The PostgreSQL loader must utilize `ON CONFLICT DO UPDATE` (Upsert) logic for dimensions and `DELETE FROM ... WHERE year = X` before inserting fact partitions to prevent data duplication on reruns.

## 2. Schema & Type Enforcement

Data types exported from `pandas` must strict-cast to the database schema defined in the Data Dictionary.

* **No Implicit Type Casting:** Dates and years must evaluate to valid integers.
* **Boolean Flags:** All dynasty flags (`is_dynastic`, `is_fat_dynasty`, `mayor_dynastic`) must cast correctly to SQL `BOOLEAN` (True/False, not 1/0 strings).

## 3. Nullability & Uniqueness Constraints

If any of the following constraints are violated, the Airflow validation task will fail and abort the database load:

* **Primary Key Uniqueness:** `person_uid` in `dim_person` and `clan_id` in `dim_clan` must be strictly unique.
* **Mandatory Fields (Not Null):**
  * `year`, `position`, `province_std`, and `person_uid` must not contain nulls in `fact_electoral_membership`.
  * `display_name` must not be null in `dim_person`.
* **Foreign Key Referential Integrity:** Every `person_uid` present in `fact_electoral_membership` must exist in `dim_person`. Every `clan_id` assigned in `dim_person` must exist in `dim_clan`.

## 4. Business Logic Validation

* **Valid Years:** The `year` column in fact tables must only contain established Philippine election years within the scope (1988, 1992, 1995, 1998, 2001, 2004, 2007, 2010, 2013, 2016, 2019, 2022, 2025) or historical roster years >= 1907.
* **Position Vocabulary:** The `position` column must strictly conform to expected categorical titles (e.g., `MAYOR`, `VICE MAYOR`, `COUNCILOR`, `GOVERNOR`, `VICE GOVERNOR`, `PROVINCIAL BOARD MEMBER`, `MEMBER, HOUSE OF REPRESENTATIVES`).
* **Share Boundaries:** Columns representing percentages (`dynastic_share`, `top_clan_share`, `provincial_dynastic_share`) must evaluate to floats between `0.0` and `1.0`.