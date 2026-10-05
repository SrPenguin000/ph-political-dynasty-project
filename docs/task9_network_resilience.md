# Task 9: Network Resilience & Cascade Simulation Engine

Notebook: `notebooks/05_network_resilience.ipynb`

## How to run

Run after Task 7 and Task 8. Reads `data/staging` (`politicians`, `kinship_edges`, `clans`, `clan_alliances`) and `data/curated` (`town_dynasty_stronghold`, `official_terms_dynastic`). Click **Run All** (under a minute). Results are the same on every run.

## The two networks

| Network | Nodes | Edges | Size |
|---|---|---|---|
| Person network | Politicians | Strong + medium kinship links (same-name "twins" removed, as in Task 8) | 54,768 people, 96,327 links |
| Clan network | Clans (paternal families) | Alliances (maternal links between two clans) | 16,481 clans, 1,649 alliances |

The person network splits into 14,907 separate groups; the largest has only 267 people. **Philippine dynasties form many local islands, not one national web.**

## Step 2: Attack test (percolation)

A **family bloc** is a group of 5+ connected relatives. People are removed step by step, either at random or most-connected first, and we track the share of people still in a bloc (`bloc_coverage`). The **robustness index R** is the average coverage over all steps (1 = unbreakable).

| Removed | Random | Targeted (most-connected first) |
|---|---|---|
| 5% | 0.906 | 0.832 |
| 10% | 0.817 | 0.664 |
| 20% | 0.647 | 0.316 |
| 30% | 0.488 | 0.056 |
| **R** | **0.816** | **0.657** |

**Finding:** dynasties survive random losses well but depend on their hub members. Removing the 30% most-connected people breaks almost all family blocs.

## Step 3: Targeted clan disruption + cascade

**Scenario:** an anti-dynasty rule disqualifies selected clans from their 2025 seats.

**Cascade model (Watts threshold, theta = 0.5):** targeted clans fall first; any clan that has lost half or more of its allies (alliance links) also falls; repeat until nothing changes. Vacated seats are assumed to go to non-dynastic winners.

| Scenario | Targeted | Fell by cascade | Rounds | Officials removed | Mayors | Governors | Stronghold towns left (of 519) | Avg town stronghold % |
|---|---|---|---|---|---|---|---|---|
| Baseline | 0 | 0 | 0 | 0 | 0 | 0 | 519 | 64.9% |
| Top 1 clan | 1 | 1 | 1 | 29 | 5 | 0 | 517 | 64.7% |
| Top 10 clans | 10 | 15 | 4 | 140 | 27 | 3 | 508 | 64.2% |
| Top 50 clans | 50 | 74 | 4 | 464 | 84 | 17 | 474 | 62.6% |
| Top 100 clans | 100 | 102 | 4 | 704 | 138 | 27 | 443 | 61.5% |
| **Top 250 clans** | 250 | **193** | 4 | **1,281** | 255 | 46 | **380** | 58.7% |
| Top clan in every province | 87 | 72 | 4 | 531 | 101 | 29 | 470 | 62.5% |
| **250 random clans** | 250 | **62** | 3 | **392** | 48 | 3 | **456** | 62.8% |

**Findings:**

1. Targeting the biggest families removes about **3x more officials** than targeting the same number of random families (1,281 vs 392), and breaks far more strongholds.
2. Alliances spread the damage: **193** allied clans fall with the top 250, vs **62** with random clans.
3. Dynasties are resilient overall: even the strongest scenario only lowers the average town stronghold % from 64.9% to 58.7%, because power is spread across 8,656 clans holding seats.
4. Cascades stay small and local (at most 4 rounds).

## Step 4: Clan resilience

One row per clan holding seats in 2025 (8,656 clans).

| Column | Meaning |
|---|---|
| `seats_2025` | Officials from the clan in 2025 |
| `n_members` | Clan members who ever held office |
| `n_allies` | Clans linked by alliances |
| `cascade_reach` | Other clans that fall if only this clan is disrupted |
| `connected_after_hub_removal` | Share of the clan still connected after removing its most-connected member (1.0 = holds together) |
| `years_in_power` | `last_year - first_year` |

**Findings:** the median clan stays 100% connected after losing its most-connected member, so a dynasty does not depend on one person. 1,483 clans would topple at least one ally if disrupted; BALINDONG (Lanao del Sur) has the widest reach among the biggest clans (8). The longest-running clans in power in 2025 are SISON, Pangasinan (since 1912) and VELOSO, Leyte (since 1916).

## Outputs (`data/curated`)

| File | Rows | Contents |
|---|---|---|
| `network_attack_curves.parquet` | 16 | Step 2 results (strategy, fraction removed, bloc coverage, largest bloc) |
| `clan_disruption_scenarios.parquet` | 8 | Step 3 results |
| `clan_resilience.parquet` | 8,656 | Step 4 results |

Files are overwritten on each run.

## Reproducibility

Clans tied in size are numbered by their smallest member ID (Task 7 Step 9), and clans tied in seats are ranked by `clan_id` (Step 3). Random scenarios use fixed seeds. Re-running gives identical results.

## Known limitations

- **Maguindanao split:** people elected under MAGUINDANAO DEL NORTE / DEL SUR were not linked to their earlier MAGUINDANAO records, so those clans show `first_year = 2025` and `years_in_power = 0`. This is the open Maguindanao question from Task 6 (section G); a fix would treat the old and new names as one area when linking people.
- The cascade only spreads through **maternal alliances**; business, party, or patronage ties are not in the data.
- Vacated seats are assumed to go to non-dynastic winners; in reality another dynasty might win them.
- Theta (0.5) is a modeling choice; a lower theta would spread cascades further.
- All results inherit the name-based kinship limits from `docs/task7_kinship.md` and the time limits from `docs/task8_stronghold.md`.

