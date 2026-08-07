from typing import Any, Dict

def process_india_data(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    # Implement the specific data processing logic for India
    processed_data = {
        "country": "India",
        "processed_value": raw_data.get("value") * 1.1,  # Example processing
        "timestamp": raw_data.get("timestamp"),
    }
    return processed_data

def fetch_india_data() -> Dict[str, Any]:
    # Implement the logic to fetch raw data for India
    raw_data = {
        "value": 100,  # Example raw data
        "timestamp": "2023-10-01T00:00:00Z",
    }
    return raw_data

def run_india_pipeline() -> Dict[str, Any]:
    raw_data = fetch_india_data()
    processed_data = process_india_data(raw_data)
    return processed_data