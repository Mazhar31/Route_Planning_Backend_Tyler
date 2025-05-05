import logging
import time
from datetime import datetime, timedelta
from fastapi import HTTPException
from app.models import MultiPitRequest
from app.utils.geo import get_coordinates, reverse_geocode
from app.utils.routing import calculate_pit_routes
from app.config import GOOGLE_API_KEY
from app.utils.google_sheets import (
    get_or_create_unique_worksheet,
    write_locations_section,
    write_distance_section,
    write_schedule_section
)

logger = logging.getLogger("app.api")

async def get_multi_pit_route(data: MultiPitRequest):
    """
    Calculate routes for multiple pit locations and write each to a separate sheet.
    """
    try:
        # Step 1: Coordinates and addresses
        print("hello")
        start_coords = get_coordinates(data.start_url, GOOGLE_API_KEY)
        start_address = reverse_geocode(start_coords[0], start_coords[1], GOOGLE_API_KEY)
        dump_coords = get_coordinates(data.dump_url, GOOGLE_API_KEY)
        dump_address = reverse_geocode(dump_coords[0], dump_coords[1], GOOGLE_API_KEY)

        # Step 2: Pit site preparation
        pit_locations = []
        for i, pit_url in enumerate(data.pit_urls):
            pit_coords = get_coordinates(pit_url, GOOGLE_API_KEY)
            pit_address = reverse_geocode(pit_coords[0], pit_coords[1], GOOGLE_API_KEY)
            pit_locations.append({
                "index": i + 1,
                "name": f"Pit {i + 1}",
                "coords": pit_coords,
                "address": pit_address
            })

        # Step 3: Work timing
        work_hours = data.work_hours
        scheduled_end_time = datetime.strptime(data.start_time, "%H:%M") + timedelta(hours=work_hours)

        # Step 4: Route calculations
        pit_results = []
        for pit in pit_locations:
            result = calculate_pit_routes(
                start_coords=start_coords,
                pit_coords=pit["coords"],
                dump_coords=dump_coords,
                start_time=data.start_time,
                work_hours=work_hours,
                pit_name=pit["name"],
                adjust_time=data.adjust_time,
            )
            pit_results.append({
                "pit_index": pit["index"],
                "pit_name": pit["name"],
                "pit_address": pit["address"],
                "latitude": pit["coords"][0],
                "longitude": pit["coords"][1],
                **result
            })
            print("\n\nPit Results:", pit_results, "\n\n")

        # Step 5: Write each pit's data to its own sheet
        for i, pit_result in enumerate(pit_results):
            sheet = get_or_create_unique_worksheet(f"{data.package}-{data.pit_materials[i]}")

            write_locations_section(
                sheet=sheet,
                start_location={
                    "latitude": start_coords[0],
                    "longitude": start_coords[1],
                    "address": start_address
                },
                dump_location={
                    "latitude": dump_coords[0],
                    "longitude": dump_coords[1],
                    "address": dump_address
                },
                pit_result=pit_result,
                package=data.package if isinstance(data.package, str) else ""
            )

            time.sleep(1)

            write_distance_section(
                sheet=sheet,
                start_location={
                    "latitude": start_coords[0],
                    "longitude": start_coords[1]
                },
                dump_location={
                    "latitude": dump_coords[0],
                    "longitude": dump_coords[1]
                },
                pit_result=pit_result
            )

            time.sleep(1)

            write_schedule_section(
                sheet=sheet,
                pit_result=pit_result,
                start_time_str=data.start_time,
                adjust_time=data.adjust_time,
                load_size=data.pit_load_sizes[i],
                rate_per_tonne=data.pit_rates[i],
                total_trips=pit_results[i]["total_trips"]
            )

        return {"status": "stored in sheets"}

    except Exception as e:
        logger.error(f"Error in get_multi_pit_route: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
