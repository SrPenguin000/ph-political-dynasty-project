import re, sys
import numpy as np
import pandas as pd
import networkx as nx
from scipy.stats import poisson
sys.path.insert(0, "..")
from src.transform.normalize import name_key, name_tokens

S = "data/staging/"
C = "data/curated/"
persons = pd.read_parquet(S + "hf_persons_clean.parquet")
memberships = pd.read_parquet(S + "hf_memberships_clean.parquet")
oh = pd.read_parquet(S + "openhalalan_winners_clean.parquet")
roster = pd.read_parquet(S + "roster_legislators_clean.parquet")
ateneo = pd.read_parquet(S + "ateneo_politicians_clean.parquet")   

HF_YEARS = range(2004, 2017)
NATIONAL = ["SENATOR", "PRESIDENT", "VICE PRESIDENT"]
HOUSE = "MEMBER, HOUSE OF REPRESENTATIVES"
SUFFIX_RE = re.compile(r"\b(JR|SR|III|II|IV)\b\.?", re.IGNORECASE)  

def extract_suffix(name):
    if not isinstance(name, str):
        return None
    m = SUFFIX_RE.search(name)
    return m.group(1).upper() if m else None

def std_suffix(s):
    if not isinstance(s, str):
        return None
    s = s.upper().replace(".", "").strip()
    return s.split()[-1] if s else None

def middle_parts(middle):
    """(middle_key, middle_initial). An initial like 'B.' gives no key."""
    if not isinstance(middle, str):
        return None, None
    key = name_key(middle)
    if not key:
        return None, None
    words = [w for w in re.findall(r"[A-Z]+", middle.upper().replace("Ñ", "N"))
             if w not in {"JR", "SR", "II", "III", "IV"}]
    if not words or all(len(w) == 1 for w in words):
        return None, key[0]
    return key, key[0]

oh = oh.reset_index(drop=True)
oh["oh_row"] = oh.index
oh["last_key"] = oh["last_name"].map(name_key, na_action="ignore").replace("", None)
oh["first_key"] = oh["first_name"].map(name_key, na_action="ignore").replace("", None)
oh["suffix"] = oh["full_name"].map(extract_suffix)
parts = oh["middle_name"].map(middle_parts)
oh["middle_key"] = parts.str[0]
oh["middle_initial"] = parts.str[1]

PARTICLES = ["DE LA", "DELA", "DE", "DEL", "DE LOS", "DELOS", "DI", "SAN", "STA", "STO"]
known_surnames = set(persons["last_key"]) | set(oh["last_key"].dropna())
mid_clean = oh["middle_name"].fillna("").str.upper().str.replace(".", "", regex=False).str.strip()
is_particle = mid_clean.isin(PARTICLES)
joined = mid_clean.str.replace(" ", "", regex=False) + oh["last_key"].fillna("")
move = is_particle & joined.isin(known_surnames)           # only if the joined surname really exists
oh.loc[move, "last_key"] = joined[move]
oh.loc[move, "last_name"] = mid_clean[move] + " " + oh.loc[move, "last_name"]
oh.loc[is_particle, ["middle_key", "middle_initial"]] = None   # a prefix alone is never a middle name
print("surname prefixes moved back:", move.sum(), "| prefix-only middle names dropped:", (is_particle & ~move).sum())

PREFIX_KEYS = {"DE", "DELA", "DEL", "DELOS", "DI", "SAN", "STA", "STO", "LA", "LOS"}

def best_surname(middle):
    words = [w for w in re.findall(r"[A-Z]+", middle.upper().replace("Ñ", "N")) if w not in {"JR", "SR", "II", "III", "IV"}]
    for i in range(len(words)):                       # try the longest ending first
        cand = "".join(words[i:])
        if len(cand) >= 2 and cand in known_surnames and cand not in PREFIX_KEYS:
            return cand
    last = words[-1] if words else ""
    return last if len(last) >= 2 and last not in PREFIX_KEYS else None

multi = oh["middle_key"].notna() & oh["middle_name"].str.strip().str.contains(" ")
oh.loc[multi, "middle_key"] = oh.loc[multi, "middle_name"].map(best_surname)
oh.loc[multi, "middle_initial"] = oh.loc[multi, "middle_key"].str[0]
print("multi-word middle names fixed:", multi.sum())

oh["town_use"] = oh["town_std"].mask(oh["town_shift_suspect"])

from src.transform.mappings import PROVINCE_GROUP
at = ateneo[ateneo["year"].lt(2001) & ateneo["position"].ne(HOUSE) & ~ateneo["is_duplicate"]].copy()   # House terms before 2001 come from the roster
at = at.reset_index(drop=True)
at["at_row"] = at.index
at["first_name"] = at["first_name_std"]
at["last_name"] = at["last_name_std"]
at["suffix"] = at["name_suffix"].map(std_suffix)
at["last_key"] = at["last_key"].replace("", None)
at["first_key"] = at["first_key"].replace("", None)
print(f"Ateneo rows used (1988-1998, local + provincial posts): {len(at):,}")

hf = memberships.merge(
    persons[["id", "first_name", "last_name", "name_suffix", "last_key", "first_key"]]
    .rename(columns={"id": "person_id"}), on="person_id", how="left")
hf["suffix"] = hf["name_suffix"].map(std_suffix)

print(len(oh), len(hf))
print("has middle_key:", oh["middle_key"].notna().sum())
print(oh["suffix"].value_counts())

def one_to_one(pairs):
    """Keep only pairs where each HF row and each OpenHalalan row has exactly one partner."""
    n_oh = pairs.groupby("id")["oh_row"].transform("nunique")
    n_hf = pairs.groupby("oh_row")["id"].transform("nunique")
    return pairs[(n_oh == 1) & (n_hf == 1)].drop_duplicates(["id", "oh_row"])

keys = ["year", "position", "province_std", "last_key"]
o = oh[oh["year"].isin(HF_YEARS) & oh["last_key"].notna() & oh["first_key"].notna()]

# Tier 1: exact first name
t1 = one_to_one(hf.merge(o[keys + ["first_key", "oh_row"]], on=keys + ["first_key"])).assign(tier="t1")

