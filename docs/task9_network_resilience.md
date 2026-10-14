# Task 9: Network Resilience & Cascade Simulation Engine

Script (run by Airflow): `src/curate/05_network_resilience.py`
Notebook (same steps, for exploring and checking results): `notebooks/05_network_resilience.ipynb`

## How to run

Run after Task 7 and Task 8. Reads `data/staging` (`politicians`, `kinship_edges`, `clans`, `clan_alliances`) and `data/curated` (`town_dynasty_stronghold`, `official_terms_dynastic`). From the project folder:

```
python src/curate/05_network_resilience.py
```

It takes under a minute. In Airflow, this is the task `run_network_resilience`, which runs after `run_dynasty_stronghold`. **Run it only after Task 8 has been rerun on the same Task 7 output**, because it joins Task 7's clan IDs with Task 8's curated tables.

## The two networks

| Network | Nodes | Edges | Size |
|---|---|---|---|
| Person network | Politicians | Strong + medium kinship links (same-name "twins" removed, as in Task 8) | 66,562 people, 116,695 links |
| Clan network | Clans (paternal families) | Alliances (maternal links between two clans) | 20,288 clans, 2,244 alliances |

The person network splits into 18,260 separate groups; the largest has only 329 people. **Philippine dynasties form many local islands, not one national web.** Each person has 3.5 relatives on average, and 3,748 clans have at least one ally.

In 2025, 11,565 of the 17,817 officials belong to a clan, spread across 9,149 clans.

## Step 2: Attack test (percolation)

A **family bloc** is a group of 5+ connected relatives. People are removed step by step, either at random or most-connected first, and we track the share of people still in a bloc (`bloc_coverage`). The **robustness index R** is the average coverage over all steps (1 = unbreakable).

| Removed | Random | Targeted (most-connected first) |
|---|---|---|
| 5% | 0.906 | 0.825 |
| 10% | 0.813 | 0.647 |
| 20% | 0.638 | 0.309 |
| 30% | 0.484 | 0.056 |
| **R** | **0.813** | **0.650** |

**Finding:** dynasties survive random losses well but depend on their hub members. Removing the 30% most-connected people breaks almost all family blocs (5.6% of people still in one, vs 48.4% after random removal).

## Step 3: Targeted clan disruption + cascade

**Scenario:** an anti-dynasty rule disqualifies selected clans from their 2025 seats.

**Cascade model (Watts threshold, theta = 0.5):** targeted clans fall first; any clan that has lost half or more of its allies (alliance links) also falls; repeat until nothing changes. Vacated seats are assumed to go to non-dynastic winners.

| Scenario | Targeted | Fell by cascade | Rounds | Officials removed | Mayors | Governors | Stronghold towns left (of 600) | Avg town stronghold % |
|---|---|---|---|---|---|---|---|---|
| Baseline | 0 | 0 | 0 | 0 | 0 | 0 | 600 | 68.1% |
| Top 1 clan | 1 | 0 | 0 | 15 | 1 | 0 | 598 | 68.1% |
| Top 10 clans | 10 | 26 | 4 | 128 | 28 | 4 | 586 | 67.5% |
| Top 50 clans | 50 | 102 | 4 | 436 | 76 | 16 | 552 | 65.9% |
| Top 100 clans | 100 | 137 | 4 | 681 | 131 | 26 | 515 | 64.8% |
| **Top 250 clans** | 250 | **255** | 4 | **1,260** | 245 | 42 | **439** | 61.9% |
| Top clan in every province | 87 | 86 | 4 | 489 | 93 | 25 | 545 | 65.9% |
| **250 random clans** | 250 | **88** | 4 | **432** | 49 | 4 | **518** | 65.8% |

**Findings:**

1. Targeting the biggest families removes about **2.9x more officials** than targeting the same number of random families (1,260 vs 432), and breaks about twice as many strongholds (161 vs 82 stronghold towns lost).
2. Alliances spread the damage: **255** allied clans fall with the top 250, vs **88** with random clans.
3. Dynasties are resilient overall: even the strongest scenario only lowers the average town stronghold % from 68.1% to 61.9%, because power is spread across 9,149 clans holding seats.
4. Cascades stay small and local (at most 4 rounds).

## Step 4: Clan resilience

One row per clan holding seats in 2025 (9,149 clans).

| Column | Meaning |
|---|---|
| `seats_2025` | Officials from the clan in 2025 |
| `n_members` | Clan members who ever held office |
| `n_allies` | Clans linked by alliances |
| `cascade_reach` | Other clans that fall if only this clan is disrupted |
| `connected_after_hub_removal` | Share of the clan still connected after removing its most-connected member (1.0 = holds together) |
| `years_in_power` | `last_year - first_year` |

**Findings:** the median clan stays 100% connected after losing its most-connected member, so a dynasty does not depend on one person. 1,816 clans would topple at least one ally if disrupted; among the biggest clans, AMPATUAN (Maguindanao) has the widest reach (9), followed by BALINDONG (Lanao del Sur, 8). The longest-running clans in power in 2025 are SISON, Pangasinan (since 1912) and VELOSO, Leyte (since 1916).

## Outputs (`data/curated`)

| File | Rows | Contents |
|---|---|---|
| `network_attack_curves.parquet` | 16 | Step 2 results (strategy, fraction removed, bloc coverage, largest bloc) |
| `clan_disruption_scenarios.parquet` | 8 | Step 3 results |
| `clan_resilience.parquet` | 9,149 | Step 4 results |

Files are overwritten on each run.

## Reproducibility

Clans tied in size are numbered by their smallest member ID (Task 7 Step 9), and clans tied in seats are ranked by `clan_id` (Step 3). Random scenarios use fixed seeds, so the attack test and the disruption scenarios repeat exactly. One known exception: when two members of a clan are equally connected, the choice of the "most-connected member" in Step 4 can differ between runs, which can change `connected_after_hub_removal` for a few clans. Breaking that tie by person ID fixes it.

## Known limitations

- **Maguindanao split:** people elected under MAGUINDANAO DEL NORTE / DEL SUR (2022 onward) were not linked to their earlier MAGUINDANAO records, so some clans (e.g. AMPATUAN and MIDTIMBANG of Maguindanao del Sur, 15 and 9 seats in 2025) show `first_year = 2025` and `years_in_power = 0`. Task 6 now provides `province_group`, which Task 7 already uses for the 1988-1998 Ateneo rows; using it for all linking and kinship rules would fix this.
- The cascade only spreads through **maternal alliances**; business, party, or patronage ties are not in the data.
- Vacated seats are assumed to go to non-dynastic winners; in reality another dynasty might win them.
- Theta (0.5) is a modeling choice; a lower theta would spread cascades further.
- All results inherit the name-based kinship limits from `docs/task7_kinship.md` and the time limits from `docs/task8_stronghold.md`.