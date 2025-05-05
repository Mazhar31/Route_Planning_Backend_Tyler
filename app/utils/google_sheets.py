from datetime import datetime, timedelta
import gspread

# Load service account and sheet
gc = gspread.service_account(filename="sheets.json")
sh = gc.open_by_url("https://docs.google.com/spreadsheets/d/12-NJ-M4DpgCKU5h1Tg4Zj7qhRdQO5vzuUFRDMiVLDk0/edit#gid=0")


def get_or_create_unique_worksheet(base_name):
    existing_titles = [ws.title for ws in sh.worksheets()]
    
    if base_name not in existing_titles:
        return sh.add_worksheet(title=base_name, rows="100", cols="20")

    # If exists, create new with a suffix
    counter = 1
    new_name = f"{base_name} ({counter})"
    while new_name in existing_titles:
        counter += 1
        new_name = f"{base_name} ({counter})"
    return sh.add_worksheet(title=new_name, rows="100", cols="20")


def find_next_empty_row(sheet):
    values = sheet.get_all_values()
    for idx in range(len(values) - 1, -1, -1):
        if any(cell.strip() != "" for cell in values[idx][:6]):  # Check columns A–F
            return idx + 2  # Next row after last non-empty + 1 empty row buffer
    return 1  # Sheet is entirely empty


def write_locations_section(sheet, start_location, dump_location, pit_result, package):
    start_row = find_next_empty_row(sheet)

    sheet.update(f"A{start_row}", [["LOCATIONS: START OF DAY, LOAD SITE, DUMP SITE, END OF DAY"]])
    sheet.format(f"A{start_row}", {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.2, "green": 0.5, "blue": 0.7}})

    headers = [["Location", "Activity", "LAT/LONG", "Location: Google Map Link"]]
    sheet.update(f"A{start_row+1}:D{start_row+1}", headers)
    sheet.format(f"A{start_row+1}:D{start_row+1}", {"textFormat": {"bold": True}})

    rows = [
        [start_location["address"], "Start of Day", f'{start_location["latitude"]}, {start_location["longitude"]}', f'https://www.google.com/maps?q={start_location["latitude"]},{start_location["longitude"]}'],
        [start_location["address"], "End of Day", f'{start_location["latitude"]}, {start_location["longitude"]}', f'https://www.google.com/maps?q={start_location["latitude"]},{start_location["longitude"]}'],
        [package if package else dump_location["address"], "Dumping", f'{dump_location["latitude"]}, {dump_location["longitude"]}', f'https://www.google.com/maps?q={dump_location["latitude"]},{dump_location["longitude"]}'],
        ["Primary Pit", "Loading", f'{pit_result["latitude"]}, {pit_result["longitude"]}', f'https://www.google.com/maps?q={pit_result["latitude"]},{pit_result["longitude"]}']
    ]
    sheet.update(f"A{start_row+2}:D{start_row+5}", rows)


def write_distance_section(sheet, start_location, dump_location, pit_result):
    start_row = find_next_empty_row(sheet)

    sheet.update(f"A{start_row}", [["DISTANCE/SPEED/TIME TRAVELLED DOMESTIC VEHICLE"]])
    sheet.format(f"A{start_row}", {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.2, "green": 0.5, "blue": 0.7}})

    headers = [["", "", "", "Distance (km)", "Time (HH:MM)", "Route"]]
    sheet.update(f"A{start_row+1}:G{start_row+1}", headers)
    sheet.format(f"A{start_row+1}:G{start_row+1}", {"textFormat": {"bold": True}})

    ri = pit_result["route_info"]
    rows = [
        ["START --> LOAD", f'{start_location["latitude"]}, {start_location["longitude"]}', ri["start_to_pit"]["route_url"].split("destination=")[-1].split("&")[0], ri["start_to_pit"]["distance_km"], ri["start_to_pit"]["time_format"], ri["start_to_pit"]["route_url"]],
        ["LOAD --> DUMP", ri["start_to_pit"]["route_url"].split("destination=")[-1].split("&")[0], ri["pit_to_dump"]["route_url"].split("destination=")[-1].split("&")[0], ri["pit_to_dump"]["distance_km"], ri["pit_to_dump"]["time_format"], ri["pit_to_dump"]["route_url"]],
        ["DUMP --> LOAD", ri["pit_to_dump"]["route_url"].split("destination=")[-1].split("&")[0], ri["dump_to_pit"]["route_url"].split("destination=")[-1].split("&")[0], ri["dump_to_pit"]["distance_km"], ri["dump_to_pit"]["time_format"], ri["dump_to_pit"]["route_url"]],
        ["DUMP --< END", ri["dump_to_pit"]["route_url"].split("destination=")[-1].split("&")[0], f'{start_location["latitude"]}, {start_location["longitude"]}', ri["dump_to_start"]["distance_km"], ri["dump_to_start"]["time_format"], ri["dump_to_start"]["route_url"]],
    ]
    sheet.update(f"A{start_row+2}:G{start_row+5}", rows)


