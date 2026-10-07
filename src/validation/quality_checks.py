"""Automated data quality test suite for staged datasets."""

import sys
from pathlib import Path
from typing import Callable, List, Tuple
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STAGING = PROJECT_ROOT / "data" / "staging"


class DataQualityChecker:
    def __init__(self, staging_dir: Path = STAGING):
        self.staging_dir = staging_dir
        self.results: List[Tuple[str, str, str]] = []
        self._load_datasets()

    def _load_datasets(self):
        print(f"Loading staged datasets from: {self.staging_dir}")
        self.persons = pd.read_parquet(self.staging_dir / "hf_persons_clean.parquet")
        self.memberships = pd.read_parquet(self.staging_dir / "hf_memberships_clean.parquet")
        self.winners = pd.read_parquet(self.staging_dir / "openhalalan_winners_clean.parquet")
        self.roster = pd.read_parquet(self.staging_dir / "roster_legislators_clean.parquet")
        self.psa = pd.read_parquet(self.staging_dir / "psa_poverty_clean.parquet")
        self.ateneo = pd.read_parquet(self.staging_dir / "ateneo_politicians_clean.parquet")
        self.ateneo_shares = pd.read_parquet(self.staging_dir / "ateneo_province_shares_clean.parquet")

    def _record(self, check_name: str, passed: bool, details: str):
        status = "PASSED" if passed else "FAILED"
        self.results.append((check_name, status, details))
        mark = "✓" if passed else "✗"
        print(f"[{mark}] {check_name}: {details}")

    def check_primary_key_uniqueness(self):
        """DQ-1: Primary key uniqueness across base entity tables."""
        persons_unique = self.persons["id"].is_unique
        memberships_unique = self.memberships["id"].is_unique
        passed = persons_unique and memberships_unique
        details = (
            f"hf_persons duplicates: {self.persons['id'].duplicated().sum()} | "
            f"hf_memberships duplicates: {self.memberships['id'].duplicated().sum()}"
        )
        self._record("DQ-1: Entity Primary Key Uniqueness", passed, details)

    def check_referential_integrity(self):
        """DQ-2: Foreign key linkage from memberships to persons."""
        orphan_mask = ~self.memberships["person_id"].isin(self.persons["id"])
        orphan_count = orphan_mask.sum()
        passed = orphan_count == 0
        details = f"Orphaned membership records without person match: {orphan_count}"
        self._record("DQ-2: Referential Integrity (Memberships -> Persons)", passed, details)

    def check_position_and_source_domains(self):
        """DQ-3: Categorical domain adherence for position and backfill source."""
        valid_sources = {
            "original",
            "history",
            "openhalalan_t1",
            "openhalalan_t2",
            "openhalalan_xyear",
            "shift_revoked",
            "unfilled",
            "not_applicable",
        }
        invalid_sources = set(self.memberships["locality_source"].dropna()) - valid_sources
        
        valid_positions = {
            "COUNCILOR",
            "MAYOR",
            "VICE MAYOR",
            "MEMBER, HOUSE OF REPRESENTATIVES",
            "GOVERNOR",
            "VICE GOVERNOR",
            "BOARD MEMBER",
            "PROVINCIAL BOARD MEMBER",
            "PRESIDENT",
            "VICE PRESIDENT",
            "SENATOR",
        }
        invalid_positions = set(self.memberships["position"].dropna()) - valid_positions

        passed = (len(invalid_sources) == 0) and (len(invalid_positions) == 0)
        details = (
            f"Invalid sources: {list(invalid_sources) if invalid_sources else 'None'} | "
            f"Invalid positions: {list(invalid_positions) if invalid_positions else 'None'}"
        )
        self._record("DQ-3: Categorical Domain Validity", passed, details)

    def check_temporal_bounds(self):
        """DQ-4: Temporal bounds for election cycles and legislative tenures."""
        # Memberships must be within the post-1987 democratic era
        valid_years = self.memberships["year"].between(1987, 2025).all()
        invalid_years = (~self.memberships["year"].between(1987, 2025)).sum()

        # Check legislative tenures: modern era (>= 1987) must have start_year <= end_year
        has_both_years = self.roster.dropna(subset=["start_year", "end_year"])
        modern_tenures = has_both_years[has_both_years["start_year"] >= 1987]
        invalid_modern = (modern_tenures["start_year"] > modern_tenures["end_year"]).sum()

        # Historical archival anomalies (pre-1987)
        total_invalid = (has_both_years["start_year"] > has_both_years["end_year"]).sum()

        passed = valid_years and (invalid_modern == 0)
        details = (
            f"Out-of-bound membership years: {invalid_years} | "
            f"Modern tenure violations (>=1987): {invalid_modern} | "
            f"Pre-1987 archival anomalies: {total_invalid}"
        )
        self._record("DQ-4: Temporal Bounds and Chronological Logic", passed, details)

    def check_locality_backfill_integrity(self):
        """DQ-5: Non-null locality checks for filled municipal positions."""
        filled_sources = ["original", "history", "openhalalan_t1", "openhalalan_t2", "openhalalan_xyear"]
        filled_mask = self.memberships["locality_source"].isin(filled_sources)
        null_localities = self.memberships.loc[filled_mask, "locality_std"].isna().sum()

        # Every resolved locality must have a non-null province
        has_locality = self.memberships["locality_std"].notna()
        missing_provinces = self.memberships.loc[has_locality, "province_std"].isna().sum()

        passed = (null_localities == 0) and (missing_provinces == 0)
        details = f"Missing locality in filled rows: {null_localities} | Missing province with known town: {missing_provinces}"
        self._record("DQ-5: Locality and Province Co-occurrence", passed, details)

    def check_poverty_metric_ranges(self):
        """DQ-6: Statistical bounds for PSA poverty indicators."""
        metric_col = "poverty_incidence" if "poverty_incidence" in self.psa.columns else "headcount_ratio"
        if metric_col not in self.psa.columns:
            # Fallback to identify floating-point percentage columns
            float_cols = self.psa.select_dtypes(include=["float64", "float32"]).columns
            metric_col = float_cols[0] if len(float_cols) > 0 else None

        if metric_col:
            out_of_bounds = (~self.psa[metric_col].dropna().between(0, 100)).sum()
            passed = out_of_bounds == 0
            details = f"Column '{metric_col}' out-of-range values (<0 or >100): {out_of_bounds}"
        else:
            passed = False
            details = "No poverty metric column identified for boundary testing."

        self._record("DQ-6: Poverty Metric Statistical Range", passed, details)

    def check_ateneo_keys_and_links(self):
        """DQ-7: Ateneo row ids are unique, and every HF link points to an existing HF row of the same person."""
        bad_ids = self.ateneo["ateneo_row_id"].isna().sum() + self.ateneo["ateneo_row_id"].duplicated().sum()
        links = self.ateneo.dropna(subset=["hf_membership_id"])
        hf_person = self.memberships.set_index("id")["person_id"]
        reused = links["hf_membership_id"].duplicated().sum()
        missing = (~links["hf_membership_id"].isin(hf_person.index)).sum()
        other_person = (links["person_id"] != links["hf_membership_id"].map(hf_person)).sum()
        link_rate = self.ateneo.loc[self.ateneo["year"].between(2004, 2016), "hf_membership_id"].notna().mean()

        passed = (bad_ids == 0) and (reused == 0) and (missing == 0) and (other_person == 0) and (link_rate >= 0.99)
        details = (
            f"Missing or duplicate row ids: {bad_ids} | HF rows linked twice: {reused} | "
            f"Links to missing HF rows: {missing} | Person differs from HF: {other_person} | "
            f"2004-2016 rows linked: {link_rate:.2%}"
        )
        self._record("DQ-7: Ateneo Keys and HF Links", passed, details)

    def check_ateneo_towns(self):
        """DQ-8: Ateneo town sources are valid, and a row has a town exactly when its source found one."""
        found_sources = {"original", "history", "openhalalan_t1", "openhalalan_t2", "openhalalan_xyear"}
        valid_sources = found_sources | {"unfilled", "not_applicable"}
        invalid_sources = set(self.ateneo["town_source"].dropna()) - valid_sources
        town_found = self.ateneo["town_source"].isin(found_sources)
        mismatched = (town_found != self.ateneo["town_std"].notna()).sum()
        bad_years = (~self.ateneo["year"].between(1987, 2022)).sum()
        unconfirmed = self.ateneo["town_verified"].eq(False).sum()

        passed = (len(invalid_sources) == 0) and (mismatched == 0) and (bad_years == 0)
        details = (
            f"Invalid town sources: {sorted(invalid_sources) if invalid_sources else 'None'} | "
            f"Town present or missing against its source: {mismatched} | Out-of-range years: {bad_years} | "
            f"Towns no other source confirms (reviewed in notebook 07): {unconfirmed}"
        )
        self._record("DQ-8: Ateneo Town Sources and Completeness", passed, details)

    def check_ateneo_province_shares(self):
        """DQ-9: Ateneo's province shares are percentages and match a recount from the politicians table."""
        shares = self.ateneo_shares.dropna(subset=["fat_dynasty_share_pct"])
        out_of_range = (~shares["fat_dynasty_share_pct"].between(0, 100)).sum()
        duplicates = self.ateneo_shares.duplicated(["province", "year"]).sum()
        recount = self.ateneo.groupby(["province", "year"])["is_fat_dynasty"].mean().mul(100)
        sheet = shares.set_index(["province", "year"])["fat_dynasty_share_pct"]
        gap = (recount.reindex(sheet.index) - sheet).abs()
        not_recounted = gap.isna().sum()

        passed = (out_of_range == 0) and (duplicates == 0) and (not_recounted == 0) and (gap.max() < 0.001)
        details = (
            f"Shares outside 0-100: {out_of_range} | Duplicate province-years: {duplicates} | "
            f"Province-years not recounted: {not_recounted} | Largest gap vs recount: {gap.max():.6f}"
        )
        self._record("DQ-9: Ateneo Province Shares vs Recount", passed, details)

    def run_all(self) -> bool:
        print("\n" + "=" * 60)
        print("RUNNING AUTOMATED DATA QUALITY CHECKS")
        print("=" * 60)
        self.check_primary_key_uniqueness()
        self.check_referential_integrity()
        self.check_position_and_source_domains()
        self.check_temporal_bounds()
        self.check_locality_backfill_integrity()
        self.check_poverty_metric_ranges()
        self.check_ateneo_keys_and_links()
        self.check_ateneo_towns()
        self.check_ateneo_province_shares()
        print("=" * 60)

        all_passed = all(status == "PASSED" for _, status, _ in self.results)
        if all_passed:
            print("ALL DATA QUALITY CHECKS PASSED SUCCESSFULLY.")
        else:
            print("DATA QUALITY CHECKS FAILED.")
        return all_passed


if __name__ == "__main__":
    checker = DataQualityChecker()
    success = checker.run_all()
    sys.exit(0 if success else 1)