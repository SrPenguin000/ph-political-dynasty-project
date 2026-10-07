"""Task 6: clean the sources and backfill missing town-level localities.

Reads raw and staging inputs, standardizes names and places, fills missing
localities in HF memberships, and writes cleaned tables to data/staging.
"""

import re
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.transform.mappings import (
    HF_PROVINCE_MAP, ORDINAL_WORDS, PERIOD_MAP, PERIOD_TYPO_MAP, PROVINCE_TOWN_MAP,
    PSA_AREA_MAP, PSA_CITY_MAP, ROSTER_CITY_MAP, ROSTER_MISSING_PROVINCE,
    ROSTER_PROVINCE_MAP, TOWN_MAP,
)
from src.transform.normalize import (
    first_names_compatible, middle_names_agree, name_key, name_tokens, norm_town,
)

RAW = PROJECT_ROOT / "data" / "raw"
STAGING = PROJECT_ROOT / "data" / "staging"

TOWN_POSITIONS = ["MAYOR", "VICE MAYOR", "COUNCILOR"]
KEYS = ["year", "position", "province_std", "last_key"]  # same-year match
XKEYS = ["province_std", "last_key"]  # cross-year match
RELIABLE_YEARS = [2001, 2004, 2007, 2016, 2019, 2022, 2025]
MAX_TOWN_OFFICIALS = 16  # more than this in one OpenHalalan 2013 town = doubled by the shift
SHIFTED_YEARS = [2010, 2013]  # OpenHalalan years with the town-label shift
JOB_WORDS = {"MAYOR", "VICEMAYOR", "COUNCILOR", "GOVERNOR", "VICEGOVERNOR", "KAGAWAD", "BOARDMEMBER"}


def apply_town_maps(towns, provinces):
    """Standardize town names: norm_town, then TOWN_MAP, then PROVINCE_TOWN_MAP."""
    std = towns.map(norm_town, na_action="ignore").replace(TOWN_MAP)
    for (prov, town), new in PROVINCE_TOWN_MAP.items():
        std = std.mask(provinces.eq(prov) & std.eq(town), new)
    return std


def standardize_memberships(memberships):
    """Add province_std and locality_std to HF memberships."""
    df = memberships.copy()
    df["province_std"] = df["province"].replace(HF_PROVINCE_MAP)
    df["locality_std"] = apply_town_maps(df["locality"], df["province_std"])
    return df


def standardize_winners(winners):
    """Add town_std to OpenHalalan winners (its province names are already the standard)."""
    df = winners.copy()
    df["town_std"] = apply_town_maps(df["City"], df["Province"])
    return df


def prep_hf(rows, persons):
    """Attach person names and match keys to HF membership rows."""
    rows = rows.merge(persons, left_on="person_id", right_on="id", suffixes=("", "_person"))
    rows["last_key"] = rows["last_name"].map(name_key)
    rows["first_key"] = rows["first_name"].map(name_key)
    return rows


def prep_oh(winners, years):
    """OpenHalalan rows for the given years that have a town, with match keys."""
    rows = winners[winners["Year"].isin(years) & winners["town_std"].notna()].copy()
    rows = rows.rename(columns={"Year": "year", "Position": "position", "Province": "province_std"})
    rows["last_key"] = rows["Last Name"].map(name_key, na_action="ignore")
    rows["first_key"] = rows["First Name"].map(name_key, na_action="ignore")
    return rows.dropna(subset=["last_key", "first_key"])


def match_towns(hf_rows, oh_rows, keys=KEYS):
    """Tier 1 and Tier 2 matching. Returns the matched town and tier for each HF membership id."""
    t1 = hf_rows.merge(oh_rows[keys + ["first_key", "town_std"]], on=keys + ["first_key"], how="inner")
    t1 = t1.groupby("id").agg(n_towns=("town_std", "nunique"), town=("town_std", "first"))
    t1 = t1[t1["n_towns"] == 1].assign(tier="t1")

    rest = hf_rows[~hf_rows["id"].isin(t1.index)]
    cand = rest.merge(oh_rows[keys + ["First Name", "town_std"]], on=keys, how="inner")
    shared = [bool(name_tokens(a) & name_tokens(b)) for a, b in zip(cand["first_name"], cand["First Name"])]
    t2 = cand.loc[shared].groupby("id").agg(n_towns=("town_std", "nunique"), town=("town_std", "first"))
    t2 = t2[t2["n_towns"] == 1].assign(tier="t2")

    return pd.concat([t1, t2])[["town", "tier"]]


