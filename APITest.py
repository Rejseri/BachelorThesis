import requests
import os
import json
import time
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

def main():
    """Main execution flow for testing the Stamdata ESG API."""
    try:
        # Configuration
        ISINS_TO_TEST = ["NO0010881246"] # Avinor AS
        YEARS_TO_TEST = ["2023"]
        
        # Initialize Client
        client = StamdataAPIClient()

        # Step 1: Request Data (Async)
        request_id = client.request_esg_pcaf_estimates(ISINS_TO_TEST, YEARS_TO_TEST)
        print(f"Successfully queued request. ID: {request_id}")

        # Step 2: Poll for completion
        download_urls = client.poll_for_completion(request_id)
        print(f"Processing complete. {len(download_urls)} file(s) available.")

        # Step 3: Retrieve Results
        # For this test, we just fetch the first available file
        final_data = client.download_data(download_urls[0])
        
        # Output summary
        print("\n" + "="*50)
        print("API TEST SUCCESSFUL")
        print("="*50)
        
        # Display meta info
        meta = final_data.get("Meta", {})
        print(f"Generated At: {final_data.get('GeneratedAt')}")
        print(f"Data Version: {meta.get('DataVersion')}")
        
        # Display data count
        results = final_data.get("Data", [])
        print(f"Records retrieved: {len(results)}")
        
        if results:
            print("\nSample Record (First Result):")
            print(json.dumps(results[0], indent=2))
            
    except Exception as e:
        print(f"\n[ERROR] API Test Failed: {e}")
        exit(1)

if __name__ == "__main__":
    main()
