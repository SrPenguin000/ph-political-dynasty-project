from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator

default_args = {
    'owner': 'dynasty_admin',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=2),
}

with DAG(
    'ph_dynasty_end_to_end_etl',
    default_args=default_args,
    description='Orchestrates transformations, network generation, DQ checks, and PG loading',
    schedule_interval='@monthly',
    start_date=datetime(2026, 10, 1),
    catchup=False,
    tags=['ph_dynasty', 'postgres', 'etl'],
) as dag:

    # 1. Ingest raw data from APIs, Hugging Face, and local files
    run_ingest_raw = BashOperator(
        task_id='run_ingest_raw',
        bash_command='cd /opt/airflow && python src/ingest/ingest_raw.py',
    )

    # 2. Extract and Parse PDF documents into structured CSV staging files
    parse_psa = BashOperator(
        task_id='parse_psa_poverty',
        bash_command='cd /opt/airflow && python src/transform/parse_psa_poverty.py',
    )

    parse_roster = BashOperator(
        task_id='parse_roster',
        bash_command='cd /opt/airflow && python src/transform/parse_roster.py',
    )

    # 3. Run the core transformation script to produce *_clean.parquet staging files
    run_clean_backfill = BashOperator(
        task_id='run_clean_backfill',
        bash_command='cd /opt/airflow && python src/transform/clean_backfill.py',
    )

    # 4. Execute the curated data Python scripts (now in src/curate/)
    run_kinship_engine = BashOperator(
        task_id='run_kinship_engine',
        bash_command='cd /opt/airflow && python src/curate/03_kinship_engine.py',
    )

    run_dynasty_stronghold = BashOperator(
        task_id='run_dynasty_stronghold',
        bash_command='cd /opt/airflow && python src/curate/04_dynasty_stronghold.py',
    )

    run_network_resilience = BashOperator(
        task_id='run_network_resilience',
        bash_command='cd /opt/airflow && python src/curate/05_network_resilience.py',
    )

    # 5. Define the downstream pipeline tasks
    run_dq_checks = BashOperator(
        task_id='run_data_quality_checks',
        bash_command='cd /opt/airflow && python src/validation/quality_checks.py',
    )

    load_data_warehouse = BashOperator(
        task_id='load_data_warehouse',
        bash_command='cd /opt/airflow && python src/load/postgres_loader.py',
    )

    # 6. Chain the pipeline in strict sequential order
    run_ingest_raw >> [parse_psa, parse_roster] >> run_clean_backfill
    run_clean_backfill >> run_kinship_engine >> run_dynasty_stronghold >> run_network_resilience
    run_network_resilience >> run_dq_checks >> load_data_warehouse