def backfill_localities(memberships, persons, winners):
    """Fill missing town-level localities in HF memberships and record how each was filled.

    Expects memberships from standardize_memberships and winners from standardize_winners.
    """
    df = memberships.copy()
    is_town = df["position"].isin(TOWN_POSITIONS)
    has_town = df["locality_std"].notna()

    # Label what is already known
    df["locality_source"] = None
    df.loc[has_town, "locality_source"] = "original"
    df.loc[~is_town & ~has_town, "locality_source"] = "not_applicable"

    # Step 1: same person (HF id), same province, exactly one known town
    known = df[is_town & has_town]
    stats = known.groupby(["person_id", "province_std"])["locality_std"].agg(n_towns="nunique", town="first")
    one_town = stats.loc[stats["n_towns"] == 1, "town"].rename("history_town").reset_index()
    df = df.merge(one_town, on=["person_id", "province_std"], how="left")
    is_town = df["position"].isin(TOWN_POSITIONS)
    fill = is_town & df["locality_std"].isna() & df["history_town"].notna()
    df.loc[fill, "locality_std"] = df.loc[fill, "history_town"]
    df.loc[fill, "locality_source"] = "history"

    # Step 2: same-year OpenHalalan match (2013 and 2016)
    todo = df["locality_source"].isna()
    same = match_towns(prep_hf(df[todo], persons), prep_oh(winners, [2013, 2016]))
    fill = todo & df["id"].isin(same.index)
    df.loc[fill, "locality_std"] = df.loc[fill, "id"].map(same["town"])
    df.loc[fill, "locality_source"] = "openhalalan_" + df.loc[fill, "id"].map(same["tier"])

    # Step 3: undo 2013 matches that point to towns hit by OpenHalalan's town-label shift
    oh13 = winners[winners["Year"].eq(2013) & winners["Position"].isin(TOWN_POSITIONS) & winners["town_std"].notna()]
    counts = oh13.groupby(["Province", "town_std"]).size()
    doubled = counts[counts > MAX_TOWN_OFFICIALS].index
    valid_pairs = pd.MultiIndex.from_frame(
        df.loc[df["locality_source"] == "original", ["province_std", "locality_std"]]
    ).unique()
    pairs = pd.MultiIndex.from_frame(df[["province_std", "locality_std"]])
    from_oh_2013 = df["locality_source"].isin(["openhalalan_t1", "openhalalan_t2"]) & df["year"].eq(2013)
    header_town = df["locality_std"].eq(df["province_std"]) & ~pairs.isin(valid_pairs)
    revoke = from_oh_2013 & (pairs.isin(doubled) | header_town)
    df.loc[revoke, "locality_std"] = None
    df.loc[revoke, "locality_source"] = "shift_revoked"

    # Step 4: same person (by name) in OpenHalalan's reliable years
    todo = is_town & (df["locality_source"].isna() | df["locality_source"].eq("shift_revoked"))
    xyear = match_towns(prep_hf(df[todo], persons), prep_oh(winners, RELIABLE_YEARS), keys=XKEYS)
    fill = todo & df["id"].isin(xyear.index)
    df.loc[fill, "locality_std"] = df.loc[fill, "id"].map(xyear["town"])
    df.loc[fill, "locality_source"] = "openhalalan_xyear"

    # Whatever is left could not be filled
    df["locality_source"] = df["locality_source"].fillna("unfilled")
    return df.drop(columns="history_town")


