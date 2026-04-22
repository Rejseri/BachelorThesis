# Stamdata ESG API Test Documentation

This document explains the functionality and workflow of the `APITest.py` script, which is designed to test and interact with the **Stamdata ESG API**.

## Overview

The `APITest.py` script implements a production-ready client for fetching ESG PCAF (Partnership for Carbon Accounting Financials) estimates for specific ISINs (International Securities Identification Numbers). 

The Stamdata API operates **asynchronously** for large data requests. This means a single request does not immediately return the final data, but rather initiates a background process.

## Prerequisites

1.  **API Key**: You must have a valid API key from Stamdata.
2.  **APIKey.txt**: The script expects a file named `APIKey.txt` in the same directory containing only your API key string.
3.  **Virtual Environment**: It is highly recommended to use the provided virtual environment.

### Environment Setup
The environment has been initialized with the necessary dependencies:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install requests pandas openpyxl
```

## Execution Workflow

The script follows a three-step lifecycle to retrieve data:

### 1. Request Submission (`POST /api/v1/feed/esg-pcaf-estimates`)
*   The script sends a JSON payload containing the targeted `ISINs` and `years`.
*   **Status Code 202 (Accepted)**: The API confirms the request is queued and returns a unique `Request ID`.

### 2. Status Polling (`GET /api/v1/feed/{request_id}`)
*   Because the data generation can take time, the script polls the status endpoint every 5 seconds.
*   **Possible Statuses**:
    *   `Queued`: Request is waiting to be processed.
    *   `Processing`: Stamdata is generating the dataset.
    *   `Processed`: The dataset is ready for download.
*   Once the status is `Processed`, the API returns one or more `FeedURLs`.

### 3. Data Retrieval (`GET {FeedURL}`)
*   The script fetches the final JSON dataset from the first available `FeedURL`.
*   The final response includes metadata (data methodology, units) and the actual ESG metrics for each ISIN.

## High-Level Functionality

The `StamdataAPIClient` now includes convenience methods:
*   `get_company_data(isin, years)`: This method orchestrates the entire asynchronous workflow in a single call. It returns a flat list of all data records found for the specified company and time period.
*   `save_to_excel(data, filename)`: Saves the retrieved list of dictionaries into an Excel `.xlsx` file. (Requires `openpyxl`).
*   `save_to_csv(data, filename)`: Saves the retrieved list of dictionaries into a CSV file.

## How to Run the Test

Activate the virtual environment and run the script:

```bash
source .venv/bin/activate
python3 APITest.py
```

### Successful Output Example
```text
[1/3] Submitting request to https://api.stamdata.com/api/v1/feed/esg-pcaf-estimates...
Successfully queued request. ID: 21b23eb3-9f0c-4157-1bf5-08de95a7652b
[2/3] Waiting for processing (ID: 21b23eb3-9f0c-4157-1bf5-08de95a7652b)...
    Attempt 1: Status is 'Processed'...
Processing complete. 1 file(s) available.
[3/3] Downloading final dataset...

==================================================
API TEST SUCCESSFUL
==================================================
...
```

## Error Handling
The script includes robust error handling:
*   **Key Validation**: Ensures the API key file exists and is not empty.
*   **HTTP Failures**: Uses `response.raise_for_status()` to catch 401 (Unauthorized), 403 (Forbidden), and 404 (Not Found) errors.
*   **Timeout**: If polling takes too long (default 60 seconds), the script will timeout gracefully to prevent infinite loops.