# Tier 2: first names share a word (only for rows not matched in Tier 1)
rest_hf = hf[~hf["id"].isin(t1["id"])]
rest_oh = o[~o["oh_row"].isin(t1["oh_row"])]
cand = rest_hf.merge(rest_oh[keys + ["first_name", "oh_row"]], on=keys, suffixes=("", "_oh"))
shared = [bool(name_tokens(a) & name_tokens(b)) for a, b in zip(cand["first_name"], cand["first_name_oh"])]
t2 = one_to_one(cand[shared]).assign(tier="t2")

xwalk = pd.concat([t1, t2])[["id", "oh_row", "tier"]].reset_index(drop=True)
print(xwalk["tier"].value_counts())
print(f"HF rows linked: {len(xwalk):,} of {len(hf):,} ({len(xwalk) / len(hf):.1%})")

def group_mode(df, key, col):
    """Most common value of `col` for each `key`."""
    d = df[[key, col]].dropna()
    c = d.groupby([key, col]).size().rename("n").reset_index()
    c = c.sort_values([key, "n", col], ascending=[True, False, True])
    return c.drop_duplicates(key).set_index(key)[col]

def compatible(a, b):
    """True when either value is missing, or both are the same."""
    return pd.isna(a) or pd.isna(b) or a == b

# Rows linked in Step 2 take the HF person's ID
row_to_person = xwalk.set_index("oh_row")["id"].map(hf.set_index("id")["person_id"])
oh["person_uid"] = "HF-" + oh["oh_row"].map(row_to_person)
oh["link_method"] = None
oh.loc[oh["person_uid"].notna(), "link_method"] = "crosswalk"

# What we now know about each HF person (middle name, suffix)
matched = oh[oh["person_uid"].notna()]
known = pd.DataFrame({"middle_key": group_mode(matched, "person_uid", "middle_key"),
                      "suffix": group_mode(matched, "person_uid", "suffix")})

# Same province + last + first name as exactly ONE HF person, no conflict
sig = ["province_std", "last_key", "first_key"]
hf_sig = hf.dropna(subset=sig)[sig + ["person_id"]].drop_duplicates()
hf_sig["person_uid"] = "HF-" + hf_sig["person_id"]
one_person = hf_sig.groupby(sig)["person_uid"].transform("nunique") == 1
hf_sig = hf_sig[one_person].drop(columns="person_id").drop_duplicates(sig)

todo = oh["person_uid"].isna() & oh[sig].notna().all(axis=1)
cand = oh.loc[todo, ["oh_row"] + sig + ["middle_key", "suffix"]].merge(hf_sig, on=sig)
cand = cand.join(known, on="person_uid", rsuffix="_hf")
ok = [compatible(m, mh) and compatible(s, sh)
      for m, mh, s, sh in zip(cand["middle_key"], cand["middle_key_hf"], cand["suffix"], cand["suffix_hf"])]
cand = cand[ok].set_index("oh_row")["person_uid"]
fill = oh["oh_row"].isin(cand.index)
oh.loc[fill, "person_uid"] = oh.loc[fill, "oh_row"].map(cand)
oh.loc[fill, "link_method"] = "name_province"

# Everyone left: new OpenHalalan-only person
todo = oh["person_uid"].isna()
rest = oh[todo].copy()
rest["place"] = rest["province_std"].fillna("NATIONAL")   # senators etc. have no province
name = ["place", "last_key", "first_key"]
rest[name] = rest[name].fillna("?")
n_mid = rest.groupby(name)["middle_key"].transform("nunique")
only_mid = rest.groupby(name)["middle_key"].transform("first")
rest["mid_group"] = rest["middle_key"]
no_mid = rest["middle_key"].isna() & n_mid.eq(1)
rest.loc[no_mid, "mid_group"] = only_mid[no_mid]   # no middle name? join the only one there is
rest["mid_group"] = rest["mid_group"].fillna("")
gid = rest.groupby(name + ["mid_group"]).ngroup()
oh.loc[todo, "person_uid"] = "OH-" + gid.astype(str).str.zfill(6)
oh.loc[todo, "link_method"] = "new"

print(oh["link_method"].value_counts())
print("people found only in OpenHalalan:", oh.loc[oh["link_method"].eq("new"), "person_uid"].nunique())
print("rows without a person ID:", oh["person_uid"].isna().sum())

# Roster: link modern House members, new IDs for historical ones
r = roster.reset_index(drop=True).copy()
r["roster_row"] = r.index
r["suffix"] = r["name_suffix"].map(std_suffix)
r["place"] = r["province_std"].fillna(r["region_province"].str.upper().str.strip())
r.loc[r["is_party_list"] | r["is_sectoral"], "place"] = "PARTY-LIST/SECTORAL"
r["place"] = r["place"].fillna("UNKNOWN")

mid_initial = group_mode(oh, "person_uid", "middle_initial")
house = pd.concat([hf.assign(person_uid="HF-" + hf["person_id"]), oh])
house = house[house["position"].eq(HOUSE)][["person_uid", "province_std", "last_key", "first_key"]].dropna()
house = house.drop_duplicates()
house = house[house.groupby(["province_std", "last_key", "first_key"])["person_uid"].transform("nunique") == 1]
house["middle_initial"] = house["person_uid"].map(mid_initial)

c = r[r["start_year"].ge(2001)].merge(house, on=["province_std", "last_key", "first_key"], suffixes=("", "_reg"))
c = c[[compatible(a, b) for a, b in zip(c["middle_initial"], c["middle_initial_reg"])]]
c = c.drop_duplicates("roster_row").set_index("roster_row")["person_uid"]
r["person_uid"] = r["roster_row"].map(c)
r["link_method"] = None
r.loc[r["person_uid"].notna(), "link_method"] = "name_province"
todo = r["person_uid"].isna()
rk = ["place", "last_key", "first_key", "middle_initial", "suffix"]
gid = r[todo][rk].fillna("").groupby(rk).ngroup()
r.loc[todo, "person_uid"] = "RL-" + gid.astype(str).str.zfill(5)
r.loc[todo, "link_method"] = "new"
print(r["link_method"].value_counts())