def clean_persons(persons):
    """Move suffixes out of last_name, standardize suffixes, and add name keys."""
    df = persons.copy()
    found = df["last_name"].str.extract(r"^(.*?)\s(Jr|Sr|II|III|IV)\.?$")
    move = found[0].notna() & df["name_suffix"].isna()
    df.loc[move, "last_name"] = found.loc[move, 0]
    df.loc[move, "name_suffix"] = found.loc[move, 1]
    df["name_suffix"] = df["name_suffix"].replace({"Jr": "Jr.", "Sr": "Sr."})
    df["suffix_suspect"] = df["name_suffix"].isin(["XIV", "XVI"])
    df["last_key"] = df["last_name"].map(name_key)
    df["first_key"] = df["first_name"].map(name_key)
    return df


def clean_winners(winners):
    """OpenHalalan with snake_case columns, standard places, and quality flags."""
    df = winners.copy()
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    df["province_std"] = df["province"]

    town_level = df["position"].isin(TOWN_POSITIONS) & df["town_std"].notna()
    counts = df[town_level].groupby(["year", "province_std", "town_std"]).size()
    doubled = counts[counts > MAX_TOWN_OFFICIALS].index
    reliable_pairs = pd.MultiIndex.from_frame(
        df.loc[town_level & df["year"].isin(RELIABLE_YEARS), ["province_std", "town_std"]]
    ).unique()

    keys = pd.MultiIndex.from_frame(df[["year", "province_std", "town_std"]])
    pairs = pd.MultiIndex.from_frame(df[["province_std", "town_std"]])
    header_town = df["town_std"].eq(df["province_std"]) & ~pairs.isin(reliable_pairs)

    df["is_national"] = df["position"].isin(["SENATOR", "PRESIDENT", "VICE PRESIDENT"])
    df["town_shift_suspect"] = df["year"].isin(SHIFTED_YEARS) & (keys.isin(doubled) | header_town)
    return df


def clean_psa(poverty):
    """PSA poverty with standard province names, city rows, and a combined-area flag."""
    df = poverty.copy()
    df["province_std"] = None
    df["town_std"] = None

    is_prov = df["level"].eq("province")
    df.loc[is_prov, "province_std"] = df.loc[is_prov, "area_key"]
    is_district = df["level"].eq("district")
    df.loc[is_district, "province_std"] = df.loc[is_district, "area_key"].map(PSA_AREA_MAP)

    for key, (prov, town) in PSA_CITY_MAP.items():
        hit = df["area_key"].eq(key)
        df.loc[hit, "province_std"] = prov
        df.loc[hit, "town_std"] = town
    # Cotabato City sits in Maguindanao del Norte after the 2022 split
    split = df["area_key"].eq("COTABATO CITY") & df["year"].ge(2023)
    df.loc[split, "province_std"] = "MAGUINDANAO DEL NORTE"

    df["is_city"] = df["area_key"].isin(PSA_CITY_MAP.keys())
    df["is_combined_area"] = df["area_key"].eq("MAGUINDANAO") & df["year"].ge(2023)
    return df


def _ordinal(n):
    """1 -> '1st', 2 -> '2nd', 12 -> '12th', 23 -> '23rd'."""
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _std_period(text):
    """Standardize a legislative period name: typos, word ordinals, wrong suffixes."""
    if not isinstance(text, str):
        return text
    for wrong, right in PERIOD_TYPO_MAP.items():
        text = text.replace(wrong, right)
    text = re.sub(r"(?i)\bcongress\b", "Congress", text)
    parts = text.split(" ", 1)
    if parts[0].upper() in ORDINAL_WORDS:
        rest = " " + parts[1] if len(parts) > 1 else ""
        text = _ordinal(ORDINAL_WORDS[parts[0].upper()]) + rest
    text = re.sub(r"^(\d+)(?:st|nd|rd|th)\b", lambda m: _ordinal(int(m.group(1))), text)
    return PERIOD_MAP.get(text, text)

def _city_province_lookup(winners_std):
    """Town name -> province, for towns that exist in only one province (reliable OpenHalalan years)."""
    rows = winners_std[winners_std["Year"].isin(RELIABLE_YEARS) & winners_std["town_std"].notna()]
    pairs = rows[["Province", "town_std"]].drop_duplicates()
    counts = pairs["town_std"].value_counts()
    unique = pairs[pairs["town_std"].isin(counts[counts == 1].index)]
    return dict(zip(unique["town_std"], unique["Province"]))