def write_schedule_section(sheet, pit_result, start_time_str, adjust_time, load_size, rate_per_tonne, total_trips):
    EXTRA_TIME = 0
    start_row = find_next_empty_row(sheet)
    truck_earning = load_size * rate_per_tonne

    sheet.update(f"A{start_row}", [["ESTIMATED DAILY SCHEDULE + DAILY/HOURLY REVENUE"]])
    sheet.format(f"A{start_row}", {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.2, "green": 0.5, "blue": 0.7}})

    headers = [["Location", "Total Time", "Buffer", "Load/Dump", "Next Stop", "Truck Revenue", "Total Tonnes"]]
    sheet.update(f"A{start_row+1}:G{start_row+1}", headers)
    sheet.format(f"A{start_row+1}:G{start_row+1}", {"textFormat": {"bold": True}})

    rows = []
    current_time = datetime.strptime(start_time_str, "%H:%M")
    total_minutes = 0

    rows.append(["Start of Day", "", current_time.strftime("%I:%M:%S %p"), "", "(START --> LOAD)", ""])

    for i, route in enumerate(pit_result["routes"]):
        steps = route["steps"]
        trip_type = route["type"]

        if trip_type == "work_cycle":
            if i == 0:
                travel_start_to_pit = next((s for s in steps if "Travel to Pit" in s["action"]), None)
                load_step = next((s for s in steps if "Load" in s["action"]), None)
                travel_minutes = int(travel_start_to_pit["time_taken"].split()[0]) if travel_start_to_pit else 0
                load_minutes = int(load_step["time_taken"].split()[0]) if load_step else 0
                trip_total = travel_minutes + load_minutes
                if(adjust_time > 0):
                    EXTRA_TIME = (trip_total/100) * adjust_time
                current_time += timedelta(minutes=(trip_total+EXTRA_TIME))
                total_minutes += (trip_total + EXTRA_TIME)
                rows.append(["Load Site -Clean Pit", f"{trip_total//60}:{str(trip_total%60).zfill(2)}", current_time.strftime("%I:%M:%S %p"), "Load", "(LOAD --> DUMP)", "", load_size])
            else:
                return_to_pit = next((s for s in steps if "Return to Pit" in s["action"]), None)
                load_step = next((s for s in steps if "Load" in s["action"]), None)
                return_minutes = int(return_to_pit["time_taken"].split()[0]) if return_to_pit else 0
                load_minutes = int(load_step["time_taken"].split()[0]) if load_step else 0
                trip_total = return_minutes + load_minutes
                if(adjust_time > 0):
                    EXTRA_TIME = (trip_total/100) * adjust_time
                current_time += timedelta(minutes=(trip_total+EXTRA_TIME))
                total_minutes += (trip_total + EXTRA_TIME)
                rows.append(["Load Site -Clean Pit", f"{trip_total//60}:{str(trip_total%60).zfill(2)}", current_time.strftime("%I:%M:%S %p"), "Load", "(LOAD --> DUMP)", "", load_size])

            travel_to_dump = next((s for s in steps if "Travel to Dump" in s["action"]), None)
            unload_step = next((s for s in steps if "Unload" in s["action"]), None)
            travel_minutes = int(travel_to_dump["time_taken"].split()[0]) if travel_to_dump else 0
            unload_minutes = int(unload_step["time_taken"].split()[0]) if unload_step else 0
            trip_total = travel_minutes + unload_minutes
            if(adjust_time > 0):
                EXTRA_TIME = (trip_total/100) * adjust_time
            current_time += timedelta(minutes=(trip_total+EXTRA_TIME))
            total_minutes += (trip_total + EXTRA_TIME)
            rows.append(["Dump Site", f"{trip_total//60}:{str(trip_total%60).zfill(2)}", current_time.strftime("%I:%M:%S %p"), "Dump", "(DUMP --> LOAD)", truck_earning, ""])

        elif trip_type == "return_to_base":
            return_step = steps[0]
            return_minutes = int(return_step["time_taken"].split()[0])
            if(adjust_time > 0):
                EXTRA_TIME = (return_minutes/100) * adjust_time
            current_time += timedelta(minutes=(return_minutes+EXTRA_TIME))
            total_minutes += (return_minutes + EXTRA_TIME)
            rows.append(["End of Day", f"{return_minutes//60}:{str(return_minutes%60).zfill(2)}", current_time.strftime("%I:%M:%S %p"), "", "(DUMP --< END)", ""])

        elif trip_type == "final_trip":
            travel_to_pit = next((s for s in steps if "Travel to Pit" in s["action"]), None)
            load_step = next((s for s in steps if "Load" in s["action"]), None)
            travel_to_dump = next((s for s in steps if "Travel to Dump" in s["action"]), None)
            unload_step = next((s for s in steps if "Unload" in s["action"]), None)
            return_step = next((s for s in steps if "Return to Base" in s["action"]), None)

            # Try to get 'Return to Pit' from previous trip if not present in current
            return_to_pit = None
            if not travel_to_pit and i > 0:
                prev_steps = pit_result["routes"][i - 1]["steps"]
                return_to_pit = next((s for s in reversed(prev_steps) if "Return to Pit" in s["action"]), None)

            # Load Site row = travel to pit + load (or return to pit + load)
            load_minutes = 0
            if travel_to_pit:
                load_minutes += int(travel_to_pit["time_taken"].split()[0])
            elif return_to_pit:
                load_minutes += int(return_to_pit["time_taken"].split()[0])
            if load_step:
                load_minutes += int(load_step["time_taken"].split()[0])

            if load_minutes > 0:
                if adjust_time > 0:
                    EXTRA_TIME = (load_minutes / 100) * adjust_time
                current_time += timedelta(minutes=(load_minutes + EXTRA_TIME))
                total_minutes += (load_minutes + EXTRA_TIME)
                rows.append(["Load Site -Clean Pit", f"{int(load_minutes)//60}:{str(int(load_minutes)%60).zfill(2)}", current_time.strftime("%I:%M:%S %p"), "Load", "(LOAD --> DUMP)", "", load_size])

            # Dump Site row = travel to dump + unload
            dump_minutes = 0
            if travel_to_dump:
                dump_minutes += int(travel_to_dump["time_taken"].split()[0])
            if unload_step:
                dump_minutes += int(unload_step["time_taken"].split()[0])
            if dump_minutes > 0:
                if adjust_time > 0:
                    EXTRA_TIME = (dump_minutes / 100) * adjust_time
                current_time += timedelta(minutes=(dump_minutes + EXTRA_TIME))
                total_minutes += (dump_minutes + EXTRA_TIME)
                rows.append(["Dump Site", f"{int(dump_minutes)//60}:{str(int(dump_minutes)%60).zfill(2)}", current_time.strftime("%I:%M:%S %p"), "Dump", "(DUMP --> END)", truck_earning, ""])

            # Return to Base
            if return_step:
                return_minutes = int(return_step["time_taken"].split()[0])
                if adjust_time > 0:
                    EXTRA_TIME = (return_minutes / 100) * adjust_time
                current_time += timedelta(minutes=(return_minutes + EXTRA_TIME))
                total_minutes += (return_minutes + EXTRA_TIME)
                rows.append(["End of Day", f"{return_minutes//60}:{str(return_minutes%60).zfill(2)}", current_time.strftime("%I:%M:%S %p"), "", "(DUMP --< END)", ""])
                rows.append([])

    total_minutes = int(total_minutes)
    sheet.update(f"A{start_row+2}:G{start_row+2+len(rows)-1}", rows)
    print("total minutes at the end of the day: ", total_minutes)
    sheet.update(f"A{start_row+2+len(rows)}:G{start_row+2+len(rows)}", [["TOTAL", "", f"{total_minutes//60}:{str(total_minutes%60).zfill(2)}", "", "", f"${truck_earning * total_trips}"]])

    # Add an empty row after the "Total" row
    sheet.update(f"A{start_row+2+len(rows)+1}:G{start_row+2+len(rows)+1}", [["", "", "", "", "", ""]])

    # Calculate hourly rate and update the "Hourly Rate" row
    hourly_rate = truck_earning * total_trips / (total_minutes / 60) if total_minutes > 0 else 0
    sheet.update(f"A{start_row+2+len(rows)+2}:G{start_row+2+len(rows)+2}", [["Hourly Rate", "", "", "", "", f"${hourly_rate:.2f}"]])