from pydantic import BaseModel
from typing import List

# Pydantic model to accept user input with multiple pit locations
class MultiPitRequest(BaseModel):
    start_url: str
    start_time: str  # Start time in HH:MM format
    dump_url: str  # Dump/unloading site URL
    package: str = ""
    pit_urls: List[str]  # List of pit site URLs
    pit_materials: List[str]
    pit_tonnes: List[float]
    work_hours: int = 10  # Optional parameter with default
    adjust_time: int = 0
    pit_load_sizes: List[float]
    pit_rates: List[float]

