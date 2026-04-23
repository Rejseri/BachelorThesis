import requests
import os
import time
import pandas as pd
from typing import Dict, Any, List, Set

class StamdataCompaniesClient:
    """
    A client for retrieving companies from the Stamdata ESG API
    that have complete data for at least 2 years.
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

    def _request_feed(self, endpoint: str) -> str:
        """
        Submits a request to a feed endpoint.
        Returns the Request ID (UUID).
        """
        url = f"{self.base_url}/api/v1/feed/{endpoint}"

        print(f"Submitting request to {url}...")
        response = requests.post(url, headers=self.headers, json={})
        
        if response.status_code == 202:
            request_id = response.json().get("ID")
            if not request_id:
                raise ValueError("API returned 202 but no Request ID was found.")
            return request_id
        
        response.raise_for_status()
        return ""

    def _poll_for_completion(self, request_id: str, interval: int = 5, max_attempts: int = 24) -> List[str]:
        """
        Polls the API until the request status is 'Processed'.
        Returns a list of download URLs.
        """
        status_url = f"{self.base_url}/api/v1/feed/{request_id}"
        print(f"Waiting for processing (ID: {request_id})...")

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

    def _download_data(self, download_url: str) -> Dict[str, Any]:
        """Downloads the final JSON data from the provided URL."""
        print(f"Downloading dataset...")
        response = requests.get(download_url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def fetch_feed_data(self, endpoint: str) -> List[Dict[str, Any]]:
        """
        Handles the entire lifecycle for a given feed: Request -> Poll -> Download -> Parse.
        """
        try:
            request_id = self._request_feed(endpoint)
            download_urls = self._poll_for_completion(request_id)
            
            all_records = []
            for url in download_urls:
                dataset = self._download_data(url)
                records = dataset.get("Data", [])
                all_records.extend(records)
                
            return all_records
        except Exception as e:
            print(f"[ERROR] Failed to fetch feed '{endpoint}': {e}")
            raise

    def get_companies_with_min_years(self, min_years: int = 2) -> List[Dict[str, Any]]:
        """
        Retrieves companies that have ESG reporting data for at least `min_years` distinct years.
        """
        print(f"\n--- [Step 1] Fetching all available companies ---")
        companies = self.fetch_feed_data("esg-companies")
        
        print(f"\n--- [Step 2] Fetching ESG reporting units to check data completeness ---")
        reporting_units = self.fetch_feed_data("esg-reporting-units")

        print(f"\n--- [Step 3] Filtering companies with >= {min_years} years of data ---")
        # Map each OrganizationNumber to a set of unique years reported
        org_years: Dict[str, Set[str]] = {}
        for unit in reporting_units:
            org_num = unit.get("OrganizationNumber")
            from_date = unit.get("From")
            
            if org_num and from_date:
                # Extract year from 'YYYY-MM-DD'
                year = from_date[:4]
                if org_num not in org_years:
                    org_years[org_num] = set()
                org_years[org_num].add(year)

        filtered_companies = []
        for comp in companies:
            org_num = comp.get("OrganizationNumber")
            # Include only those with at least min_years unique years
            if org_num in org_years and len(org_years[org_num]) >= min_years:
                filtered_companies.append(comp)

        return filtered_companies

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
            self.save_to_csv(data, filename.replace(".xlsx", ".csv"))
        except Exception as e:
            print(f"[ERROR] Failed to save to Excel: {e}")

def main():
    try:
        client = StamdataCompaniesClient()
        
        # Fetch companies with >= 2 years of complete data
        companies = client.get_companies_with_min_years(min_years=2)
        
        # We overwrite AllCompanies.csv so it contains the filtered data
        output_file = "data/AllCompanies.csv"
        client.save_to_csv(companies, output_file)
        
        print("\n" + "="*50)
        print(f"RETRIEVAL SUCCESSFUL: {len(companies)} companies found with complete data for >= 2 years")
        print("="*50)
        
    except Exception as e:
        print(f"\n[ERROR] Execution failed: {e}")
        exit(1)

if __name__ == "__main__":
    main()