# Ateneo 1988-1998: same province + last + first name as exactly ONE known person -> that person; else a new AT person
reg = pd.concat([
    hf.assign(person_uid="HF-" + hf["person_id"])[["person_uid", "province_std", "last_key", "first_key", "suffix"]],
    oh[["person_uid", "province_std", "last_key", "first_key", "suffix"]],
    r[["person_uid", "province_std", "last_key", "first_key", "suffix"]],
]).dropna(subset=["province_std", "last_key", "first_key"])
reg_suffix = group_mode(reg, "person_uid", "suffix")
reg["province_group"] = reg["province_std"].replace(PROVINCE_GROUP)   # follow people across province splits (e.g. Biliran from Leyte, 1992)
reg = reg.drop(columns=["suffix", "province_std"]).drop_duplicates()
reg = reg[reg.groupby(["province_group", "last_key", "first_key"])["person_uid"].transform("nunique") == 1]
c = at.merge(reg, on=["province_group", "last_key", "first_key"])
c = c[[compatible(x, y) for x, y in zip(c["suffix"], c["person_uid"].map(reg_suffix))]]
at["person_uid"] = at["at_row"].map(c.set_index("at_row")["person_uid"])
at["link_method"] = None
at.loc[at["person_uid"].notna(), "link_method"] = "name_province"
todo = at["person_uid"].isna()
ak = ["province_group", "last_key", "first_key", "suffix"]
gid = at[todo][ak].fillna("").groupby(ak).ngroup()
at.loc[todo, "person_uid"] = "AT-" + gid.astype(str).str.zfill(6)
at.loc[todo, "link_method"] = "new"
print("Ateneo 1988-1998:", at["link_method"].value_counts().to_dict())

# Terms: one row per term served (is_primary = count each mandate once)
terms = pd.concat([
    pd.DataFrame({"person_uid": "HF-" + hf["person_id"], "source": "hf", "source_row_id": hf["id"],
                  "year": hf["year"], "position": hf["position"], "province_std": hf["province_std"],
                  "town_std": hf["locality_std"], "party": hf["party"], "is_primary": True}),
    pd.DataFrame({"person_uid": oh["person_uid"], "source": "openhalalan",
                  "source_row_id": "OH-row-" + oh["oh_row"].astype(str),
                  "year": oh["year"], "position": oh["position"], "province_std": oh["province_std"],
                  "town_std": oh["town_use"], "party": oh["party"],
                  "is_primary": ~oh["year"].isin(HF_YEARS) | oh["position"].isin(NATIONAL)}),
    pd.DataFrame({"person_uid": r["person_uid"], "source": "roster",
                  "source_row_id": "RL-row-" + r["roster_row"].astype(str),
                  "year": r["start_year"], "end_year": r["end_year"], "position": HOUSE,
                  "province_std": r["province_std"], "town_std": r["town_std"], "place_label": r["place"],
                    "is_primary": r["start_year"].lt(2001) | r["start_year"].isna()}),
    pd.DataFrame({"person_uid": at["person_uid"], "source": "ateneo",
                        "source_row_id": at["ateneo_row_id"],
                  "year": at["year"], "position": at["position"], "province_std": at["province_std"],
                  "town_std": at["town_std"], "party": at["party"], "is_primary": True}),
], ignore_index=True)

terms["year"] = terms["year"].astype("Int64")
terms["end_year"] = terms["end_year"].astype("Int64")
terms["place_label"] = terms["place_label"].fillna(terms["province_std"])
terms.loc[terms["position"].isin(NATIONAL), "place_label"] = "NATIONAL"

# People: one row per person
hf_names = persons.assign(person_uid="HF-" + persons["id"], suffix=persons["name_suffix"].map(std_suffix))
hf_names = hf_names.set_index("person_uid")[["first_name", "last_name", "last_key", "first_key", "suffix"]]
oh_names = oh.groupby("person_uid")[["first_name", "last_name", "last_key", "first_key"]].first()
for col in ["suffix", "middle_name", "middle_key", "middle_initial", "sex"]:
    oh_names[col] = group_mode(oh, "person_uid", col)
rl_names = r.groupby("person_uid").agg(first_name=("first_name", "first"), last_name=("surname", "first"),
                                       last_key=("last_key", "first"), first_key=("first_key", "first"))
for col in ["suffix", "middle_initial"]:
    rl_names[col] = group_mode(r, "person_uid", col)

at_names = at.groupby("person_uid")[["first_name", "last_name", "last_key", "first_key"]].first()
at_names["suffix"] = group_mode(at, "person_uid", "suffix")

people = hf_names.combine_first(oh_names).combine_first(rl_names).combine_first(at_names)   # HF names first, then OH, roster, Ateneo
people = people.reindex(terms["person_uid"].unique())
people.index.name = "person_uid"

home_prov = group_mode(terms, "person_uid", "province_std")
in_home = terms["province_std"].eq(terms["person_uid"].map(home_prov))
people["home_province"] = home_prov
people["home_town"] = group_mode(terms[in_home], "person_uid", "town_std")
people["home_place"] = people["home_province"].fillna(group_mode(terms, "person_uid", "place_label"))
yrs = terms.groupby("person_uid").agg(first_year=("year", "min"), last_year=("year", "max"), n_terms=("year", "size"))
people = people.join(yrs)
u = terms[["person_uid", "position"]].drop_duplicates().sort_values("position")
people["positions"] = u.groupby("person_uid")["position"].agg("; ".join)
people = people.reset_index()
people["display_name"] = (people["last_name"].fillna("").str.upper() + ", " + people["first_name"].fillna("")
                          + (" " + people["suffix"]).fillna("") + (" " + people["middle_initial"] + ".").fillna(""))

print(f"people: {len(people):,} | terms: {len(terms):,}")
print(people["person_uid"].str[:2].value_counts())
print("people with a middle name:", people["middle_key"].notna().sum())
print(people.loc[people["last_key"].eq("ABAD") & people["home_place"].eq("BATANES"),
           ["display_name", "positions", "first_year", "last_year"]])

PRIORITY = {"HF": 0, "AT": 1, "OH": 2, "RL": 3}     # keep the ID that exists in dim_person

