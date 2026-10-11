import sys
import numpy as np
import pandas as pd
import shutil
from pathlib import Path

sys.path.insert(0, ".")

S = "data/staging/"
C = "data/curated/"

people = pd.read_parquet(S + "politicians.parquet")
terms = pd.read_parquet(S + "politician_terms.parquet")
edges = pd.read_parquet(S + "kinship_edges.parquet")
clans = pd.read_parquet(S + "clans.parquet")
memberships = pd.read_parquet(S + "hf_memberships_clean.parquet")   # used to know which towns are cities

ELECTION_YEARS = [1988, 1992, 1995, 1998, 2001, 2004, 2007, 2010, 2013, 2016, 2019, 2022, 2025]
LOCAL = ["MAYOR", "VICE MAYOR", "COUNCILOR"]
PROVINCIAL = ["GOVERNOR", "VICE GOVERNOR", "PROVINCIAL BOARD MEMBER"]
print(f"people: {len(people):,} | terms: {len(terms):,} | kinship links: {len(edges):,} | clans: {len(clans):,}")

info = people.set_index("person_uid")

# Strong/medium links, without same-name "twins" (probably one person under two IDs)
sm = edges[edges["tier"].isin(["strong", "medium"])]
A, B = info.loc[sm["person_a"]], info.loc[sm["person_b"]]
same_name = (A["last_key"].to_numpy() == B["last_key"].to_numpy()) & (A["first_key"].to_numpy() == B["first_key"].to_numpy())
mid_ok = A["middle_key"].isna().to_numpy() | B["middle_key"].isna().to_numpy() | (A["middle_key"].to_numpy() == B["middle_key"].to_numpy())
twin = same_name & mid_ok
sm = sm[~twin]
print(f"links skipped as possible same-person twins: {twin.sum():,}")

# For each person: the earliest year any of their relatives held office (primary terms only)
first_primary_year = terms[terms["is_primary"]].groupby("person_uid")["year"].min()
pairs = pd.concat([sm[["person_a", "person_b"]].set_axis(["person_uid", "relative"], axis=1),
                   sm[["person_b", "person_a"]].set_axis(["person_uid", "relative"], axis=1)])
pairs["relative_first_year"] = pairs["relative"].map(first_primary_year)
first_relative_year = pairs.groupby("person_uid")["relative_first_year"].min()

# One row per official per election: dynastic if a relative was in office that year or earlier
t = terms[terms["is_primary"] & terms["year"].isin(ELECTION_YEARS)].copy()
t["first_relative_year"] = t["person_uid"].map(first_relative_year)
t["is_dynastic"] = t["first_relative_year"].le(t["year"]).fillna(False).astype(bool)
t["clan_id"] = t["person_uid"].map(info["clan_id"])

# "Fat dynasty" (Ateneo's definition): a relative holds office in the SAME province in the SAME year
held = t.dropna(subset=["province_std"])[["person_uid", "year", "province_std"]].drop_duplicates()
together = (pairs.merge(held, on="person_uid")
                 .merge(held.rename(columns={"person_uid": "relative"}), on=["relative", "year", "province_std"]))
fat_keys = set(zip(together["person_uid"], together["year"], together["province_std"]))
t["is_fat_dynasty"] = [k in fat_keys for k in zip(t["person_uid"], t["year"], t["province_std"])]

print(t.groupby("year").agg(officials=("person_uid", "size"), source=("source", lambda s: s.mode().iloc[0]),
                      dynastic_share=("is_dynastic", "mean"), fat_dynasty_share=("is_fat_dynasty", "mean")).round(3))

# Which towns are cities (HF writes them as "CITY OF ...")
city = memberships.loc[memberships["locality"].fillna("").str.upper().str.contains("CITY"), ["province_std", "locality_std"]]
city = set(map(tuple, city.dropna().drop_duplicates().to_numpy()))

# Local officials with a known town
loc = t[t["position"].isin(LOCAL)].dropna(subset=["town_std"])
keys = ["year", "province_std", "town_std"]

