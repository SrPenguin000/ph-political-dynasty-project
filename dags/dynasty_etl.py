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

    # 1. Run the core transformation script to produce *_clean.parquet staging files
    run_clean_backfill = BashOperator(
        task_id='run_clean_backfill',
        bash_command='cd /opt/airflow && python src/transform/clean_backfill.py',
    )

    # 2. Define the notebooks that generate curated data
    notebooks = [
        "03_kinship_engine.ipynb",
        "04_dynasty_stronghold.ipynb",
        "05_network_resilience.ipynb"
    ]

    notebook_tasks = []

    # 3. Dynamically generate a Bash task for each notebook
    for nb in notebooks:
        task_id = f"run_{nb.replace('.ipynb', '')}"
        
        # Combine the installation and execution into a single, bulletproof bash command
        run_nb = BashOperator(
            task_id=task_id,
            bash_command=f"python -m pip install nbconvert ipykernel networkx scipy && cd /opt/airflow/notebooks && python -m nbconvert --execute --inplace {nb}",
        )
        notebook_tasks.append(run_nb)

    # 4. Define the downstream pipeline tasks
    run_dq_checks = BashOperator(
        task_id='run_data_quality_checks',
        bash_command='cd /opt/airflow && python src/validation/quality_checks.py',
    )

    load_data_warehouse = BashOperator(
        task_id='load_data_warehouse',
        bash_command='cd /opt/airflow && python src/load/postgres_loader.py',
    )

    # 5. Chain the pipeline in strict sequential order
    run_clean_backfill >> notebook_tasks[0]
    
    for i in range(len(notebook_tasks) - 1):
        notebook_tasks[i] >> notebook_tasks[i + 1]

    # 6. Connect the final notebook to the DQ checks and Data Warehouse load
    notebook_tasks[-1] >> run_dq_checks >> load_data_warehouse