def merge_split_people(people, terms):
    info = people.set_index("person_uid")

    # 1. Candidate pairs: same province group + surname in at least one term
    tp = terms.dropna(subset=["person_uid", "province_std"])[["person_uid", "province_std"]].drop_duplicates()
    tp["pgroup"] = tp["province_std"].replace(PROVINCE_GROUP)
    tp["last_key"] = tp["person_uid"].map(info["last_key"])
    blocks = tp.dropna(subset=["last_key"])[["person_uid", "pgroup", "last_key"]].drop_duplicates()
    pr = blocks.merge(blocks, on=["pgroup", "last_key"], suffixes=("_a", "_b"))
    pr = pr[pr["person_uid_a"] < pr["person_uid_b"]][["person_uid_a", "person_uid_b"]].drop_duplicates()
    n_pairs = len(pr)

    # 2. Name checks
    A, B = info.loc[pr["person_uid_a"]], info.loc[pr["person_uid_b"]]
    words = lambda s: s.fillna("").str.upper().str.findall(r"[A-ZÑ]+").map(set).to_numpy()
    first_ok = np.array([bool(x) and bool(y) and (x <= y or y <= x)
                         for x, y in zip(words(A["first_name"]), words(B["first_name"]))])
    def agree(col):
        x, y = A[col].to_numpy(), B[col].to_numpy()
        return pd.isna(x) | pd.isna(y) | (x == y)
    suffix_ok = A["suffix"].fillna("").to_numpy() == B["suffix"].fillna("").to_numpy()
    pr = pr[first_ok & suffix_ok & agree("middle_key") & agree("middle_initial")]

    # 3. Share a town (or one of them has no town)
    towns = terms.dropna(subset=["town_std"]).groupby("person_uid")["town_std"].agg(set)
    ta, tb = pr["person_uid_a"].map(towns), pr["person_uid_b"].map(towns)
    share = [(not isinstance(x, set)) or (not isinstance(y, set)) or bool(x & y) for x, y in zip(ta, tb)]
    pr = pr[share]

    # 4. Never different seats in the same year
    yp = terms.dropna(subset=["person_uid", "year"])[["person_uid", "year", "position", "town_std"]].drop_duplicates()
    ya = yp.rename(columns={"person_uid": "person_uid_a", "position": "pos_a", "town_std": "town_a"})
    yb = yp.rename(columns={"person_uid": "person_uid_b", "position": "pos_b", "town_std": "town_b"})
    m = pr.merge(ya, on="person_uid_a").merge(yb, on=["person_uid_b", "year"])
    clash = (m["pos_a"] != m["pos_b"]) | (m["town_a"].notna() & m["town_b"].notna() & (m["town_a"] != m["town_b"]))
    bad = set(zip(m.loc[clash, "person_uid_a"], m.loc[clash, "person_uid_b"]))
    pr = pr[[(a, b) not in bad for a, b in zip(pr["person_uid_a"], pr["person_uid_b"])]]

    # 5. Merge only complete groups
    H = nx.Graph()
    H.add_edges_from(zip(pr["person_uid_a"], pr["person_uid_b"]))
    remap, groups, skipped = {}, {}, 0
    for comp in nx.connected_components(H):
        n = len(comp)
        if H.subgraph(comp).number_of_edges() != n * (n - 1) // 2:
            skipped += 1
            continue
        canon = min(comp, key=lambda u: (PRIORITY.get(u[:2], 9), u))
        groups[canon] = sorted(comp)
        remap.update({u: canon for u in comp if u != canon})
    print(f"candidate pairs: {n_pairs:,} | merged groups: {len(groups):,} "
          f"({len(remap):,} duplicate IDs removed) | groups skipped (not every pair agrees): {skipped:,}")
    if not remap:
        return people, terms, remap

    # Re-point every term at the surviving ID
    terms = terms.copy()
    terms["person_uid"] = terms["person_uid"].map(remap).fillna(terms["person_uid"])

    # The same mandate can now appear twice (once per source). Count it once.
    twice = terms["is_primary"] & terms.duplicated(
        ["person_uid", "year", "position", "province_std", "town_std"], keep="first")
    terms.loc[twice, "is_primary"] = False
    print(f"mandates recorded by two sources, counted once: {twice.sum():,}")

    # Surviving row keeps its own values, and borrows anything it is missing from the IDs it absorbed
    old = people.set_index("person_uid")
    fill_cols = [c for c in ["first_name", "last_name", "last_key", "first_key", "suffix", "middle_name",
                             "middle_key", "middle_initial", "sex"] if c in old.columns]
    for canon, members in groups.items():
        for col in fill_cols:
            if pd.isna(old.at[canon, col]):
                vals = old.loc[members, col].dropna()
                if len(vals):
                    old.at[canon, col] = vals.iloc[0]
    people = old.drop(index=list(remap))

    # Recompute the per-person summaries from the merged terms (same logic as the people table above)
    people = people.drop(columns=[c for c in ["home_province", "home_town", "home_place", "first_year",
                                              "last_year", "n_terms", "positions", "display_name"]
                                  if c in people.columns])
    home_prov = group_mode(terms, "person_uid", "province_std")
    in_home = terms["province_std"].eq(terms["person_uid"].map(home_prov))
    people["home_province"] = home_prov
    people["home_town"] = group_mode(terms[in_home], "person_uid", "town_std")
    people["home_place"] = people["home_province"].fillna(group_mode(terms, "person_uid", "place_label"))
    people = people.join(terms.groupby("person_uid").agg(first_year=("year", "min"), last_year=("year", "max"),
                                                         n_terms=("year", "size")))
    u = terms[["person_uid", "position"]].drop_duplicates().sort_values("position")
    people["positions"] = u.groupby("person_uid")["position"].agg("; ".join)
    people = people.reset_index()
    people["display_name"] = (people["last_name"].fillna("").str.upper() + ", " + people["first_name"].fillna("")
                              + (" " + people["suffix"]).fillna("") + (" " + people["middle_initial"] + ".").fillna(""))
    return people, terms, remap

n_before = len(people)
people, terms, id_remap = merge_split_people(people, terms)
print(f"people: {n_before:,} -> {len(people):,}")