# Stronghold % per town and election
loc_people = loc.drop_duplicates(keys + ["person_uid"])   # count each person once per town (some IDs hold 2 posts)
town = loc_people.groupby(keys).agg(n_officials=("person_uid", "nunique"),
                                    n_dynastic=("is_dynastic", "sum")).reset_index()
town["dynastic_share"] = (town["n_dynastic"] / town["n_officials"]).round(3)

# Is the mayor dynastic?
mayor = loc[loc["position"].eq("MAYOR")].groupby(keys).agg(mayor_uid=("person_uid", "first"),
                                                          mayor_dynastic=("is_dynastic", "max")).reset_index()
town = town.merge(mayor, on=keys, how="left")
town["mayor_dynastic"] = town["mayor_dynastic"].astype("boolean")    # empty when no mayor is recorded

# The family (clan) holding the most seats in each town
top = (loc.dropna(subset=["clan_id"]).groupby(keys + ["clan_id"])["person_uid"].nunique().rename("top_clan_seats")
          .reset_index().sort_values(["top_clan_seats", "clan_id"], ascending=[False, True]).drop_duplicates(keys)
          .rename(columns={"clan_id": "top_clan_id"}))
town = town.merge(top, on=keys, how="left")
town["top_clan_seats"] = town["top_clan_seats"].fillna(0).astype(int)
town["top_clan_share"] = (town["top_clan_seats"] / town["n_officials"]).round(3)
town["top_clan_label"] = town["top_clan_id"].map(clans.set_index("clan_id")["clan_label"])
town["fat_dynasty"] = town["top_clan_seats"] >= 2

town["is_city"] = [(p, c) in city for p, c in zip(town["province_std"], town["town_std"])]
town["stronghold_level"] = pd.cut(town["dynastic_share"], [-0.01, 0.25, 0.5, 0.75, 1.0],
                                  labels=["low (0-25%)", "moderate (25-50%)", "high (50-75%)", "stronghold (75-100%)"])
town["source"] = np.select([town["year"].lt(2001), town["year"].between(2004, 2016)], ["ateneo", "hf"], default="openhalalan")

print(f"town-year rows: {len(town):,}")
print(town.groupby("year").agg(
    towns=("town_std", "size"),
    avg_dynastic_share=("dynastic_share", "mean"),
    dynastic_mayor=("mayor_dynastic", "mean"),
    fat_dynasty=("fat_dynasty", "mean"),
    strongholds=("stronghold_level", lambda s: (s == "stronghold (75-100%)").mean())).round(3))

# Towns where ONE family holds the biggest share of seats (2025)
print(town[town["year"].eq(2025)].sort_values(["top_clan_share", "n_officials"], ascending=False)[
    ["province_std", "town_std", "n_officials", "dynastic_share", "top_clan_label", "top_clan_seats", "top_clan_share"]].head(10))

pv = t[t["position"].isin(PROVINCIAL)].dropna(subset=["province_std"])
pk = ["year", "province_std"]

# Provincial officials (governor, vice governor, board members)
pv_people = pv.drop_duplicates(pk + ["person_uid"])   # count each person once per province
prov_tbl = pv_people.groupby(pk).agg(n_provincial_officials=("person_uid", "nunique"),
                                     n_dynastic=("is_dynastic", "sum")).reset_index()
prov_tbl["provincial_dynastic_share"] = (prov_tbl["n_dynastic"] / prov_tbl["n_provincial_officials"]).round(3)

# Is the governor dynastic?
gov = pv[pv["position"].eq("GOVERNOR")].groupby(pk).agg(governor_uid=("person_uid", "first"),
                                                       governor_dynastic=("is_dynastic", "max")).reset_index()

# Summary of the province's towns (from Step 3)
towns_sum = town.groupby(pk).agg(n_towns=("town_std", "size"),
                                 share_towns_dynastic_mayor=("mayor_dynastic", "mean"),
                                 avg_town_dynastic_share=("dynastic_share", "mean"),
                                 n_stronghold_towns=("stronghold_level", lambda s: (s == "stronghold (75-100%)").sum())).reset_index()