def clean_roster(roster, winners_std):
    """Roster with fixed flags, standardized periods and provinces, and split names.

    winners_std is OpenHalalan from standardize_winners, used to resolve city names to provinces.
    """
    df = roster.copy()
    compact = df["region_province"].fillna("").str.upper().str.replace(r"[^A-Z]", "", regex=True)
    df["is_party_list"] = df["is_party_list"] | compact.isin(["PARTYLIST", "PARTLIST", "PATYLIST"])

    # Periods and congress numbers
    df["period_std"] = df["period_clean"].map(_std_period)
    commonwealth = df["period_std"].eq("1st Congress") & df["start_year"].lt(1946)
    df.loc[commonwealth, "period_std"] = "1st Congress of Commonwealth"
    num = df["period_std"].str.extract(r"^(\d+)(?:st|nd|rd|th) Congress$")[0]
    df["congress_number"] = pd.to_numeric(num, errors="coerce")

    # Provinces: clean the text, apply fixes, then resolve cities through OpenHalalan
    prov = (
        df["region_province"].str.upper()
        .str.replace("*", "", regex=False)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
        .replace(ROSTER_PROVINCE_MAP)
    )
    is_std = prov.isin(set(winners_std["Province"].dropna()))
    town = prov.map(norm_town, na_action="ignore").replace(TOWN_MAP)
    city_province = town.map(_city_province_lookup(winners_std))
    from_city = ~is_std & df["start_year"].ge(1987) & city_province.notna()

    df["province_std"] = prov.where(is_std)
    df.loc[from_city, "province_std"] = city_province[from_city]
    df["town_std"] = town.where(from_city)

    for name, (p, t) in ROSTER_CITY_MAP.items():
        hit = prov.eq(name) & df["start_year"].ge(1987)
        df.loc[hit, "province_std"] = p
        df.loc[hit, "town_std"] = t
    fix = df["region_province"].isna() & df["name"].isin(ROSTER_MISSING_PROVINCE.keys())
    df.loc[fix, "province_std"] = df.loc[fix, "name"].map(ROSTER_MISSING_PROVINCE)

    no_place = df["is_party_list"] | df["is_sectoral"]
    df.loc[no_place, ["province_std", "town_std"]] = None

    # Names: "SURNAME, FIRST [SUFFIX] M." -> first name, middle initial, suffix, match keys
    given = df["name"].str.split(",", n=1).str[1].str.strip()
    suffix = given.str.extract(r"\b(JR|SR|III|II|IV)\b\.?", flags=re.IGNORECASE)[0]
    given = given.str.replace(r"\b(?:JR|SR|III|II|IV)\b\.?", "", regex=True, flags=re.IGNORECASE)
    given = given.str.replace(r"\s+", " ", regex=True).str.strip()
    df["middle_initial"] = given.str.extract(r"\s([A-Z])\.?$")[0]
    df["first_name"] = given.str.replace(r"\s[A-Z]\.?$", "", regex=True).str.strip()
    df["name_suffix"] = suffix.str.upper().replace({"JR": "Jr.", "SR": "Sr."})
    df["last_key"] = df["surname"].map(name_key)
    df["first_key"] = df["first_name"].map(name_key, na_action="ignore")
    return df

def _split_id_pairs(persons, memberships, years):
    """HF ID pairs that may be one person: same province, surname key, and suffix,
    compatible first names, and never in office in the same year."""
    pp = memberships[["person_id", "province_std"]].drop_duplicates().merge(
        persons[["id", "first_name", "last_key", "name_suffix"]], left_on="person_id", right_on="id"
    )
    pp["suffix"] = pp["name_suffix"].fillna("")
    pairs = pp.merge(pp, on=["province_std", "last_key", "suffix"], suffixes=("_a", "_b"))
    pairs = pairs[pairs["person_id_a"] < pairs["person_id_b"]]
    pairs = pairs.drop_duplicates(["person_id_a", "person_id_b"])
    keep = [first_names_compatible(a, b) for a, b in zip(pairs["first_name_a"], pairs["first_name_b"])]
    pairs = pairs.loc[keep]
    apart = [not (years[a] & years[b]) for a, b in zip(pairs["person_id_a"], pairs["person_id_b"])]
    return pairs.loc[apart, ["person_id_a", "person_id_b", "first_name_a", "first_name_b"]].reset_index(drop=True)