first_words = pd.concat([oh["first_name"], persons["first_name"], roster["first_name"], at["first_name"]]).dropna()
first_words = first_words.str.upper().str.replace("Ñ", "N").str.findall(r"[A-Z]+").explode()
first_words = first_words[first_words.str.len() >= 2]
surname_counts = pd.concat([people["last_key"], oh["last_key"]]).value_counts()

mk = people["middle_key"]
as_last = mk.map(surname_counts).fillna(0)                 # times used as a surname
as_first = mk.map(first_words.value_counts()).fillna(0)    # times used as a first name

is_first_name = mk.notna() & (as_first > 0) & (as_first >= as_last)
is_junk = mk.isin(["MAYOR", "VICEMAYOR", "COUNCILOR", "GOVERNOR", "NONE", "NULL", "NA"])  
too_short = mk.fillna("").str.len().le(2) & as_last.eq(0)   # initials like "DP" (UY, GO, TY are kept)

people["middle_is_given_name"] = is_first_name
people["middle_status"] = np.select(
    [mk.isna(), is_junk, too_short, is_first_name, as_last > 0],
    ["none", "junk", "initials", "first_name", "surname_known"], default="surname_new")
people.loc[people["middle_status"].isin(["junk", "initials", "first_name"]), "middle_key"] = None

print(people["middle_status"].value_counts())
print("middle names kept as surnames:", people["middle_key"].notna().sum())
print("examples removed as first names:", people.loc[people["middle_status"].eq("first_name"), "middle_name"].str.upper().value_counts().head(8).index.tolist())
print("examples kept, not held by any politician:", people.loc[people["middle_status"].eq("surname_new"), "middle_key"].value_counts().head(8).index.tolist())

P_MAX, PRIOR = 0.01, 50   # p-value cutoff; PRIOR smooths toward the national share

region_of = group_mode(oh.dropna(subset=["province_std"]), "province_std", "region").to_dict()
p = people.dropna(subset=["last_key"]).copy()
p["region"] = p["home_place"].map(region_of).fillna("NO REGION")
national = p["last_key"].value_counts() / len(p)

def chance_test(n, total, ref_n, ref_total, nat_share):
    """P(seeing n or more people with this surname here | how common it is around here)."""
    share = (ref_n + PRIOR * nat_share) / (ref_total + PRIOR)
    expected = share * total
    return poisson.sf(n - 1, expected), expected

# Province vs rest of its region
prov = p.groupby(["home_place", "region", "last_key"]).size().rename("n").reset_index()
prov = prov.merge(p.groupby("home_place").size().rename("total").reset_index(), on="home_place")
prov = prov.merge(p.groupby(["region", "last_key"]).size().rename("reg_n").reset_index(), on=["region", "last_key"])
prov = prov.merge(p.groupby("region").size().rename("reg_total").reset_index(), on="region")
prov["p_value"], prov["expected"] = chance_test(prov["n"], prov["total"], prov["reg_n"] - prov["n"],
                                                prov["reg_total"] - prov["total"], prov["last_key"].map(national))

# Town vs rest of its province
t = p.dropna(subset=["home_town"])
town = t.groupby(["home_place", "home_town", "last_key"]).size().rename("n").reset_index()
town = town.merge(t.groupby(["home_place", "home_town"]).size().rename("total").reset_index(), on=["home_place", "home_town"])
town = town.merge(p.groupby(["home_place", "last_key"]).size().rename("prov_n").reset_index(), on=["home_place", "last_key"])
town = town.merge(p.groupby("home_place").size().rename("prov_total").reset_index(), on="home_place")
town["p_value"], town["expected"] = chance_test(town["n"], town["total"], town["prov_n"] - town["n"],
                                                town["prov_total"] - town["total"], town["last_key"].map(national))

for name, df in [("province", prov), ("town", town)]:
    g = df[df["n"] >= 2]
    print(f"{name}: {len(g):,} surname groups with 2+ people, {(g['p_value'] < P_MAX).sum():,} pass ({(g['p_value'] < P_MAX).mean():.0%})")

# Sanity check on well-known families
prov[prov["last_key"].isin(["AMPATUAN", "ABAD", "ORTEGA"]) & (prov["n"] >= 5)][["home_place", "last_key", "n", "expected", "p_value"]]

def pairs_within(df, cols):
    """All pairs of different people who share the same values in `cols` (each pair once)."""
    x = df[cols + ["person_uid"]]
    pr = x.merge(x, on=cols, suffixes=("_a", "_b"))
    return pr[pr["person_uid_a"] < pr["person_uid_b"]]

def make_edges(pr, relation, tier, hint, p_value=None, succession=False):
    """Turn a table of pairs into kinship links."""
    return pd.DataFrame({"person_a": pr["person_uid_a"].to_numpy(), "person_b": pr["person_uid_b"].to_numpy(),
                         "relation": relation, "tier": tier, "relation_hint": hint,
                         "p_value": np.nan if p_value is None else np.asarray(p_value, dtype=float),
                         "succession": succession if np.isscalar(succession) else np.asarray(succession, dtype=bool)})

info = people.set_index("person_uid")
with_mid = people.dropna(subset=["middle_key", "last_key"])
town_ok = town.loc[town["p_value"] < P_MAX, ["home_place", "home_town", "last_key", "p_value"]]
prov_ok = prov.loc[prov["p_value"] < P_MAX, ["home_place", "last_key", "p_value"]]

# Rule 1: nuclear family (same last + same middle name, same province)
nu = pairs_within(with_mid, ["home_place", "last_key", "middle_key"])
e_nuclear = make_edges(nu, "nuclear_family", "strong", "sibling or mother-child")

# Rule 2: father and son (same full name + generational suffix pair)
fs = pairs_within(people.dropna(subset=["last_key", "first_key"]), ["home_place", "last_key", "first_key"])
sa = fs["person_uid_a"].map(info["suffix"]).fillna("")
sb = fs["person_uid_b"].map(info["suffix"]).fillna("")
chain = {("SR", "JR"), ("", "JR"), ("JR", "III"), ("", "II"), ("II", "III"), ("III", "IV")}
fs = fs[[(x, y) in chain or (y, x) in chain for x, y in zip(sa, sb)]]
e_father = make_edges(fs, "father_son", "strong", "father and son")

