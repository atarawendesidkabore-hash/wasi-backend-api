from typing import Dict, Any
import requests

class CountryDataPipeline:
    def __init__(self, country_code: str):
        self.country_code = country_code
        self.api_url = f"https://api.example.com/data/{country_code}"

    def fetch_data(self) -> Dict[str, Any]:
        response = requests.get(self.api_url)
        response.raise_for_status()
        return response.json()

    def process_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # Implement specific data processing logic for each country
        processed_data = {
            "country": self.country_code,
            "value": data.get("value"),
            "timestamp": data.get("timestamp"),
        }
        return processed_data

    def run_pipeline(self) -> Dict[str, Any]:
        raw_data = self.fetch_data()
        return self.process_data(raw_data)

def run_all_pipelines() -> Dict[str, Dict[str, Any]]:
    country_codes = [
        "argentina", "australia", "brazil", "canada", "france",
        "germany", "india", "japan", "mexico", "russia",
        "singapore", "south_africa", "south_korea", "uk", "usa"
    ]
    results = {}
    for code in country_codes:
        pipeline = CountryDataPipeline(code)
        results[code] = pipeline.run_pipeline()
    return results