# Fat dynasty share over ALL officials in the province (local + provincial + House), Ateneo's definition
fat = t.dropna(subset=["province_std"]).groupby(pk)["is_fat_dynasty"].mean().rename("fat_dynasty_share").round(3).reset_index()
prov_tbl = prov_tbl.merge(gov, on=pk, how="left").merge(towns_sum, on=pk, how="left").merge(fat, on=pk, how="left")
prov_tbl["governor_dynastic"] = prov_tbl["governor_dynastic"].astype("boolean")
cols = ["share_towns_dynastic_mayor", "avg_town_dynastic_share"]
prov_tbl[cols] = prov_tbl[cols].astype(float).round(3)

print(f"province-year rows: {len(prov_tbl):,}")
# The 10 most dynastic provinces in 2025 (by their towns)
print(prov_tbl[prov_tbl["year"].eq(2025)].sort_values("avg_town_dynastic_share", ascending=False)[
    ["province_std", "governor_dynastic", "provincial_dynastic_share", "n_towns", "avg_town_dynastic_share", "n_stronghold_towns", "fat_dynasty_share"]].head(10))

bench = pd.DataFrame({
    "cities_with_dynastic_mayor": town[town["is_city"]].groupby("year")["mayor_dynastic"].mean().astype(float),
    "provinces_with_dynastic_governor": prov_tbl.groupby("year")["governor_dynastic"].mean().astype(float)})
pcij = pd.DataFrame({"cities_with_dynastic_mayor": [113 / 149],
                     "provinces_with_dynastic_governor": [71 / 82]}, index=["PCIJ benchmark"])
print((pd.concat([bench, pcij]) * 100).round(1).astype(str).add("%"))

# Ateneo's fat dynasty share per province and year (cleaned in Task 6)
ap = pd.read_parquet(S + "ateneo_province_shares_clean.parquet")
ap["ateneo_fat_share"] = ap["fat_dynasty_share_pct"] / 100
cmp = prov_tbl[["year", "province_std", "fat_dynasty_share"]].merge(ap[["year", "province_std", "ateneo_fat_share"]], on=pk)
by_year = cmp.groupby("year").apply(lambda d: pd.Series({
    "provinces": len(d),
    "ours_avg": d["fat_dynasty_share"].mean(),
    "ateneo_avg": d["ateneo_fat_share"].mean(),
    "correlation": d["fat_dynasty_share"].corr(d["ateneo_fat_share"])})).round(3)
print(f"province-years compared: {len(cmp):,} | overall correlation: {cmp['fat_dynasty_share'].corr(cmp['ateneo_fat_share']):.3f}")
print(by_year)

out_dir = Path(C)
officials = t[["person_uid", "year", "position", "province_std", "town_std", "party", "source",
               "is_dynastic", "is_fat_dynasty", "first_relative_year", "clan_id"]].copy()

tables = {
    "town_dynasty_stronghold": town,
    "province_dynasty_stronghold": prov_tbl,
    "official_terms_dynastic": officials,
}
for name, df in tables.items():
    df = df.copy()
    df["year"] = df["year"].astype(int)                  # plain int so the year folders read back cleanly
    for col in df.select_dtypes("category").columns:     # e.g. stronghold_level
        df[col] = df[col].astype(str)
    out = out_dir / name
    if out.exists():
        shutil.rmtree(out)                               # rewrite cleanly each run (idempotent)
    df.to_parquet(out, partition_cols=["year"], index=False)
    parts = sorted(p.name for p in out.iterdir())
    print(f"{name:30s} {len(df):>8,} rows -> {C}{name}/  ({len(parts)} folders: {parts[0]} ... {parts[-1]})")

# Check: read back ONLY 2025 (this reads just one folder)
back = pd.read_parquet(out_dir / "town_dynasty_stronghold", filters=[("year", "=", 2025)])
print(f"\nread back year=2025 only: {len(back):,} towns")