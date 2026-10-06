"""Idempotent PostgreSQL Data Loader for Staged Philippine Dynasty Datasets."""

import os
import sys
from pathlib import Path
from typing import Dict, Tuple
from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STAGING = PROJECT_ROOT / "data" / "staging"
SQL_DIR = PROJECT_ROOT / "sql"

# Load credentials from .env file
load_dotenv(PROJECT_ROOT / ".env")

PG_USER = os.getenv("POSTGRES_USER", "postgres")
PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
PG_DB = os.getenv("POSTGRES_DB", "dynasty_db")
PG_PORT = os.getenv("POSTGRES_PORT", "5432")

# If running on Windows host terminal, connect via localhost; inside Docker, use 'postgres'
PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
if PG_HOST == "postgres" and sys.platform == "win32":
    PG_HOST = "localhost"

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}",
)


class PostgresLoader:
    def __init__(self, db_url: str = DATABASE_URL, staging_dir: Path = STAGING):
        self.engine = create_engine(db_url, pool_pre_ping=True)
        self.staging_dir = staging_dir

    def init_schema(self, schema_file: Path = SQL_DIR / "init_schema.sql"):
        """Execute DDL statements to construct tables, constraints, and indexes."""
        print(f"Applying schema DDL from {schema_file}...")
        with open(schema_file, "r", encoding="utf-8") as f:
            ddl_sql = f.read()

        with self.engine.begin() as conn:
            conn.execute(text(ddl_sql))
        print("Schema successfully initialized.")

    def load_dim_geography(self) -> Dict[Tuple[str, str], int]:
        """Aggregate all distinct (province, town) pairs and upsert into dim_geography."""
        print("Extracting and loading dim_geography...")
        memberships = pd.read_parquet(self.staging_dir / "hf_memberships_clean.parquet")
        winners = pd.read_parquet(self.staging_dir / "openhalalan_winners_clean.parquet")
        psa = pd.read_parquet(self.staging_dir / "psa_poverty_clean.parquet")

        pairs = pd.concat([
            memberships[["province_std", "locality_std"]].rename(columns={"locality_std": "town_std"}),
            winners[["province_std", "town_std"]],
            psa[["province_std", "town_std"]],
        ]).dropna(subset=["province_std"]).drop_duplicates()

        pairs["town_std"] = pairs["town_std"].where(pairs["town_std"].notna(), None)
        records = pairs.to_dict(orient="records")

        with self.engine.begin() as conn:
            for row in records:
                query = text("""
                    INSERT INTO dim_geography (province_std, town_std)
                    VALUES (:province_std, :town_std)
                    ON CONFLICT (province_std, town_std) DO NOTHING;
                """)
                conn.execute(query, row)

        geo_df = pd.read_sql("SELECT location_id, province_std, town_std FROM dim_geography;", self.engine)
        geo_map = {
            (r["province_std"], r["town_std"]): r["location_id"]
            for _, r in geo_df.iterrows()
        }
        print(f"dim_geography synchronized. Total entries: {len(geo_map)}")
        return geo_map

    def load_dim_person(self, chunksize: int = 5000):
        """Idempotently upsert biographical profiles into dim_person."""
        print("Loading dim_person...")
        persons = pd.read_parquet(self.staging_dir / "hf_persons_clean.parquet")

        # The exact columns expected by the SQL query
        expected_cols = ["id", "first_name", "last_name", "middle_name", "name_suffix", "sex", "sex_source", "suffix_suspect"]

        # 1. Ensure all expected columns exist in the dataframe. Add as None if missing.
        for col in expected_cols:
            if col not in persons.columns:
                persons[col] = None

        # 2. Select only the expected columns and rename 'id' to 'person_id'
        df = persons[expected_cols].copy().rename(columns={"id": "person_id"})

        # 3. Strictly replace pandas NA/NaN values with Python None for PostgreSQL compatibility
        import numpy as np
        df = df.replace({np.nan: None, pd.NA: None})
        df = df.where(df.notnull(), None)

        records = df.to_dict(orient="records")

        with self.engine.begin() as conn:
            for i in range(0, len(records), chunksize):
                batch = records[i:i + chunksize]
                query = text("""
                    INSERT INTO dim_person (
                        person_id, first_name, last_name, middle_name, name_suffix, sex, sex_source, suffix_suspect
                    ) VALUES (
                        :person_id, :first_name, :last_name, :middle_name, :name_suffix, :sex, :sex_source, :suffix_suspect
                    )
                    ON CONFLICT (person_id) DO UPDATE SET
                        first_name = EXCLUDED.first_name,
                        last_name = EXCLUDED.last_name,
                        middle_name = EXCLUDED.middle_name,
                        name_suffix = EXCLUDED.name_suffix,
                        sex = EXCLUDED.sex,
                        suffix_suspect = EXCLUDED.suffix_suspect,
                        updated_at = CURRENT_TIMESTAMP;
                """)
                conn.execute(query, batch)
        print(f"dim_person loaded ({len(records)} rows).")

    def load_fact_memberships(self, geo_map: Dict[Tuple[str, str], int], chunksize: int = 5000):
        """Map foreign keys and upsert historical electoral memberships."""
        print("Loading fact_electoral_membership...")
        df = pd.read_parquet(self.staging_dir / "hf_memberships_clean.parquet")

        df["location_id"] = [geo_map.get((p, t)) for p, t in zip(df["province_std"], df["locality_std"])]

        load_cols = ["id", "person_id", "location_id", "year", "position", "locality_source"]
        df_load = df[load_cols].rename(columns={"id": "membership_id"}).copy()
        
        # Strictly cast to native Python types and handle NaNs
        import numpy as np
        df_load["location_id"] = df_load["location_id"].apply(lambda x: int(x) if pd.notnull(x) else None)
        df_load["year"] = df_load["year"].apply(lambda x: int(x) if pd.notnull(x) else None)
        
        # Drop dirty duplicates to respect the PostgreSQL unique constraint
        df_load = df_load.drop_duplicates(subset=["person_id", "year", "position"], keep="first")
        
        df_load = df_load.replace({np.nan: None, pd.NA: None})
        df_load = df_load.where(df_load.notnull(), None)
        
        records = df_load.to_dict(orient="records")

        with self.engine.begin() as conn:
            for i in range(0, len(records), chunksize):
                batch = records[i:i + chunksize]
                query = text("""
                    INSERT INTO fact_electoral_membership (
                        membership_id, person_id, location_id, year, position, locality_source
                    ) VALUES (
                        :membership_id, :person_id, :location_id, :year, :position, :locality_source
                    )
                    ON CONFLICT (membership_id) DO UPDATE SET
                        location_id = EXCLUDED.location_id,
                        locality_source = EXCLUDED.locality_source;
                """)
                conn.execute(query, batch)
        print(f"fact_electoral_membership loaded ({len(records)} rows).")

    def load_fact_poverty(self, geo_map: Dict[Tuple[str, str], int]):
        """Load PSA poverty indicators linked by geographic jurisdiction."""
        print("Loading fact_poverty_metric...")
        psa = pd.read_parquet(self.staging_dir / "psa_poverty_clean.parquet")

        psa["location_id"] = [geo_map.get((p, t)) for p, t in zip(psa["province_std"], psa["town_std"])]
        incidence_col = "poverty_incidence" if "poverty_incidence" in psa.columns else "headcount_ratio"

        df_load = psa[["location_id", "year", "area_key", "level", incidence_col, "is_city", "is_combined_area"]].copy()
        df_load = df_load.rename(columns={incidence_col: "poverty_incidence"})
        
        # Strictly cast to native Python types and handle NaNs
        import numpy as np
        df_load["location_id"] = df_load["location_id"].apply(lambda x: int(x) if pd.notnull(x) else None)
        df_load["year"] = df_load["year"].apply(lambda x: int(x) if pd.notnull(x) else None)
        df_load["poverty_incidence"] = df_load["poverty_incidence"].apply(lambda x: float(x) if pd.notnull(x) else None)
        
        df_load = df_load.replace({np.nan: None, pd.NA: None})
        df_load = df_load.where(df_load.notnull(), None)
        
        records = df_load.to_dict(orient="records")

        with self.engine.begin() as conn:
            for row in records:
                query = text("""
                    INSERT INTO fact_poverty_metric (
                        location_id, year, area_key, level, poverty_incidence, is_city, is_combined_area
                    ) VALUES (
                        :location_id, :year, :area_key, :level, :poverty_incidence, :is_city, :is_combined_area
                    )
                    ON CONFLICT (location_id, year, area_key) DO UPDATE SET
                        poverty_incidence = EXCLUDED.poverty_incidence;
                """)
                conn.execute(query, row)
        print(f"fact_poverty_metric loaded ({len(records)} rows).")

    def run_all(self):
        print("STARTING POSTGRESQL IDEMPOTENT ETL LOAD")
        self.init_schema()
        geo_map = self.load_dim_geography()
        self.load_dim_person()
        self.load_fact_memberships(geo_map)
        self.load_fact_poverty(geo_map)
        print("ALL TABLES LOADED SUCCESSFULLY.")


if __name__ == "__main__":
    loader = PostgresLoader()
    loader.run_all()