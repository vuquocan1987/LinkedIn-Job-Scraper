#!/bin/bash

# Define execution times (in seconds)
SEARCH_RETRIEVER_DURATION=120  # 1 minute
DETAILS_RETRIEVER_DURATION=600  # 5 minutes

# Define CSV output parameters
DESTINATION_FOLDER="results/"
DATABASE_FILE="linkedin_jobs.db"

# Function to run a script for a specific duration
run_script() {
    local script_name=$1
    local duration=$2
    echo "Starting: $script_name"
    python "$script_name" &
    script_pid=$!
    sleep "$duration"
    kill $script_pid
    echo "Stopped: $script_name"
}

# Step 1: Run search_retriever.py for 1 minute
run_script "search_retriever.py" $SEARCH_RETRIEVER_DURATION

# Step 2: Run details_retriever.py for 5 minutes
run_script "details_retriever.py" $DETAILS_RETRIEVER_DURATION

# Step 3: Convert database to CSV
echo "Converting database to CSV..."
python to_csv.py --folder "$DESTINATION_FOLDER" --database "$DATABASE_FILE"

echo "Job scraping completed!"