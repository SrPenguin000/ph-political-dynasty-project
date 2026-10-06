"""Apache Airflow DAG for the Philippine Political Dynasty ETL Pipeline."""

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
    description='Orchestrates staging data quality checks and PostgreSQL data warehouse loading',
    schedule_interval='@monthly',
    start_date=datetime(2026, 10, 1),
    catchup=False,
    tags=['ph_dynasty', 'postgres', 'etl'],
) as dag:

    # Navigate to the mounted project root inside the Airflow container before executing
    run_dq_checks = BashOperator(
        task_id='run_data_quality_checks',
        bash_command='cd /opt/airflow && python src/validation/quality_checks.py',
    )

    load_data_warehouse = BashOperator(
        task_id='load_data_warehouse',
        bash_command='cd /opt/airflow && python src/load/postgres_loader.py',
    )

    # Define the execution order
    run_dq_checks >> load_data_warehouse