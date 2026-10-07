"""Suggestions for town names that no reference source knows (task 6 town review)."""

import difflib

import pandas as pd


def suggest_town_fixes(to_check, reference, years_ahead=10, min_shared=3):
    """One row per unknown (province_group, town_std) in to_check, with two clues from reference.

    Both tables need province_group, town_std, year, and last_key columns.
    - spelling: the reference town of the same province group with the closest spelling.
    - shared_town / shared: the reference town where the most of the same surnames held office,
      from the unknown name's first year up to `years_ahead` years later.
    - suggestion: spelling if found, otherwise shared_town if at least `min_shared` surnames match.
    """
    towns = reference.groupby("province_group")["town_std"].agg(lambda s: sorted(set(s)))
    rows = []
    for (group, town), r in to_check.groupby(["province_group", "town_std"]):
        close = difflib.get_close_matches(town, towns.get(group, []), n=1, cutoff=0.8)
        first_year = r["year"].min()
        ref = reference[reference["province_group"].eq(group) & reference["year"].between(first_year, first_year + years_ahead)]
        names = set(r.loc[r["year"].eq(first_year), "last_key"])
        shared = ref[ref["last_key"].isin(names)].groupby("town_std")["last_key"].nunique()
        rows.append({
            "province_group": group,
            "town_std": town,
            "rows": len(r),
            "years": sorted(set(r["year"])),
            "spelling": close[0] if close else None,
            "shared_town": shared.idxmax() if len(shared) else None,
            "shared": int(shared.max()) if len(shared) else 0,
            "of": len(names),
        })
    df = pd.DataFrame(rows)
    df["suggestion"] = df["spelling"].fillna(df["shared_town"].where(df["shared"] >= min_shared))
    return df


def label_suspects(towns, min_other=4, max_own=1):
    """Town-years whose label may be wrong: their officials share at most `max_own` surnames with the
    same town in the next election, but at least `min_other` with another town of the same province.

    towns needs province_group, town_std, year, and last_key columns (rows with a verified town).
    """
    families = towns.groupby(["province_group", "year", "town_std"])["last_key"].agg(set)
    next_year = dict(zip(sorted(towns["year"].unique())[:-1], sorted(towns["year"].unique())[1:]))
    rows = []
    for (group, year, town), names in families.items():
        if year not in next_year or (group, next_year[year]) not in families.index.droplevel(2):
            continue
        later = families.loc[(group, next_year[year])]
        shared = {other: len(names & later_names) for other, later_names in later.items()}
        own = shared.pop(town, 0)
        if shared and max(shared.values()) >= min_other and own <= max_own:
            best = max(shared, key=shared.get)
            rows.append({"province_group": group, "year": year, "town_std": town, "officials": len(names),
                         "shared_with_itself": own, "next_year": next_year[year], "best_other": best, "shared_with_other": shared[best]})
    return pd.DataFrame(rows)