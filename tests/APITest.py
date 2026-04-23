
import requests
import os
import json
import time
import pandas as pd
from typing import Dict, Any, List, Optional, Union

class StamdataAPIClient:
    """
    A client for interacting with the Stamdata ESG API.
    Handles authentication, asynchronous request submission, polling, and data retrieval.
    """

    def __init__(self, api_key_path: str = "APIKey.txt", base_url: str = "https://api.stamdata.com"):
        self.base_url = base_url
        self.api_key = self._load_api_key(api_key_path)
        self.headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def _load_api_key(self, path: str) -> str:
        """Loads the API key from a local file."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"API key file not found at: {path}")
        
        with open(path, "r") as f:
            key = f.read().strip()
            
        if not key:
            raise ValueError("API key file is empty.")
        return key

    def request_esg_pcaf_estimates(self, isins: List[str], years: List[str]) -> str:
        """
        Submits a request for ESG PCAF estimates.
        Returns the Request ID (UUID).
        """
        url = f"{self.base_url}/api/v1/feed/esg-pcaf-estimates"
        payload = {
            "ISINs": isins,
            "years": years
        }

        print(f"[1/3] Submitting request to {url}...")
        response = requests.post(url, headers=self.headers, json=payload)
        
        if response.status_code == 202:
            request_id = response.json().get("ID")
            if not request_id:
                raise ValueError("API returned 202 but no Request ID was found.")
            return request_id
        
        response.raise_for_status()
        return "" # Should not reach here if raise_for_status is used

    def poll_for_completion(self, request_id: str, interval: int = 5, max_attempts: int = 12) -> List[str]:
        """
        Polls the API until the request status is 'Processed'.
        Returns a list of download URLs.
        """
        status_url = f"{self.base_url}/api/v1/feed/{request_id}"
        print(f"[2/3] Waiting for processing (ID: {request_id})...")

        for attempt in range(1, max_attempts + 1):
            time.sleep(interval)
            response = requests.get(status_url, headers=self.headers)
            
            if response.status_code == 200:
                data = response.json()
                status = data.get("Status")
                
                if status == "Processed":
                    urls = data.get("FeedURLs", [])
                    if not urls:
                        raise ValueError("Request processed but no download URLs provided.")
                    return urls
                
                print(f"    Attempt {attempt}: Status is '{status}'...")
            elif response.status_code == 202:
                print(f"    Attempt {attempt}: Still queued/processing...")
            else:
                response.raise_for_status()

        raise TimeoutError(f"Request {request_id} did not complete within the timeout period.")

    def download_data(self, download_url: str) -> Dict[str, Any]:
        """Downloads the final JSON data from the provided URL."""
        print(f"[3/3] Downloading final dataset...")
        response = requests.get(download_url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def get_company_data(self, isin: str, years: List[str]) -> List[Dict[str, Any]]:
        """
        Convenience method to retrieve all ESG data for a specific company (ISIN) and years.
        Handles the entire lifecycle: Request -> Poll -> Download -> Parse.
        """
        try:
            # Step 1: Request Data
            request_id = self.request_esg_pcaf_estimates([isin], years)
            
            # Step 2: Poll for completion
            download_urls = self.poll_for_completion(request_id)
            
            # Step 3: Retrieve and aggregate results
            all_records = []
            for url in download_urls:
                dataset = self.download_data(url)
                records = dataset.get("Data", [])
                all_records.extend(records)
                
            return all_records
            
        except Exception as e:
            print(f"[ERROR] Failed to fetch data for ISIN {isin}: {e}")
            raise

    def save_to_excel(self, data: List[Dict[str, Any]], filename: str):
        """Saves the data list to an Excel file using pandas."""
        if not data:
            print("[WARN] No data to save.")
            return

        df = pd.DataFrame(data)
        try:
            df.to_excel(filename, index=False)
            print(f"Data successfully saved to Excel: {filename}")
        except ModuleNotFoundError:
            print("[ERROR] 'openpyxl' is not installed. Please install it to export to Excel.")
            print("Fallback: Saving to CSV instead.")
            self.save_to_excel(data, filename.replace(".xlsx", ".csv"))
        except Exception as e:
            print(f"[ERROR] Failed to save to Excel: {e}")

    def save_to_csv(self, data: List[Dict[str, Any]], filename: str):
        """Saves the data list to a CSV file using pandas."""
        if not data:
            print("[WARN] No data to save.")
            return

        df = pd.DataFrame(data)
        try:
            df.to_csv(filename, index=False)
            print(f"Data successfully saved to CSV: {filename}")
        except Exception as e:
            print(f"[ERROR] Failed to save to CSV: {e}")

def main():
    """Main execution flow for testing the Stamdata ESG API."""
    try:
        # Configuration
        ISIN = "NO0010881246" # Avinor AS
        YEARS = ["2023", "2022", "2021"]
        
        # Initialize Client
        client = StamdataAPIClient()

        # Fetch all data for the company in one call
        print(f"--- Fetching all data for {ISIN} ({', '.join(YEARS)}) ---")
        all_data = client.get_company_data(ISIN, YEARS)
        
        # Save to Excel
        output_file = f"data/CompanyData_{ISIN}.xlsx"
        client.save_to_excel(all_data, output_file)
        
        # Output summary
        print("\n" + "="*50)
        print(f"RETRIEVAL SUCCESSFUL: {len(all_data)} records found")
        print("="*50)
        
        if all_data:
            print("\nSample Data (First Record):")
            # Filter to show a few key fields if the record is large
            sample = all_data[0]
            print(json.dumps(sample, indent=2))
            
    except Exception as e:
        print(f"\n[ERROR] API Test Failed: {e}")
        exit(1)

if __name__ == "__main__":
    main()
