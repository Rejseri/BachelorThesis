import requests
import os
import json
import time
import pandas as pd
from typing import Dict, Any, List, Set

class Omx10IndustryGenerator:
    """
    Retrieves ESG data for the top 10 highest revenue companies 
    within the same industry that have at least 2 years of data.
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
        if not os.path.exists(path):
            raise FileNotFoundError(f"API key file not found at: {path}")
        with open(path, "r") as f:
            key = f.read().strip()
        if not key:
            raise ValueError("API key file is empty.")
        return key

    def fetch_feed_data(self, endpoint: str, payload: Dict = None) -> List[Dict[str, Any]]:
        """Handles the asynchronous lifecycle for any feed endpoint."""
        url = f"{self.base_url}/api/v1/feed/{endpoint}"
        print(f"Submitting request to {url}...")
        
        response = requests.post(url, headers=self.headers, json=payload or {})
        if response.status_code != 202:
            response.raise_for_status()
        
        request_id = response.json().get("ID")
        status_url = f"{self.base_url}/api/v1/feed/{request_id}"
        
        print(f"Waiting for processing (ID: {request_id})...")
        while True:
            time.sleep(10)
            res = requests.get(status_url, headers=self.headers)
            if res.status_code == 200:
                data = res.json()
                if data.get("Status") == "Processed":
                    urls = data.get("FeedURLs", [])
                    all_records = []
                    for d_url in urls:
                        dataset = requests.get(d_url, headers=self.headers).json()
                        all_records.extend(dataset.get("Data", []))
                    return all_records
                print(f"    Status: {data.get('Status')}...")
            elif res.status_code != 202:
                res.raise_for_status()

    def generate_data(self):
        # 1. Fetch all companies to get Industry Codes
        print("\n--- [1/4] Fetching all companies and industry metadata ---")
        companies_meta = self.fetch_feed_data("esg-companies")
        industry_map = {c['OrganizationNumber']: c.get('IndustryCode') for c in companies_meta if 'OrganizationNumber' in c}
        name_map = {c['OrganizationNumber']: c.get('Name') for c in companies_meta if 'OrganizationNumber' in c}

        # 2. Fetch reporting units to count years per company
        print("\n--- [2/4] Verifying data completeness (min 2 years) ---")
        reporting_units = self.fetch_feed_data("esg-reporting-units")
        org_years: Dict[str, Set[str]] = {}
        for unit in reporting_units:
            org_num = unit.get("OrganizationNumber")
            from_date = unit.get("From")
            if org_num and from_date:
                year = from_date[:4]
                if org_num not in org_years:
                    org_years[org_num] = set()
                org_years[org_num].add(year)
        
        qualified_orgs = {org for org, years in org_years.items() if len(years) >= 2}

        # 3. Fetch PCAF estimates for 2023 to get Revenue
        print(f"\n--- [3/4] Fetching revenue estimates for 2023 for {len(qualified_orgs)} qualified companies ---")
        # To avoid 400 or payload size issues, we pass the qualified org numbers
        # The API documentation shows "organizationNumbers" as a key
        pcaf_data = self.fetch_feed_data("esg-pcaf-estimates", {
            "organizationNumbers": list(qualified_orgs),
            "years": ["2023"]
        })
        
        # 4. Analyze and filter
        print("\n--- [4/4] Analyzing industry data ---")
        company_stats = []
        for record in pcaf_data:
            org_num = record.get("OrganizationNumber")
            if org_num in qualified_orgs:
                revenue = record.get("Revenue_Estimate", 0)
                industry = industry_map.get(org_num)
                if industry:
                    company_stats.append({
                        "OrganizationNumber": org_num,
                        "Name": name_map.get(org_num, record.get("Name")),
                        "Revenue": revenue,
                        "IndustryCode": industry
                    })

        if not company_stats:
            print("[ERROR] No companies found matching the criteria.")
            return

        df = pd.DataFrame(company_stats)
        
        # Find the industry with the highest total revenue or most top-tier companies
        # We'll pick the industry that contains the #1 highest revenue company
        top_company = df.sort_values(by="Revenue", ascending=False).iloc[0]
        target_industry = top_company["IndustryCode"]
        
        print(f"Highest revenue company: {top_company['Name']} (Revenue: {top_company['Revenue']})")
        print(f"Targeting Industry Code: {target_industry}")

        # Filter for that industry and take top 10
        industry_df = df[df["IndustryCode"] == target_industry].sort_values(by="Revenue", ascending=False).head(10)
        
        target_orgs = industry_df["OrganizationNumber"].tolist()
        
        print(f"Selected Top 10 companies from industry {target_industry}:")
        for i, row in industry_df.iterrows():
            print(f"  - {row['Name']} (Revenue: {row['Revenue']})")

        # Finally, fetch all historical data (2020-2023) for these specific 10 companies
        print(f"\nFetching full historical dataset for these 10 companies...")
        final_pcaf_data = self.fetch_feed_data("esg-pcaf-estimates", {
            "organizationNumbers": target_orgs,
            "years": ["2023", "2022", "2021", "2020"]
        })

        if final_pcaf_data:
            final_df = pd.DataFrame(final_pcaf_data)
            # Add industry info
            final_df["IndustryCode"] = final_df["OrganizationNumber"].map(industry_map)
            
            # Ensure output directory exists
            os.makedirs("data", exist_ok=True)
            
            final_df.to_csv("data/Omx10IndustryData.csv", index=False)
            final_df.to_excel("data/Omx10IndustryData.xlsx", index=False)
            print(f"\nSUCCESS: Data saved to data/Omx10IndustryData.csv/xlsx")
        else:
            print("[ERROR] Failed to retrieve final dataset.")

def main():
    generator = Omx10IndustryGenerator()
    generator.generate_data()

if __name__ == "__main__":
    main()
