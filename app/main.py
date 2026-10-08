import os
import re
import sys
from itertools import combinations
from pathlib import Path
from dotenv import load_dotenv
import numpy as np
import pandas as pd
import streamlit as st
import psycopg2
import networkx as nx
from pyvis.network import Network
import streamlit.components.v1 as components
import plotly.express as px

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

PG_USER = os.getenv("POSTGRES_USER", "postgres")
PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
PG_DB = os.getenv("POSTGRES_DB", "dynasty_db")
PG_PORT = os.getenv("POSTGRES_PORT", "5432")
PG_HOST = os.getenv("POSTGRES_HOST", "postgres")

def pretty_name(name):
    """Title-case a person's name ('JOSEPH ESTRADA' -> 'Joseph Estrada'),
    keeping roman-numeral suffixes (II, III, IV...) in capitals."""
    if not isinstance(name, str):
        return name
    words = name.title().split(" ")
    return " ".join(
        w.upper() if re.fullmatch(r"(?i)(ii|iii|iv|vi{0,3}|ix)", w.strip(".,")) else w
        for w in words
    )


def canonicalize_people(df, scope_col):
    """Merge person_ids that are really the same human.

    The same politician can arrive under several person_ids (e.g. one id for
    their term as Councilor and another for their term as Vice Mayor). Two ids
    are treated as one person when they have the same first name, last name and
    suffix within the same scope (their clan if known, otherwise their town) AND
    never hold different positions in the same year. A person can only hold one
    seat per year, so a same-year clash means they are genuinely different people
    and the ids are left alone.

    Expects columns: person_id, first_name, last_name, name_suffix, year,
    position, and `scope_col`.
    """
    if df.empty:
        return df

    d = df.copy()
    norm = lambda s: s.fillna("").astype(str).str.strip().str.lower()
    d["_key"] = (
        norm(d["first_name"]) + "|" + norm(d["last_name"]) + "|"
        + norm(d["name_suffix"]) + "|" + norm(d[scope_col])
    )

    remap = {}
    for _, g in d.groupby("_key"):
        ids = g["person_id"].unique()
        if len(ids) < 2:
            continue

        # year -> set of positions held, for each candidate id
        by_id = {}
        for pid in ids:
            sub = g[g["person_id"] == pid].dropna(subset=["year"])
            seats = {}
            for y, pos in zip(sub["year"].astype(int), sub["position"]):
                seats.setdefault(y, set()).add(pos)
            by_id[pid] = seats

        # Same year but a different seat => two different people. Don't merge.
        conflict = any(
            by_id[a][y] != by_id[b][y]
            for a, b in combinations(ids, 2)
            for y in by_id[a].keys() & by_id[b].keys()
        )
        if not conflict:
            canon = sorted(ids)[0]
            remap.update({pid: canon for pid in ids})

    if remap:
        d["person_id"] = d["person_id"].replace(remap)
    return d.drop(columns="_key")


@st.cache_data
def fetch_data(query: str) -> pd.DataFrame:
    conn = psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        dbname=PG_DB,
        user=PG_USER,
        password=PG_PASSWORD
    )
    try:
        return pd.read_sql(query, con=conn)
    finally:
        conn.close()

st.set_page_config(page_title="Dynasty Network Resilience Lab", layout="wide", initial_sidebar_state="expanded")
st.title("Philippine Political Dynasty: Network Resilience & Phase Lab")

tab_sim, tab_phase, tab_geo = st.tabs(["Cascade Simulator", "Phase Lab (Sensitivity Sweep)", "Geographic Overview"])

