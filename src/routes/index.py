from fastapi import APIRouter
from engines.index_calculation import calculate_index
from pipelines.country_data import get_country_data

router = APIRouter()

@router.get("/index/{country_code}")
async def get_index(country_code: str):
    data = get_country_data(country_code)
    index_value = calculate_index(data)
    return {"country_code": country_code, "index_value": index_value}

@router.get("/index")
async def get_all_indices():
    indices = {}
    for country_code in ["argentina", "australia", "brazil", "canada", "france", 
                         "germany", "india", "japan", "mexico", "russia", 
                         "singapore", "south_africa", "south_korea", "uk", "usa"]:
        data = get_country_data(country_code)
        indices[country_code] = calculate_index(data)
    return indices