def _hf_middle_names(persons, memberships, winners_clean):
    """Most common OpenHalalan middle-name key for each HF person, matched by election, surname, and a shared first-name word."""
    oh = winners_clean[winners_clean["year"].isin(memberships["year"].unique()) & winners_clean["middle_name"].notna()].copy()
    oh["last_key"] = oh["last_name"].map(name_key, na_action="ignore")
    oh["middle_key"] = oh["middle_name"].str.split().str[-1].map(name_key, na_action="ignore")

    hf = memberships.merge(persons[["id", "first_name", "last_key"]], left_on="person_id", right_on="id", suffixes=("", "_p"))
    keys = ["year", "position", "province_std", "last_key"]
    cand = hf.merge(oh[keys + ["first_name", "middle_key"]], on=keys, suffixes=("", "_oh"))
    shared = [bool(name_tokens(a) & name_tokens(b)) for a, b in zip(cand["first_name"], cand["first_name_oh"])]
    cand = cand.loc[shared]
    cand = cand[cand.groupby("id")["middle_key"].transform("size") == 1]
    return cand.groupby("person_id")["middle_key"].agg(lambda s: s.mode().iloc[0])


def _usable_middle(mid, words):
    """A real middle name: longer than one letter, not a job title, not a word from the first names."""
    return isinstance(mid, str) and len(mid) > 1 and mid not in words and mid not in JOB_WORDS


def _pair_evidence(pairs, person_mid):
    """'agree', 'conflict', or 'unknown' for each pair, from OpenHalalan middle names."""
    evidence = []
    for pa, pb, fa, fb in zip(pairs["person_id_a"], pairs["person_id_b"], pairs["first_name_a"], pairs["first_name_b"]):
        words = name_tokens(fa) | name_tokens(fb)
        ma, mb = person_mid.get(pa), person_mid.get(pb)
        if not (_usable_middle(ma, words) and _usable_middle(mb, words)):
            evidence.append("unknown")
        elif middle_names_agree(ma, mb):
            evidence.append("agree")
        else:
            evidence.append("conflict")
    return evidence


