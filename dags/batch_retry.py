from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
import pytz
import requests
import pandas as pd
import os
from datetime import timedelta, datetime

# Define the directory where the CSV will be saved
OUTPUT_DIR = "/opt/airflow/output"  # Replace with your desired output path
MAX_RECORDS_PER_REQUEST = 10000

# API endpoint and headers
API_URL = 'http://34.124.138.144:8000/api/common/authentication'
HEADERS = {
    'Authorization': '',
    'Content-Type': 'application/json'
}

# Default arguments for the DAG with retries
default_args = {
    'owner': 'airflow',
    'start_date': datetime(2024, 9, 24, 1, 0),  # DAG starts one day ago
    'retries': 100,  # Retry up to 3 times if the request fails
    'retry_delay': timedelta(minutes=1),  # Wait 5 minutes between retries
}

# Define the DAG with a daily schedule at 1 AM
with DAG(
    'batch_retry',
    default_args=default_args,
    description='DAG to fetch paginated data from API and save incrementally to CSV',
    schedule_interval="0 1 * * *",  # Run daily at 1 AM
    catchup=False,  # Do not backfill
) as dag:

    # Function to fetch data from the API with pagination and save incrementally
    def fetch_data_and_save(**kwargs):
        search_after = None
        request_count = 0
        total_records = 0

        bangkok_tz = pytz.timezone('Asia/Bangkok')
        current_time = datetime.now(bangkok_tz)

        # # Default endDate is 1 AM of the execution date (same day as DAG run)
        end_date = current_time.replace(hour=1, minute=0, second=0, microsecond=0)

        # Default startDate is 1 AM of the day before execution_date
        start_date = end_date - timedelta(days=1)

        # Get startDate and endDate from DAG params (or use the calculated defaults)
        start_date_str = kwargs['dag_run'].conf.get('startDate', start_date.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3])
        end_date_str = kwargs['dag_run'].conf.get('endDate', end_date.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3])


        print(f"Start Date: {start_date_str}, End Date: {end_date_str}")

        # Prepare the base request body with dynamic startDate and endDate
        BASE_REQUEST_BODY = {
            "startDate": start_date_str,
            "endDate": end_date_str
        }

        # Make the initial request to fetch the total number of records
        initial_request_body = BASE_REQUEST_BODY.copy()
        response = requests.post(API_URL, headers=HEADERS, json=initial_request_body)
        response.raise_for_status()

        # Get the total number of records
        data = response.json()
        total_records = data.get('hits', {}).get('total', {}).get('value', 0)
        print(f"Total records to fetch: {total_records}")

        # Calculate the number of requests needed
        total_requests = (total_records + MAX_RECORDS_PER_REQUEST - 1) // MAX_RECORDS_PER_REQUEST
        print(f"Total requests required: {total_requests}")

        # Paginate through the results
        while request_count < total_requests:
            # Prepare request body for pagination
            request_body = BASE_REQUEST_BODY.copy()
            if search_after:
                request_body['search_after'] = search_after

            # Make the API request
            response = requests.post(API_URL, headers=HEADERS, json=request_body)
            response.raise_for_status()

            # Get the response data
            data = response.json()

            # Extract records (hits)
            hits = data.get('hits', {}).get('hits', [])
            
            # Prepare data for CSV
            rows = []
            for hit in hits:
                row = {
                    'MemberType': hit.get('MemberType', ''),
                    'Latitude': hit.get('Latitude', ''),
                    'Longitude': hit.get('Longitude', ''),
                    'Status': hit.get('Status', ''),
                    'DeviceOS': hit.get('DeviceOS', ''),
                    'ModelName': hit.get('ModelName', ''),
                    'UserToken': hit.get('UserToken', ''),
                    'RequestDateTime': hit.get('RequestDateTime', ''),
                    '_id': hit.get('_id', '')
                }
                rows.append(row)

            # Convert the list of dictionaries into a Pandas DataFrame
            df = pd.DataFrame(rows)

            # Ensure the output directory exists
            os.makedirs(OUTPUT_DIR, exist_ok=True)

            # Define the CSV file path
            csv_file_path = os.path.join(OUTPUT_DIR, "api_response_paginated.csv")

            # Save DataFrame to CSV, append mode if file exists
            df.to_csv(csv_file_path, index=False, mode='a', header=not os.path.exists(csv_file_path))
            print(f"Batch {request_count+1} saved to {csv_file_path}")

            # Prepare the `search_after` field for the next request if more data exists
            if len(hits) == MAX_RECORDS_PER_REQUEST:
                last_hit = hits[-1]
                search_after = [last_hit['RequestDateTime'], last_hit['_id']]
                request_count += 1
            else:
                break

    # Function to simulate moving a file
    def csv_file(**kwargs):
        # Dummy task to simulate moving a file
        print("Simulating file move...")
        pass  # Do nothing for now

    # Function to simulate sending a notification
    def send_notification(**kwargs):
        # Dummy task to simulate sending a notification
        print("Simulating sending a notification...")
        pass  # Do nothing for now

    # Define the task to fetch data and save to CSV
    fetch_paginated_api_data = PythonOperator(
        task_id='fetch_paginated_api_data',
        python_callable=fetch_data_and_save,
        provide_context=True,  # To access params from the DAG run
        dag=dag,
    )

    # Task 1: Move the file (dummy task)
    csv_file_task = PythonOperator(
        task_id='csv_file',
        python_callable=csv_file,
        provide_context=True,
        dag=dag,
    )

    # Task 2: Send notification (dummy task)
    send_notification_task = PythonOperator(
        task_id='send_notification',
        python_callable=send_notification,
        provide_context=True,
        dag=dag,
    )

    # Define task dependencies
    fetch_paginated_api_data >> csv_file_task >> send_notification_task