# Succession: same seat (position + place) held one election after the other
st = terms[terms["is_primary"]].dropna(subset=["person_uid", "year", "province_std"]).copy()
st = st[st["position"].isin(["MAYOR", "VICE MAYOR", "GOVERNOR", "VICE GOVERNOR", HOUSE])]
st["seat"] = st["position"] + "|" + st["province_std"] + "|" + st["town_std"].fillna("")
yrs = sorted(st["year"].unique())
prev_year = dict(zip(yrs[1:], yrs[:-1]))
cur = st[["seat", "year", "person_uid"]].drop_duplicates()
nxt = cur.assign(year=cur["year"].map(prev_year))
sp = cur.merge(nxt, on=["seat", "year"], suffixes=("_a", "_b"))
sp = sp[sp["person_uid_a"] != sp["person_uid_b"]]
succ = pd.MultiIndex.from_arrays([sp[["person_uid_a", "person_uid_b"]].min(axis=1),
                                  sp[["person_uid_a", "person_uid_b"]].max(axis=1)]).unique()

# Rule 3: paternal kin (same last name)
pt = pairs_within(people.dropna(subset=["last_key", "home_town"]), ["home_place", "home_town", "last_key"])
pt = pt.merge(town_ok, on=["home_place", "home_town", "last_key"], how="left")
pt["succession"] = pd.MultiIndex.from_frame(pt[["person_uid_a", "person_uid_b"]]).isin(succ)
pt = pt[pt["p_value"].notna() | pt["succession"]]
e_pat_town = make_edges(pt, "paternal_kin", "medium", "same paternal family", pt["p_value"], pt["succession"])

# (governors, board members, House reps have no town, so the town test can't apply to them)
PROVINCIAL = ["GOVERNOR", "VICE GOVERNOR", "PROVINCIAL BOARD MEMBER", HOUSE, "SENATOR"]
prov_post = terms[terms["position"].isin(PROVINCIAL)].groupby("person_uid").size().gt(0)
prov_strong = prov[(prov["p_value"] < P_MAX) & (prov["n"] / prov["expected"] >= 7)][["home_place", "last_key", "p_value"]]
po = pairs_within(people.dropna(subset=["last_key"]), ["home_place", "last_key"]).merge(prov_strong, on=["home_place", "last_key"])
po = po[po["person_uid_a"].map(prov_post).fillna(False) | po["person_uid_b"].map(prov_post).fillna(False)]
po["succession"] = pd.MultiIndex.from_frame(po[["person_uid_a", "person_uid_b"]]).isin(succ)
e_pat_office = make_edges(po, "paternal_kin", "medium", "same paternal family (provincial office)", po["p_value"], po["succession"])

pp = pairs_within(people.dropna(subset=["last_key"]), ["home_place", "last_key"]).merge(prov_ok, on=["home_place", "last_key"])
e_pat_prov = make_edges(pp, "paternal_kin", "weak", "same paternal family", pp["p_value"])

# Rule 4: maternal kin (A's middle name = B's last name)
mk = with_mid[["home_place", "middle_key", "person_uid"]].merge(
    people.dropna(subset=["last_key"])[["home_place", "last_key", "person_uid"]],
    left_on=["home_place", "middle_key"], right_on=["home_place", "last_key"], suffixes=("_a", "_b"))
mk = mk[mk["person_uid_a"] != mk["person_uid_b"]].copy()
mk = mk[mk["person_uid_a"].map(info["last_key"]) != mk["last_key"]]   # middle = own surname adds nothing new
mk["home_town"] = mk["person_uid_b"].map(info["home_town"])
same_town = mk["person_uid_a"].map(info["home_town"]).eq(mk["home_town"])
mt = mk[same_town].merge(town_ok, on=["home_place", "home_town", "last_key"])
mp = mk[~same_town].merge(prov_ok, on=["home_place", "last_key"])
hint = "A's mother is from B's family"
e_mat = pd.concat([make_edges(mt, "maternal_kin", "medium", hint, mt["p_value"]),
                   make_edges(mp, "maternal_kin", "weak", hint, mp["p_value"])], ignore_index=True)

# Rule 5: maternal cousins (same middle name, different last names, same town)
mc = pairs_within(with_mid.dropna(subset=["home_town"]), ["home_place", "home_town", "middle_key"])
mc = mc[mc["person_uid_a"].map(info["last_key"]) != mc["person_uid_b"].map(info["last_key"])]
mc = mc.merge(town_ok.rename(columns={"last_key": "middle_key"}), on=["home_place", "home_town", "middle_key"])
e_cousin = make_edges(mc, "maternal_cousin", "weak", "possible first cousins", mc["p_value"])

for n, e in [("nuclear_family", e_nuclear), ("father_son", e_father), ("paternal_kin (same town)", e_pat_town),
             ("paternal_kin (provincial office)", e_pat_office), ("paternal_kin (same province)", e_pat_prov),
             ("maternal_kin", e_mat), ("maternal_cousin", e_cousin)]:
    print(f"{n:34s} {len(e):>8,}   {e['tier'].value_counts().to_dict()}")
print("same-seat successions found:", int(e_pat_town["succession"].sum()))

e = pd.concat([e_nuclear, e_father, e_pat_town, e_pat_office, e_pat_prov, e_mat, e_cousin], ignore_index=True)
a = e[["person_a", "person_b"]].min(axis=1)
b = e[["person_a", "person_b"]].max(axis=1)
e["person_a"], e["person_b"] = a, b
e["rank"] = e["tier"].map({"strong": 0, "medium": 1, "weak": 2})
e = e.sort_values(["person_a", "person_b", "rank"])
edges = e.groupby(["person_a", "person_b"], sort=False).agg(
    relation=("relation", "first"), tier=("tier", "first"), relation_hint=("relation_hint", "first"),
    all_relations=("relation", lambda s: ",".join(sorted(set(s)))),
    p_value=("p_value", "min"), succession=("succession", "max")).reset_index()
edges["weight"] = edges["tier"].map({"strong": 1.0, "medium": 0.7, "weak": 0.4})
print(f"rule hits: {len(e):,} -> unique pairs: {len(edges):,}")