def resolve_persons(persons, memberships, winners_clean):
    """Merge HF person IDs that belong to one person written differently.

    Returns (persons_merged, id_map). persons_merged has one row per person. id_map links every
    original HF id (person_id_raw) to its merged id (person_uid) and the evidence for the merge.
    """
    years = memberships.groupby("person_id")["year"].apply(set)
    pairs = _split_id_pairs(persons, memberships, years)
    person_mid = _hf_middle_names(persons, memberships, winners_clean)
    pairs["evidence"] = _pair_evidence(pairs, person_mid)
    accepted = pairs[pairs["evidence"].isin(["agree", "unknown"])]

    # Union-find: join every accepted pair into groups
    parent = {pid: pid for pid in persons["id"]}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in zip(accepted["person_id_a"], accepted["person_id_b"]):
        parent[find(a)] = find(b)
    group = pd.Series({pid: find(pid) for pid in parent})

    # Safeguard: undo groups with members in office the same year or conflicting middle names
    first_words = persons.set_index("id")["first_name"].map(name_tokens)
    for members in group.groupby(group).groups.values():
        members = list(members)
        if len(members) < 2:
            continue
        yrs = [years.get(m, set()) for m in members]
        words = set().union(*(first_words.get(m, set()) for m in members))
        mids = [x for x in (person_mid.get(m) for m in members) if _usable_middle(x, words)]
        overlap = sum(len(y) for y in yrs) != len(set().union(*yrs))
        conflict = not all(middle_names_agree(x, y) for i, x in enumerate(mids) for y in mids[i + 1:])
        if overlap or conflict:
            group[members] = members

    # One merged id per group: the member with the most terms (ties: smallest id)
    info = pd.DataFrame({"person_id_raw": group.index, "group": group.values})
    info["n_rows"] = info["person_id_raw"].map(memberships["person_id"].value_counts()).fillna(0)
    info = info.sort_values(["group", "n_rows", "person_id_raw"], ascending=[True, False, True])
    info["person_uid"] = info.groupby("group")["person_id_raw"].transform("first")
    info["n_ids"] = info.groupby("group")["person_id_raw"].transform("size")

    # Evidence label: 'name_only' if any merge in the group lacked middle-name confirmation
    same_group = accepted["person_id_a"].map(group) == accepted["person_id_b"].map(group)
    used = accepted[same_group]
    name_only = set(used.loc[used["evidence"].eq("unknown"), "person_id_a"].map(group))
    info["merge_evidence"] = None
    multi = info["n_ids"] > 1
    info.loc[multi, "merge_evidence"] = "middle_name_agree"
    info.loc[multi & info["group"].isin(name_only), "merge_evidence"] = "name_only"
    id_map = info[["person_id_raw", "person_uid", "n_ids", "merge_evidence"]].reset_index(drop=True)

    # One row per person, with one display name
    p = persons.merge(id_map, left_on="id", right_on="person_id_raw")
    p["n_words"] = p["first_name"].str.split().str.len()
    p["name_len"] = p["first_name"].str.len()
    p["has_enye"] = p["last_name"].str.contains("ñ", case=False)
    best_first = p.sort_values(["n_words", "name_len"], ascending=False).drop_duplicates("person_uid").set_index("person_uid")["first_name"]
    best_last = p.sort_values("has_enye", ascending=False).drop_duplicates("person_uid").set_index("person_uid")["last_name"]
    variants = (p["first_name"] + " " + p["last_name"]).groupby(p["person_uid"]).agg(lambda s: " | ".join(sorted(set(s))))

    merged = p[p["id"].eq(p["person_uid"])].drop(columns=["person_id_raw", "person_uid", "n_words", "name_len", "has_enye"])
    merged = merged.set_index("id")
    merged["first_name"] = best_first
    merged["last_name"] = best_last
    merged["suffix_suspect"] = p.groupby("person_uid")["suffix_suspect"].any()
    merged["name_variants"] = variants
    merged["first_key"] = merged["first_name"].map(name_key)
    merged["last_key"] = merged["last_name"].map(name_key)
    return merged.reset_index(), id_map


def main(out_dir=STAGING):
    """Read all inputs, clean them, backfill localities, merge split person IDs, and write the cleaned tables."""
    persons_raw = pd.read_parquet(RAW / "hf_persons.parquet")
    memberships_raw = pd.read_parquet(RAW / "hf_memberships.parquet")
    winners_raw = pd.read_csv(RAW / "openhalalan_winners.csv")
    poverty_raw = pd.read_csv(STAGING / "psa_poverty.csv")
    roster_raw = pd.read_csv(STAGING / "roster_legislators.csv")

    winners_std = standardize_winners(winners_raw)
    winners_clean = clean_winners(winners_std)
    persons = clean_persons(persons_raw)
    memberships = backfill_localities(standardize_memberships(memberships_raw), persons, winners_std)

    # Merge split person IDs. Memberships keep the original id in person_id_raw.
    persons_merged, id_map = resolve_persons(persons, memberships, winners_clean)
    memberships["person_id_raw"] = memberships["person_id"]
    memberships["person_id"] = memberships["person_id_raw"].map(id_map.set_index("person_id_raw")["person_uid"])

    outputs = {
        "hf_persons_clean": persons_merged,
        "hf_person_id_map": id_map,
        "hf_memberships_clean": memberships,
        "openhalalan_winners_clean": winners_clean,
        "psa_poverty_clean": clean_psa(poverty_raw),
        "roster_legislators_clean": clean_roster(roster_raw, winners_std),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in outputs.items():
        path = out_dir / f"{name}.parquet"
        df.to_parquet(path, index=False)
        print(f"{name}: {len(df):,} rows -> {path}")

    print(f"\npeople: {len(persons):,} HF IDs -> {len(persons_merged):,} after merging split IDs")
    print("\nlocality_source:")
    print(memberships["locality_source"].value_counts().to_string())
    

if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else STAGING)