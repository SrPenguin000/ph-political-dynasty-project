# Task 9: Network Resilience & Cascade Simulation Engine

Notebook: `notebooks/05_network_resilience.ipynb`

## How to run

Run after Task 7 and Task 8. Reads `data/staging` (`politicians`, `kinship_edges`, `clans`, `clan_alliances`) and `data/curated` (`town_dynasty_stronghold`, `official_terms_dynastic`). Click **Run All** (under a minute). Results are the same on every run.

## The two networks

| Network | Nodes | Edges | Size |
|---|---|---|---|
| Person network | Politicians | Strong + medium kinship links (same-name "twins" removed, as in Task 8) | 69,376 people, 128,262 links |
| Clan network | Clans (paternal families) | Alliances (maternal links between two clans) | 20,394 clans, 2,274 alliances |

The person network splits into 18,347 separate groups; the largest has only 338 people. **Philippine dynasties form many local islands, not one national web.** Each person has 3.7 relatives on average, and 3,791 clans have at least one ally.

In 2025, 11,545 of the 17,819 officials belong to a clan, spread across 9,112 clans.

## Step 2: Attack test (percolation)

A **family bloc** is a group of 5+ connected relatives. People are removed step by step, either at random or most-connected first, and we track the share of people still in a bloc (`bloc_coverage`). The **robustness index R** is the average coverage over all steps (1 = unbreakable).

| Removed | Random | Targeted (most-connected first) |
|---|---|---|
| 5% | 0.906 | 0.842 |
| 10% | 0.816 | 0.680 |
| 20% | 0.647 | 0.358 |
| 30% | 0.489 | 0.093 |
| **R** | **0.816** | **0.674** |

**Finding:** dynasties survive random losses well but depend on their hub members. Removing the 30% most-connected people breaks almost all family blocs (9.3% of people still in one, vs 48.9% after random removal).

## Step 3: Targeted clan disruption + cascade

**Scenario:** an anti-dynasty rule disqualifies selected clans from their 2025 seats.

**Cascade model (Watts threshold, theta = 0.5):** targeted clans fall first; any clan that has lost half or more of its allies (alliance links) also falls; repeat until nothing changes. Vacated seats are assumed to go to non-dynastic winners.

| Scenario | Targeted | Fell by cascade | Rounds | Officials removed | Mayors | Governors | Stronghold towns left (of 604) | Avg town stronghold % |
|---|---|---|---|---|---|---|---|---|
| Baseline | 0 | 0 | 0 | 0 | 0 | 0 | 604 | 67.9% |
| Top 1 clan | 1 | 1 | 1 | 29 | 5 | 0 | 602 | 67.7% |
| Top 10 clans | 10 | 18 | 4 | 141 | 28 | 3 | 591 | 67.2% |
| Top 50 clans | 50 | 87 | 4 | 448 | 80 | 15 | 552 | 65.6% |
| Top 100 clans | 100 | 122 | 4 | 693 | 135 | 24 | 516 | 64.5% |
| **Top 250 clans** | 250 | **243** | 4 | **1,283** | 251 | 42 | **441** | 61.6% |
| Top clan in every province | 87 | 89 | 4 | 511 | 100 | 24 | 546 | 65.5% |
| **250 random clans** | 250 | **68** | 3 | **390** | 49 | 4 | **536** | 65.8% |

**Findings:**

1. Targeting the biggest families removes about **3x more officials** than targeting the same number of random families (1,283 vs 390), and breaks far more strongholds (163 vs 68 stronghold towns lost).
2. Alliances spread the damage: **243** allied clans fall with the top 250, vs **68** with random clans.
3. Dynasties are resilient overall: even the strongest scenario only lowers the average town stronghold % from 67.9% to 61.6%, because power is spread across 9,112 clans holding seats.
4. Cascades stay small and local (at most 4 rounds).

## Step 4: Clan resilience

One row per clan holding seats in 2025 (9,112 clans).

| Column | Meaning |
|---|---|
| `seats_2025` | Officials from the clan in 2025 |
| `n_members` | Clan members who ever held office |
| `n_allies` | Clans linked by alliances |
| `cascade_reach` | Other clans that fall if only this clan is disrupted |
| `connected_after_hub_removal` | Share of the clan still connected after removing its most-connected member (1.0 = holds together) |
| `years_in_power` | `last_year - first_year` |

**Findings:** the median clan stays 100% connected after losing its most-connected member, so a dynasty does not depend on one person. 1,812 clans would topple at least one ally if disrupted; BALINDONG (Lanao del Sur) has the widest reach among the biggest clans (8). The longest-running clans in power in 2025 are SISON, Pangasinan (since 1912) and VELOSO, Leyte (since 1916).

## Outputs (`data/curated`)

| File | Rows | Contents |
|---|---|---|
| `network_attack_curves.parquet` | 16 | Step 2 results (strategy, fraction removed, bloc coverage, largest bloc) |
| `clan_disruption_scenarios.parquet` | 8 | Step 3 results |
| `clan_resilience.parquet` | 9,112 | Step 4 results |

Files are overwritten on each run.

## Reproducibility

Clans tied in size are numbered by their smallest member ID (Task 7 Step 9), and clans tied in seats are ranked by `clan_id` (Step 3). Random scenarios use fixed seeds. Re-running gives identical results.

## Known limitations

- **Maguindanao split:** people elected under MAGUINDANAO DEL NORTE / DEL SUR (2022 onward) were not linked to their earlier MAGUINDANAO records, so those clans (e.g. AMPATUAN, MIDTIMBANG, SANGKI, SINSUAT) show `first_year = 2025` and `years_in_power = 0`. Task 6 now provides `province_group`, which Task 7 already uses for the 1988-1998 Ateneo rows; using it for all linking and kinship rules would fix this.
- The cascade only spreads through **maternal alliances**; business, party, or patronage ties are not in the data.
- Vacated seats are assumed to go to non-dynastic winners; in reality another dynasty might win them.
- Theta (0.5) is a modeling choice; a lower theta would spread cascades further.
- All results inherit the name-based kinship limits from `docs/task7_kinship.md` and the time limits from `docs/task8_stronghold.md`.