# Possible same person under two IDs (e.g. Lissa / Lissa Marie Streegan)
dp = pairs_within(people.dropna(subset=["last_key", "first_name"]), ["home_place", "last_key"])
A, B = info.loc[dp["person_uid_a"]], info.loc[dp["person_uid_b"]]
wa = A["first_name"].str.upper().str.findall(r"[A-ZÑ]+").map(set).to_numpy()
wb = B["first_name"].str.upper().str.findall(r"[A-ZÑ]+").map(set).to_numpy()
first_ok = np.array([x <= y or y <= x for x, y in zip(wa, wb)])        # same first name, or one inside the other
def agree(col):
    x, y = A[col].to_numpy(), B[col].to_numpy()
    return pd.isna(x) | pd.isna(y) | (x == y)
suffix_ok = A["suffix"].fillna("").to_numpy() == B["suffix"].fillna("").to_numpy()
fa, la = A["first_year"].astype(float).to_numpy(), A["last_year"].astype(float).to_numpy()
fb, lb = B["first_year"].astype(float).to_numpy(), B["last_year"].astype(float).to_numpy()
never_together = (la < fb) | (lb < fa)                                 # never in office in the same years
keep = first_ok & agree("middle_key") & agree("middle_initial") & suffix_ok & never_together
dups = dp[keep].rename(columns={"person_uid_a": "person_a", "person_uid_b": "person_b"})[["home_place", "last_key", "person_a", "person_b"]]
is_dup = pd.MultiIndex.from_frame(edges[["person_a", "person_b"]]).isin(pd.MultiIndex.from_frame(dups[["person_a", "person_b"]]))
edges = edges[~is_dup].reset_index(drop=True)
print(f"possible duplicate people: {len(dups):,} pairs (removed from kinship links)")

# Place and time info for each link
edges["place"] = edges["person_a"].map(info["home_place"])
ta, tb = edges["person_a"].map(info["home_town"]), edges["person_b"].map(info["home_town"])
edges["same_town"] = ta.notna() & ta.eq(tb)
gap = pd.concat([edges["person_b"].map(info["first_year"]) - edges["person_a"].map(info["last_year"]),
                 edges["person_a"].map(info["first_year"]) - edges["person_b"].map(info["last_year"])], axis=1).max(axis=1)
edges["year_gap"] = gap.clip(lower=0).astype("Int64")                 # 0 = their careers overlapped

print(f"final kinship links: {len(edges):,}\n")
print(edges.groupby(["tier", "relation"]).size().to_string())

# Show a few of the duplicates that were caught
show = dups.head(5).merge(people[["person_uid", "display_name", "first_year", "last_year"]], left_on="person_a", right_on="person_uid") \
               .merge(people[["person_uid", "display_name", "first_year", "last_year"]], left_on="person_b", right_on="person_uid", suffixes=("_a", "_b"))
print(show[["display_name_a", "first_year_a", "last_year_a", "display_name_b", "first_year_b", "last_year_b"]])

# Full kinship network (all strong + medium links), used later by Task 9
G = nx.Graph()
G.add_nodes_from(people["person_uid"])
sm = edges[edges["tier"].isin(["strong", "medium"])]
G.add_edges_from((a, b, {"relation": r, "weight": w}) for a, b, r, w in zip(sm["person_a"], sm["person_b"], sm["relation"], sm["weight"]))
print(f"kinship network: {G.number_of_nodes():,} people, {G.number_of_edges():,} strong/medium links")

# Clans = paternal families: groups joined by nuclear_family, father_son, or paternal_kin links
fam_links = sm[sm["relation"].isin(["nuclear_family", "father_son", "paternal_kin"])]
F = nx.Graph()
F.add_edges_from(zip(fam_links["person_a"], fam_links["person_b"]))
groups = sorted(nx.connected_components(F), key=lambda c: (-len(c), min(c)))   # biggest first; ties broken by ID so numbering is the same every run
clan_of = {pid: f"CLAN-{i:05d}" for i, comp in enumerate(groups, start=1) for pid in comp}

# Alliances = maternal links that connect two DIFFERENT clans (intermarriage between families)
mat = sm[sm["relation"].eq("maternal_kin")]
ca, cb = mat["person_a"].map(clan_of), mat["person_b"].map(clan_of)
ally = pd.DataFrame({"clan_a": ca, "clan_b": cb}).dropna()
ally = ally[ally["clan_a"] != ally["clan_b"]]
ally[["clan_a", "clan_b"]] = np.sort(ally[["clan_a", "clan_b"]].to_numpy(), axis=1)
alliances = ally.value_counts().rename("n_links").reset_index()
n_allies = pd.concat([alliances["clan_a"], alliances["clan_b"]]).value_counts()

# Clan info for each person, and a clan summary table
people = people.drop(columns=["clan_id", "clan_size", "n_relatives", "has_relative_in_office"], errors="ignore")
people["clan_id"] = people["person_uid"].map(clan_of)
people["n_relatives"] = people["person_uid"].map(dict(G.degree())).astype(int)
people["has_relative_in_office"] = people["n_relatives"] > 0
m = people.dropna(subset=["clan_id"])
clans = m.groupby("clan_id").agg(
    clan_surname=("last_name", lambda s: s.str.upper().mode().iloc[0]),
    main_place=("home_place", lambda s: s.mode().iloc[0]),
    n_members=("person_uid", "size"), first_year=("first_year", "min"), last_year=("last_year", "max")).reset_index()
clans["clan_label"] = clans["clan_surname"] + " | " + clans["main_place"]
clans["n_allied_clans"] = clans["clan_id"].map(n_allies).fillna(0).astype(int)
clans = clans.sort_values("n_members", ascending=False).reset_index(drop=True)
people["clan_size"] = people["clan_id"].map(clans.set_index("clan_id")["n_members"]).astype("Int64")

print(f"clans: {len(clans):,} | people in a clan: {people['clan_id'].notna().sum():,} of {len(people):,} ({people['clan_id'].notna().mean():.0%})")
print(f"alliances between clans (maternal links): {len(alliances):,}")
print(f"people with at least one relative in office: {people['has_relative_in_office'].sum():,} ({people['has_relative_in_office'].mean():.0%})")
print(clans[["clan_id", "clan_label", "n_members", "first_year", "last_year", "n_allied_clans"]].head(15))