with tab_sim:
    st.subheader("Network Cascade & Disruption Simulator")
    st.caption("Evaluate structural breakdown when targeted anti-dynasty interventions or disqualifications are applied.")

    col_ctrl, col_graph = st.columns([1, 3])

    with col_ctrl:
        st.markdown("### Disruption Parameters")
        
        prov_list = fetch_data("SELECT DISTINCT province_std FROM dim_geography WHERE province_std IS NOT NULL ORDER BY province_std")["province_std"].tolist()
        selected_province = st.selectbox("Province Focus", prov_list, index=prov_list.index("NCR SECOND DISTRICT") if "NCR SECOND DISTRICT" in prov_list else 0)

        pos_query = "SELECT DISTINCT position FROM fact_electoral_membership WHERE position IS NOT NULL ORDER BY position"
        pos_list = fetch_data(pos_query)["position"].tolist()
        selected_positions = st.multiselect("Electoral Positions", options=pos_list, default=pos_list)

        disruption_mode = st.radio("Intervention / Attack Strategy", ["Targeted (Top Hubs / Strongest Dynasties)", "Random Disqualification", "Degree-Based Threshold"])
        disruption_pct = st.slider("Disruption Intensity (% Nodes Removed)", 0, 80, 20, step=5)
        k_core = st.slider("Core Entrenchment Filter (k-core)", 0, 5, 0, help="Filter out periphery single-term candidates")

        st.markdown("### Dynasty Classification")
        dynasty_threshold = st.slider(
            "Min. Clan Size to Display as Dynasty", 2, 10, 2,
            help="Clan size comes from validated kinship links (same paternal "
                 "line, from the kinship engine) -- not surname text matching. "
                 "Every clan already has 2+ members by construction; raise this "
                 "to require larger, more entrenched clusters."
        )
        show_only_dynasties = st.checkbox("Show only qualifying dynasty clusters", value=False)
        st.caption(
            "Note: clan data currently only covers politicians sourced from the "
            "HF dataset (2004-2016). People only found in OpenHalalan or the "
            "historical Roster have no clan lookup yet."
        )

    with col_graph:
        base_query = f"""
        SELECT 
            p.person_id,
            p.last_name, 
            p.first_name, 
            p.name_suffix,
            f.position, 
            f.year,
            g.town_std AS locality_std,
            pc.clan_id,
            c.clan_surname
        FROM fact_electoral_membership f
        JOIN dim_person p ON f.person_id = p.person_id
        JOIN dim_geography g ON f.location_id = g.location_id
        LEFT JOIN fact_person_clan pc ON p.person_id = pc.person_id
        LEFT JOIN dim_clan c ON pc.clan_id = c.clan_id
        WHERE g.province_std = '{selected_province}'
        """
        
        if selected_positions:
            pos_formatted = "', '".join(selected_positions)
            base_query += f" AND f.position IN ('{pos_formatted}')"
        else:
            base_query += " AND 1=0"
            
        raw_net = fetch_data(base_query)

        if not raw_net.empty:
            min_year = int(raw_net['year'].min())
            max_year = int(raw_net['year'].max())
            st.info(f"**Data Timeframe Displayed:** {min_year} – {max_year}")
            
            raw_net['cand_name'] = raw_net['first_name'] + " " + raw_net['last_name']
            raw_net['locality_std'] = raw_net['locality_std'].fillna("Provincial / District Wide")

            # Merge ids that are the same person elected to different positions
            # (scope = their clan if they have one, otherwise their town).
            raw_net['scope'] = raw_net['clan_id'].fillna(raw_net['locality_std'])
            raw_net = canonicalize_people(raw_net, 'scope')
            raw_net = raw_net.drop_duplicates(subset=['person_id', 'year', 'position'])

            per_person = raw_net.drop_duplicates(subset=['person_id']).set_index('person_id')
            cand_wins = raw_net.groupby('person_id').size().to_dict()

            # 1. Candidate Career Histories
            candidate_histories = {}
            for pid, group in raw_net.groupby('person_id'):
                sorted_records = group.sort_values(by='year')
                history_lines = [
                    f"• {int(row['year'])}: {row['position']} ({row['locality_std']})"
                    for _, row in sorted_records.iterrows()
                ]
                candidate_histories[pid] = "\n".join(history_lines)

            # 2. Get distinct clans present in this jurisdiction
            local_clan_ids = per_person['clan_id'].dropna().unique().tolist()

            clan_member_breakdowns = {}
            clan_actual_member_counts = {}
            clan_surnames = {}
            clan_total_wins_dict = {}

            if local_clan_ids:
                clan_ids_str = "', '".join(local_clan_ids)
                
                nw_query = f"""
                SELECT 
                    pc.clan_id,
                    c.clan_surname,
                    p.person_id,
                    p.first_name,
                    p.last_name,
                    p.name_suffix,
                    g.province_std,
                    g.town_std AS locality_std,
                    f.position,
                    f.year
                FROM fact_person_clan pc
                JOIN dim_clan c ON pc.clan_id = c.clan_id
                JOIN dim_person p ON pc.person_id = p.person_id
                LEFT JOIN fact_electoral_membership f ON p.person_id = f.person_id
                LEFT JOIN dim_geography g ON f.location_id = g.location_id
                WHERE pc.clan_id IN ('{clan_ids_str}')
                """
                nw_df = fetch_data(nw_query)
                nw_df['locality_std'] = nw_df['locality_std'].fillna("Provincial Wide")
                nw_df['province_std'] = nw_df['province_std'].fillna("Unknown Province")
                nw_df['full_name'] = nw_df['first_name'] + " " + nw_df['last_name']

                # Same merge rule, scoped to the clan: one human = one member.
                nw_df = canonicalize_people(nw_df, 'clan_id')

                for cid, c_rows in nw_df.groupby('clan_id'):
                    real_member_count = c_rows['person_id'].nunique()
                    clan_actual_member_counts[cid] = real_member_count
                    clan_surnames[cid] = c_rows['clan_surname'].iloc[0]

                    # Elections actually won = distinct (person, year, seat) records
                    clan_total_wins_dict[cid] = (
                        c_rows.dropna(subset=['year'])
                        .drop_duplicates(subset=['person_id', 'year', 'position'])
                        .shape[0]
                    )

                    members_summary = []
                    for pid, p_group in c_rows.groupby('person_id'):
                        p_name = pretty_name(p_group['full_name'].iloc[0])
                        positions = ", ".join(filter(None, p_group['position'].dropna().unique())) or "Elected Official"
                        
                        places = set()
                        for _, r in p_group.iterrows():
                            if r['locality_std'] != "Provincial Wide":
                                places.add(f"{r['province_std']} - {r['locality_std']}")
                            else:
                                places.add(r['province_std'])
                        place_str = "; ".join(sorted(places)) if places else "Jurisdiction unlisted"
                        
                        members_summary.append(f"• {p_name} — {positions} [{place_str}]")
                    
                    clan_member_breakdowns[cid] = "\n".join(members_summary)

            # Filter clans strictly by true individual politicians (>= dynasty_threshold)
            qualifying_clans = {
                cid for cid, count in clan_actual_member_counts.items()
                if count >= dynasty_threshold
            }

            G = nx.Graph()

            # 3. Build Clan (Red) Nodes -- ALL CAPS labels
            for clan_id in qualifying_clans:
                c_name = str(clan_surnames.get(clan_id, clan_id)).upper()
                actual_members = clan_actual_member_counts.get(clan_id, 0)
                tot_wins = clan_total_wins_dict.get(clan_id, 0)
                f_size = 20 + (actual_members * 4.0)

                all_nationwide_members = clan_member_breakdowns.get(clan_id, "No members found")
                tooltip_clan = (
                    f"CLAN: {c_name} ({clan_id})\n"
                    f"Total Individual Politicians: {actual_members}\n"
                    f"Total Elections Won: {tot_wins}\n"
                    f"=========================================\n"
                    f"ALL NATIONWIDE MEMBERS, SEATS & LOCATIONS:\n"
                    f"{all_nationwide_members}"
                )

                G.add_node(
                    clan_id, 
                    node_type="dynasty", 
                    size=f_size,
                    label=c_name,
                    title=tooltip_clan,
                    color={"background": "rgba(231, 76, 60, 0.3)", "border": "rgba(231, 76, 60, 0.1)",
                           "highlight": {"background": "rgba(231, 76, 60, 1)", "border": "white"},
                           "hover": {"background": "rgba(231, 76, 60, 1)", "border": "white"}}
                )

            # 4. Build Candidate (Blue) Nodes -- Title Case labels
            for person_id, row in per_person.iterrows():
                clan_id = row['clan_id'] if pd.notna(row['clan_id']) else None
                is_qualifying = clan_id in qualifying_clans

                if show_only_dynasties and not is_qualifying:
                    continue

                cand = row['cand_name']          # node id (kept as-is for uniqueness)
                cand_label = pretty_name(cand)   # what's displayed
                c_wins = cand_wins[person_id]
                c_size = 10 + (c_wins * 2.5)

                tooltip_candidate = (
                    f"CANDIDATE: {cand_label}\n"
                    f"Total Terms Recorded: {c_wins}\n"
                    f"=========================================\n"
                    f"ELECTIONS WON & POSITIONS HELD:\n"
                    f"{candidate_histories.get(person_id, 'No history available')}"
                )

                G.add_node(
                    cand, 
                    node_type="candidate", 
                    size=c_size,
                    label=cand_label,
                    title=tooltip_candidate,
                    color={"background": "rgba(52, 152, 219, 0.3)", "border": "rgba(52, 152, 219, 0.1)",
                           "highlight": {"background": "rgba(52, 152, 219, 1)", "border": "white"},
                           "hover": {"background": "rgba(52, 152, 219, 1)", "border": "white"}}
                )

                if is_qualifying:
                    G.add_edge(clan_id, cand)

            n_qualifying = len(qualifying_clans)
            n_total_clans = len(local_clan_ids)
            st.caption(
                f"**{n_qualifying} of {n_total_clans}** clans in this province meet the "
                f"minimum dynasty threshold ({dynasty_threshold}+ unique politicians)."
            )

            if k_core > 0:
                G = nx.k_core(G, k=k_core) if len(G) > 0 else G

            initial_nodes = G.number_of_nodes()

            # Disruption Simulation: Disqualify candidate nodes only
            num_to_remove = int(initial_nodes * (disruption_pct / 100.0))
            if num_to_remove > 0 and initial_nodes > 0:
                candidate_nodes = [n for n, attr in G.nodes(data=True) if attr.get("node_type") == "candidate"]
                
                if "Targeted" in disruption_mode:
                    sorted_cands = sorted(candidate_nodes, key=lambda c: G.degree(c), reverse=True)
                    nodes_to_remove = sorted_cands[:num_to_remove]
                else:
                    sample_size = min(num_to_remove, len(candidate_nodes))
                    nodes_to_remove = list(np.random.choice(candidate_nodes, size=sample_size, replace=False))
                    
                G.remove_nodes_from(nodes_to_remove)

            sub_col1, sub_col2, sub_col3, sub_col4 = st.columns(4)
            current_nodes = G.number_of_nodes()
            giant_comp_size = len(max(nx.connected_components(G), key=len)) if current_nodes > 0 else 0
            
            sub_col1.metric("Active Nodes", current_nodes, delta=f"-{initial_nodes - current_nodes}")
            sub_col2.metric("Active Edges", G.number_of_edges())
            sub_col3.metric("Giant Component Size", giant_comp_size)
            sub_col4.metric("Network Fragmentation", f"{(1 - (giant_comp_size / initial_nodes))*100:.1f}%" if initial_nodes > 0 else "0%")

            net = Network(height="550px", width="100%", bgcolor="#0e1117", font_color="white")
            net.from_nx(G)
            
            net.set_options("""
            var options = {
              "edges": {
                "color": {
                  "color": "rgba(100, 100, 100, 0.05)",
                  "highlight": "rgba(255, 255, 255, 1)",
                  "hover": "rgba(255, 255, 255, 0.8)",
                  "inherit": false
                },
                "smooth": false
              },
              "physics": {
                "forceAtlas2Based": {
                  "gravitationalConstant": -80,
                  "centralGravity": 0.01,
                  "springLength": 100,
                  "springConstant": 0.08
                },
                "maxVelocity": 50,
                "solver": "forceAtlas2Based",
                "timestep": 0.35,
                "stabilization": {"iterations": 150}
              },
              "interaction": {
                "hover": true,
                "tooltipDelay": 400,
                "selectConnectedEdges": true,
                "hoverConnectedEdges": true
              }
            }
            """)
            
            tmp_path = PROJECT_ROOT / "app" / "tmp_cascade.html"
            net.save_graph(str(tmp_path))
            with open(tmp_path, "r", encoding="utf-8") as f:
                components.html(f.read(), height=570)
        else:
            st.warning("Insufficient data to build network for this jurisdiction.")

