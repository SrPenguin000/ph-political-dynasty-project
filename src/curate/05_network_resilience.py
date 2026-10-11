import random
import numpy as np
import pandas as pd
import networkx as nx

S = "data/staging/"
C = "data/curated/"
people = pd.read_parquet(S + "politicians.parquet")
edges = pd.read_parquet(S + "kinship_edges.parquet")
clans = pd.read_parquet(S + "clans.parquet")
alliances = pd.read_parquet(S + "clan_alliances.parquet")
town = pd.read_parquet(C + "town_dynasty_stronghold")
officials = pd.read_parquet(C + "official_terms_dynastic")
town["year"] = town["year"].astype(int)            # partition folders come back as a category; make it a number
officials["year"] = officials["year"].astype(int)

LATEST = 2025
LOCAL = ["MAYOR", "VICE MAYOR", "COUNCILOR"]
info = people.set_index("person_uid")

# Person network: strong + medium kinship links, without same-name "twins" (same rule as Task 8)
sm = edges[edges["tier"].isin(["strong", "medium"])]
A, B = info.loc[sm["person_a"]], info.loc[sm["person_b"]]
twin = ((A["last_key"].to_numpy() == B["last_key"].to_numpy()) & (A["first_key"].to_numpy() == B["first_key"].to_numpy())
        & (A["middle_key"].isna().to_numpy() | B["middle_key"].isna().to_numpy() | (A["middle_key"].to_numpy() == B["middle_key"].to_numpy())))
sm = sm[~twin]
G = nx.Graph()
G.add_edges_from(zip(sm["person_a"], sm["person_b"]))

# Clan network: clans = nodes, alliances (maternal links between clans) = edges
CG = nx.Graph()
CG.add_nodes_from(clans["clan_id"])
CG.add_edges_from(zip(alliances["clan_a"], alliances["clan_b"]))

pieces = sorted((len(c) for c in nx.connected_components(G)), reverse=True)
print(f"person network: {G.number_of_nodes():,} people, {G.number_of_edges():,} links, {len(pieces):,} separate groups, largest = {pieces[0]}")
print(f"average relatives per person: {2 * G.number_of_edges() / G.number_of_nodes():.1f}")
allied = [c for c in CG if CG.degree(c) > 0]
print(f"clan network: {CG.number_of_nodes():,} clans, {CG.number_of_edges():,} alliances, {len(allied):,} clans have at least one ally")
o = officials[officials["year"].eq(LATEST)]
print(f"{LATEST}: {len(o):,} officials, {o['clan_id'].notna().sum():,} belong to a clan, {o['clan_id'].nunique():,} clans hold seats")

def bloc_coverage(H, min_size=5):
    """People who are still in a family bloc of 5+ connected relatives."""
    return sum(len(c) for c in nx.connected_components(H) if len(c) >= min_size)

def largest_bloc(H):
    return max((len(c) for c in nx.connected_components(H)), default=0)

N = G.number_of_nodes()
base = bloc_coverage(G)
by_degree = [n for n, _ in sorted(G.degree, key=lambda x: -x[1])]     # most-connected people first
fractions = [0, 0.01, 0.02, 0.05, 0.10, 0.15, 0.20, 0.30]

rows = []
for strategy in ["random", "targeted (most-connected first)"]:
    for f in fractions:
        k = int(f * N)
        if strategy == "random":
            results = []
            for seed in range(3):                                   # average of 3 random runs
                H = G.copy()
                H.remove_nodes_from(random.Random(seed).sample(list(G.nodes), k))
                results.append((bloc_coverage(H), largest_bloc(H)))
            cov, big = np.mean(results, axis=0)
        else:
            H = G.copy()
            H.remove_nodes_from(by_degree[:k])
            cov, big = bloc_coverage(H), largest_bloc(H)
        rows.append({"strategy": strategy, "fraction_removed": f, "people_removed": k,
                     "bloc_coverage": round(cov / base, 3), "largest_bloc": int(big)})
attack_curves = pd.DataFrame(rows)
print(attack_curves.pivot(index="fraction_removed", columns="strategy", values="bloc_coverage"))
robustness = attack_curves.groupby("strategy")["bloc_coverage"].mean().round(3)
print("robustness index R (1 = unbreakable, lower = more fragile):")
print(robustness.to_string())

def cascade(seed_clans, theta=0.5):
    """Watts threshold cascade on the clan alliance network.
    A clan falls when at least `theta` of its allies have fallen. Returns (fallen clans, rounds)."""
    fallen, rounds = set(seed_clans), 0
    while True:
        new = {c for f in fallen for c in CG[f] if c not in fallen
               and sum(n in fallen for n in CG[c]) / CG.degree(c) >= theta}
        if not new:
            return fallen, rounds
        fallen |= new
        rounds += 1