def show_family(surname, place):
    """Everyone with this surname in this province, with their clan."""
    x = people[(people["last_key"] == surname) & (people["home_place"] == place)]
    return x[["display_name", "positions", "first_year", "last_year", "clan_id", "n_relatives"]].sort_values("first_year")

def relatives_of(name_part, place):
    """All kinship links of one person (search by part of their display name)."""
    me = people[people["display_name"].str.contains(name_part, case=False, na=False) & people["home_place"].eq(place)]
    pid = me["person_uid"].iloc[0]
    e = edges[(edges["person_a"] == pid) | (edges["person_b"] == pid)].copy()
    e["relative"] = e["person_b"].where(e["person_a"] == pid, e["person_a"])
    out = e.merge(people[["person_uid", "display_name", "first_year", "last_year"]], left_on="relative", right_on="person_uid")
    print("Relatives of", me["display_name"].iloc[0])
    return out[["display_name", "relation", "tier", "all_relations", "first_year", "last_year"]].sort_values(["tier", "first_year"])

# Do well-known dynasties each land in ONE clan?
families = [("AMPATUAN", "MAGUINDANAO"), ("ORTEGA", "LA UNION"), ("ABAD", "BATANES"), ("MARCOS", "ILOCOS NORTE"),
            ("ECLEO", "DINAGAT ISLANDS"), ("SINGSON", "ILOCOS SUR"), ("DY", "ISABELA"), ("ROMUALDEZ", "LEYTE")]
rows = []
for s, p in families:
    x = people[(people["last_key"] == s) & (people["home_place"] == p)]
    rows.append({"family": s, "province": p, "people_found": len(x),
                 "in_main_clan": x["clan_id"].value_counts().iloc[0] if x["clan_id"].notna().any() else 0,
                 "n_clans": x["clan_id"].nunique()})
print(pd.DataFrame(rows))
print(show_family("ABAD", "BATANES"))
print(relatives_of("ABAD, Henedina", "BATANES"))

outputs = {
    "politicians": people,                 # one row per person, with clan_id and n_relatives
    "politician_terms": terms,             # one row per term served (use is_primary to count each mandate once)
    "kinship_edges": edges,                # one row per related pair (strong / medium / weak)
    "person_duplicates": dups,             # pairs that are probably one person under two IDs
    "clans": clans,                        # one row per clan (paternal family)
    "clan_alliances": alliances,           # maternal links between two different clans
    "surname_concentration": pd.concat([prov.assign(level="province"), town.assign(level="town")], ignore_index=True),
}
for name, df in outputs.items():
    df.to_parquet(S + f"{name}.parquet", index=False)
    print(f"{name:24s} {len(df):>9,} rows -> data/staging/{name}.parquet")

# Ateneo marks an official "fat" when someone with the SAME SURNAME holds office in the same province in the same year.
# the official has a strong/medium relative (from our kinship links) in office in the same province, same year.
info = people.set_index("person_uid")
sm = edges[edges["tier"].isin(["strong", "medium"])]
both_ways = pd.concat([sm[["person_a", "person_b"]].set_axis(["person_uid", "relative"], axis=1),
                       sm[["person_b", "person_a"]].set_axis(["person_uid", "relative"], axis=1)])
held = terms[terms["is_primary"]].dropna(subset=["province_std", "year"])[["person_uid", "year", "province_std", "position"]].copy()
held["year"] = held["year"].astype(int)
in_office = held[["person_uid", "year", "province_std"]].drop_duplicates()
together = (both_ways.merge(in_office, on="person_uid")
                     .merge(in_office.rename(columns={"person_uid": "relative"}), on=["relative", "year", "province_std"]))
fat_keys = set(zip(together["person_uid"], together["year"], together["province_std"]))
held["our_fat"] = [k in fat_keys for k in zip(held["person_uid"], held["year"], held["province_std"])]

# Match each Ateneo row to our term with the same year, position, province, last and first name (one-to-one only)
a = ateneo.rename(columns={"is_fat_dynasty": "ateneo_fat"})   
held["last_key"] = held["person_uid"].map(info["last_key"])
held["first_key"] = held["person_uid"].map(info["first_key"])
k = ["year", "position", "province_std", "last_key", "first_key"]
matched = held.drop_duplicates(k, keep=False).merge(a.drop_duplicates(k, keep=False)[k + ["ateneo_fat"]], on=k)

agree = (matched["ateneo_fat"] == matched["our_fat"]).mean()
both = (matched["ateneo_fat"] & matched["our_fat"]).sum()
print(f"Ateneo rows matched to our terms: {len(matched):,} of {len(a):,}")
print(f"agreement: {agree:.1%} | of Ateneo's fat officials we also flag: {both / matched['ateneo_fat'].sum():.1%} "
      f"| of ours, Ateneo also flags: {both / matched['our_fat'].sum():.1%}")

# Why we disagree
same_surname = together["person_uid"].map(info["last_key"]).to_numpy() == together["relative"].map(info["last_key"]).to_numpy()
same_keys = set(zip(together.loc[same_surname, "person_uid"], together.loc[same_surname, "year"], together.loc[same_surname, "province_std"]))
ours_only = matched[matched["our_fat"] & ~matched["ateneo_fat"]]
diff_surname = 1 - pd.Series([k in same_keys for k in zip(ours_only["person_uid"], ours_only["year"], ours_only["province_std"])]).mean()
print(f"flagged by us only: {len(ours_only):,}, and {diff_surname:.1%} of them have a relative with a DIFFERENT surname (mother's side or marriage)")
ateneo_only = matched[matched["ateneo_fat"] & ~matched["our_fat"]]
print(f"flagged by Ateneo only: {len(ateneo_only):,}; most common surnames:", ateneo_only["last_key"].value_counts().head(6).to_dict())

print(matched.groupby("year").agg(rows=("our_fat", "size"), ateneo_fat=("ateneo_fat", "mean"),
                            our_fat=("our_fat", "mean")).assign(
    agreement=matched.groupby("year").apply(lambda d: (d["ateneo_fat"] == d["our_fat"]).mean())).round(3))