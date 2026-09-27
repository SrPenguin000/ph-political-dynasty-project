# Philippine Political Dynasty Analytics & Network Resilience Pipeline

An end-to-end, containerized Data Engineering pipeline that ingests, cleans, models, and analyzes multi-decade Philippine election records and public official datasets. 

The system maps familial ties—including multi-hop kinship such as siblings, 1st cousins, and maternal links—to calculate empirical town-level dynasty stronghold metrics and run network percolation/cascade simulations to test dynasty resilience under systemic political disruptions.

### Tech Stack
* **Orchestration:** Apache Airflow
* **Database & Modeling:** PostgreSQL (Star Schema + Kinship Graph Edges)
* **Storage Layers:** Medallion Architecture (Raw \(\rightarrow\) Staging \(\rightarrow\) Curated Parquet)
* **Graph & Simulation Engine:** NetworkX
* **Deployment:** Docker & Docker Compose
* **Exploratory UI:** Streamlit + PyVis