towns_now = town[town["year"].eq(LATEST)].set_index(["province_std", "town_std"])

def impact(fallen):
    """Seats vacated by fallen clans, and what happens to town strongholds (seats go to non-dynastic winners)."""
    hit = o[o["clan_id"].isin(fallen)]
    lost = (hit[hit["position"].isin(LOCAL)].dropna(subset=["town_std"])
            .groupby(["province_std", "town_std"])["is_dynastic"].sum().rename("lost_dynastic"))
    tt = towns_now.join(lost, how="left").fillna({"lost_dynastic": 0})
    new_share = (tt["n_dynastic"] - tt["lost_dynastic"]) / tt["n_officials"]
    return {"officials_removed": hit["person_uid"].nunique(),
            "mayors_removed": int(hit["position"].eq("MAYOR").sum()),
            "governors_removed": int(hit["position"].eq("GOVERNOR").sum()),
            "stronghold_towns_after": int((new_share >= 0.75).sum()),
            "avg_town_share_after": round(float(new_share.mean()), 3)}

# Seats each clan holds in 2025, and the biggest clan in each province
seats = (o.dropna(subset=["clan_id"]).groupby("clan_id")["person_uid"].nunique()
           .reset_index(name="n").sort_values(["n", "clan_id"], ascending=[False, True]).set_index("clan_id")["n"])  # ties broken by clan_id
top_per_province = (o.dropna(subset=["clan_id"]).groupby(["province_std", "clan_id"])["person_uid"].nunique().rename("s").reset_index()
                    .sort_values(["s", "clan_id"], ascending=[False, True]).drop_duplicates("province_std"))

scenarios = {"no disruption (baseline)": []}
scenarios.update({f"top {k} clans by seats": list(seats.index[:k]) for k in [1, 10, 50, 100, 250]})
scenarios["top clan in every province"] = list(top_per_province["clan_id"].unique())
scenarios["250 random clans"] = random.Random(0).sample(list(seats.index), 250)

rows = []
for name, seed in scenarios.items():
    fallen, rounds = cascade(seed)
    row = {"scenario": name, "clans_targeted": len(seed), "clans_fell_by_cascade": len(fallen) - len(seed), "cascade_rounds": rounds}
    row.update(impact(fallen))
    rows.append(row)
scenario_results = pd.DataFrame(rows)
print(scenario_results)

# Systemic importance: how many OTHER clans fall if only this clan is disrupted
reach = {c: len(cascade([c])[0]) - 1 for c in seats.index if CG.degree(c) > 0}

# Hub dependence: remove a clan's most-connected member; how much of the clan stays connected?
members = people.dropna(subset=["clan_id"]).groupby("clan_id")["person_uid"].apply(list)
def after_hub_removal(clan_id):
    sub = G.subgraph(members[clan_id]).copy()
    if sub.number_of_nodes() < 3:
        return np.nan                                   # too small to measure
    hub = max(sub.degree, key=lambda x: x[1])[0]
    sub.remove_node(hub)
    return round(largest_bloc(sub) / sub.number_of_nodes(), 3)

clan_resilience = pd.DataFrame({"clan_id": seats.index, "seats_2025": seats.values})
clan_resilience = clan_resilience.merge(clans[["clan_id", "clan_label", "n_members", "first_year", "last_year"]], on="clan_id", how="left")
clan_resilience["n_allies"] = clan_resilience["clan_id"].map(dict(CG.degree())).fillna(0).astype(int)
clan_resilience["cascade_reach"] = clan_resilience["clan_id"].map(reach).fillna(0).astype(int)
clan_resilience["connected_after_hub_removal"] = clan_resilience["clan_id"].map(after_hub_removal)
clan_resilience["years_in_power"] = clan_resilience["last_year"] - clan_resilience["first_year"]

print(f"clans with seats in {LATEST}: {len(clan_resilience):,}")
print(f"clans whose disruption topples at least one allied clan: {(clan_resilience['cascade_reach'] > 0).sum():,}")
print(f"median share of a clan still connected after losing its most-connected member: {clan_resilience['connected_after_hub_removal'].median():.0%}")
print(clan_resilience.head(15))

from pathlib import Path
out = Path(C)
for name, df in {"network_attack_curves": attack_curves,
                 "clan_disruption_scenarios": scenario_results,
                 "clan_resilience": clan_resilience}.items():
    df.to_parquet(out / f"{name}.parquet", index=False)        # overwrites each run (idempotent)
    print(f"{name:28s} {len(df):>6,} rows -> data/curated/{name}.parquet")