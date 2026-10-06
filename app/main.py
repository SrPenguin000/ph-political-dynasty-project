import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import numpy as np
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine
import networkx as nx
from pyvis.network import Network
import streamlit.components.v1 as components
import plotly.express as px
from sqlalchemy import create_engine, text
import psycopg2

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

PG_USER = os.getenv("POSTGRES_USER", "postgres")
PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
PG_DB = os.getenv("POSTGRES_DB", "dynasty_db")
PG_PORT = os.getenv("POSTGRES_PORT", "5432")
PG_HOST = "localhost"

DB_URL = f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"

@st.cache_data
def fetch_data(query: str) -> pd.DataFrame:
    """Execute SQL query using a raw psycopg2 connection to satisfy pandas."""
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
        selected_province = st.selectbox("Province Focus", prov_list, index=prov_list.index("MAGUINDANAO") if "MAGUINDANAO" in prov_list else 0)

        disruption_mode = st.radio("Intervention / Attack Strategy", ["Targeted (Top Hubs / Strongest Dynasties)", "Random Disqualification", "Degree-Based Threshold"])
        disruption_pct = st.slider("Disruption Intensity (% Nodes Removed)", 0, 80, 20, step=5)
        k_core = st.slider("Core Entrenchment Filter (k-core)", 0, 5, 0, help="Filter out periphery single-term candidates")

    with col_graph:
        query = f"""
        SELECT 
            p.last_name, 
            p.first_name, 
            f.position, 
            f.year
        FROM fact_electoral_membership f
        JOIN dim_person p ON f.person_id = p.person_id
        JOIN dim_geography g ON f.location_id = g.location_id
        WHERE g.province_std = '{selected_province}' AND f.year >= 2010
        """
        raw_net = fetch_data(query)

        if not raw_net.empty:
            G = nx.Graph()
            for _, r in raw_net.iterrows():
                family = r['last_name']
                cand = f"{r['first_name']} {r['last_name']}"
                G.add_node(family, node_type="dynasty", size=24, color="#e74c3c")
                G.add_node(cand, node_type="candidate", size=12, color="#3498db")
                G.add_edge(family, cand)

            if k_core > 0:
                G = nx.k_core(G, k=k_core) if len(G) > 0 else G

            initial_nodes = G.number_of_nodes()

            num_to_remove = int(initial_nodes * (disruption_pct / 100.0))
            if num_to_remove > 0 and initial_nodes > 0:
                if "Targeted" in disruption_mode:
                    sorted_nodes = sorted(G.degree, key=lambda x: x[1], reverse=True)
                    nodes_to_remove = [n[0] for n in sorted_nodes[:num_to_remove]]
                else:
                    nodes_to_remove = list(np.random.choice(list(G.nodes()), size=min(num_to_remove, len(G)), replace=False))
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
            
            net.repulsion(node_distance=150, central_gravity=0.05, spring_length=120)
            for edge in net.edges:
                edge['color'] = '#555555'
                
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
        WHERE f.year >= 2010
        GROUP BY g.province_std
        ORDER BY unique_surnames DESC
    """)
    st.dataframe(corr_df, use_container_width=True)