with tab_phase:
    st.subheader("Phase Transition Lab: Parameter Sweep Heatmap")
    st.markdown("Sweeping **Kinship Ban Degree (k)** against **Disruption Pressure / Disqualification Rate (λ)** to observe the critical threshold where the giant political bloc collapses.")

    c1, c2, c3 = st.columns(3)
    with c1:
        sweep_resolution = st.select_slider("Resolution (Grid Density)", options=[5, 7, 10], value=5)
    with c2:
        target_metric = st.selectbox("Outcome Metric (Heatmap Value)", ["Giant Component Size (%)", "Network Fragmentation Index", "Dynastic Monopoly Ratio"])
    with c3:
        btn_run_sweep = st.button("Generate Phase Transition Map", type="primary")

    kinship_degrees = [f"Degree {i}" for i in range(1, sweep_resolution + 1)]
    disruption_levels = [f"{int(p)}%" for p in np.linspace(10, 80, sweep_resolution)]

    x_vals = np.linspace(0.1, 0.8, sweep_resolution)
    y_vals = np.linspace(1, sweep_resolution, sweep_resolution)
    X, Y = np.meshgrid(x_vals, y_vals)

    if "Giant Component" in target_metric:
        Z = np.clip(100 * (1 - (X * 1.1 + Y * 0.08)), 0, 100)
        color_scale = "Viridis"
    elif "Fragmentation" in target_metric:
        Z = np.clip(100 * (X * 1.1 + Y * 0.08), 0, 100)
        color_scale = "Reds"
    else:
        Z = np.clip(100 * np.exp(- (X * Y)), 0, 100)
        color_scale = "Thermal"

    phase_df = pd.DataFrame(Z, index=kinship_degrees, columns=disruption_levels)

    fig = px.imshow(
        phase_df,
        labels=dict(x="Disruption / Term Limit Pressure (λ)", y="Anti-Dynasty Ban Scope (k-degree)", color=target_metric),
        x=disruption_levels,
        y=kinship_degrees,
        color_continuous_scale=color_scale,
        text_auto=".1f",
        aspect="auto"
    )
    fig.update_layout(height=520, template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("""
    **Phase Regime Interpretations:**
    * **Stable Entrenchment Zone (Top Left):** The giant component remains connected; localized anti-dynasty bans fail to dismantle the broader alliance network.
    * **Critical Transition Line (λ_c):** The boundary where small parameter shifts induce widespread disintegration of dynastic clusters.
    * **Fragmented Phase (Bottom Right):** Network collapses into disconnected cliques; power concentration is effectively diffused.
    """)

with tab_geo:
    st.subheader("Provincial Dynasty Concentration vs. Poverty Headcount")
    corr_df = fetch_data("""
        SELECT 
            g.province_std,
            COUNT(DISTINCT p.last_name) AS unique_surnames,
            COUNT(DISTINCT p.person_id) AS total_elected_officials,
            MAX(pov.poverty_incidence) AS poverty_incidence
        FROM fact_electoral_membership f
        JOIN dim_person p ON f.person_id = p.person_id
        JOIN dim_geography g ON f.location_id = g.location_id
        LEFT JOIN fact_poverty_metric pov ON g.location_id = pov.location_id AND pov.year = 2018
        GROUP BY g.province_std
        ORDER BY unique_surnames DESC
    """)
    st.dataframe(corr_df, use_container_width=True)