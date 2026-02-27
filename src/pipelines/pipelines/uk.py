from typing import Any, Dict
import requests

class UKDataPipeline:
    def __init__(self):
        self.api_url = "https://api.example.com/uk-data"  # Replace with actual API endpoint

    def fetch_data(self) -> Dict[str, Any]:
        response = requests.get(self.api_url)
        response.raise_for_status()  # Raise an error for bad responses
        return response.json()

    def process_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # Implement specific data processing logic for UK data
        processed_data = {
            "key_metric": data["key_metric"],  # Example processing
            "additional_info": data.get("additional_info", {})
        }
        return processed_data

    def run_pipeline(self) -> Dict[str, Any]:
        raw_data = self.fetch_data()
        return self.process_data(raw_data)