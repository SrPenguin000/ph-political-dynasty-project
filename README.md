# Philippine Political Dynasty Analytics & Network Resilience Pipeline

An end-to-end, containerized Data Engineering pipeline that ingests, cleans, models, and analyzes multi-decade Philippine election records and public official datasets. 

The system maps familial ties (including multi-hop kinship such as siblings, 1st cousins, and maternal links) to calculate empirical town-level dynasty stronghold metrics and run network percolation/cascade simulations to test dynasty resilience under systemic political disruptions.

### Tech Stack
* **Orchestration:** Apache Airflow
* **Database & Modeling:** PostgreSQL (Star Schema + Kinship Graph Edges)
* **Storage Layers:** Medallion Architecture (Raw > Staging > Curated Parquet)
* **Graph & Simulation Engine:** NetworkX
* **Deployment:** Docker & Docker Compose
* **Exploratory UI:** Streamlit + PyVis

## Data Sources & Provenance Justification

| Env Variable | Source Name | Format / Type | Role in Pipeline & Methodological Justification |
| :--- | :--- | :--- | :--- |
| `PRIMARY_HF_DATASET` | **BetterGov.PH Raw Philippine Data** (`persons` & `memberships`)[cite: 1] | Parquet (Hugging Face API)[cite: 1] | **Main Data Source:** Contains pre-linked `person_id` records across election cycles (2004–2016)[cite: 1], solving longitudinal entity resolution across terms. |
| `SECONDARY_SOURCE_URL` | **OpenHalalan Dataset (2001–2025)** | CSV | **Longitudinal Extension & Prior Art:** Extends local/national winners across 25 years and provides pre-computed per-town dynastic share metrics to benchmark our graph calculations. |
| `TERTIARY_SOURCE_URL` | **PSA OpenSTAT Poverty Incidence** (`0011E3DF010.px`) | JSON (PXWeb REST API) | **Socioeconomic Covariate:** Enables exploratory correlation between provincial dynasty stronghold rates and poverty incidence beyond pure network topology. |
| `HISTORICAL_ROSTER_URL` | **House of Representatives Roster of Legislators (1907–2019)** | PDF (Direct S3 Bucket) | **50+ Year Historical Depth:** Reaches prior to Martial Law, enabling tracking of national legislative dynasties across regime changes. |
| `WIKIDATA_SPARQL_URL` | **Wikidata Query Service** | JSON (SPARQL API) | **Explicit Kinship Enrichment:** Provides structured spouse, parent, sibling, and relative edges (`P22`, `P25`, `P26`, `P3373`, `P1038`) to verify multi-hop relationships beyond surname heuristics. |
| `FAMILY_NETWORK_VALIDATION_URL` | **openICPSR 113048 (Village Family Networks)** | Reference / Validation | **External Methodological Validation:** Peer-reviewed AER family-network dataset used to validate that surname/middle-name graph construction aligns with empirical Philippine kinship structures. |
| `BENCHMARK_VALIDATION_URL` | **PCIJ Political Dynasties Report** | Benchmark Metrics | **Sanity-Check Validation:** Provides published macro benchmarks (e.g., 113 of 149 cities and 71 of 82 provinces classified as dynastic) for automated pipeline data quality checks. |