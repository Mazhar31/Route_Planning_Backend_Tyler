import logging
from datetime import datetime, timedelta

from app.config import (
    LOADING_TIME_MINUTES, 
    UNLOADING_TIME_MINUTES, 
    OVERTIME_ALLOWANCE_MINUTES,
    GOOGLE_API_KEY
)
from app.utils.geo import get_directions

logger = logging.getLogger("app.routing")


def calculate_pit_routes(start_coords, pit_coords, dump_coords, start_time, work_hours, pit_name="", adjust_time=0):
    print("calculate pit routes started")
    """
    Calculate routes for a single pit, returning to the start location at the end
    """
    # Apply adjust_time percentage buffer to each duration component
    def apply_adjustment(seconds):
        return seconds + int(seconds * adjust_time / 100)
    
    # Parse the start time provided by the user
    current_time = datetime.strptime(start_time, "%H:%M")
    
    # Calculate the scheduled end time (based on start time + work hours)
    scheduled_end_time = current_time + timedelta(hours=work_hours)
    
    # Hard cutoff at 5:00 PM - create a datetime for today at 17:00
    today = datetime.now().date()
    hard_cutoff = datetime.combine(today, datetime.strptime("17:20", "%H:%M").time())
    
    # Use the earlier of scheduled_end_time or hard_cutoff
    original_end_time = scheduled_end_time
    if scheduled_end_time > hard_cutoff:
        scheduled_end_time = hard_cutoff
        print(f"Using hard cutoff of 5:00 PM instead of calculated end time {original_end_time.strftime('%H:%M')}")
    
    logger.debug(f"Start time: {current_time.strftime('%H:%M')}, Scheduled end time: {scheduled_end_time.strftime('%H:%M')}")
    print(f"Start time: {current_time.strftime('%H:%M')}, Scheduled end time: {scheduled_end_time.strftime('%H:%M')}")
    
    # Add overtime allowance for potentially going over the scheduled end time
    max_end_time = scheduled_end_time + timedelta(minutes=OVERTIME_ALLOWANCE_MINUTES)
    print(f"Max end time with overtime allowance: {max_end_time.strftime('%H:%M')}")
    
    # Start location is also end location
    end_coords = start_coords

    results = []
    current_location = start_coords
    trip_counter = 0

    # Store route information for different segments
    route_segments = {
        "start_to_pit": None,
        "pit_to_dump": None,
        "dump_to_pit": None,
        "dump_to_start": None
    }

    # Pre-calculate directions for the segments we'll need
    if current_location != pit_coords:
        route_segments["start_to_pit"] = get_directions(start_coords, pit_coords, GOOGLE_API_KEY)
    
    route_segments["pit_to_dump"] = get_directions(pit_coords, dump_coords, GOOGLE_API_KEY)
    route_segments["dump_to_pit"] = get_directions(dump_coords, pit_coords, GOOGLE_API_KEY)
    
    if dump_coords != end_coords:
        route_segments["dump_to_start"] = get_directions(dump_coords, end_coords, GOOGLE_API_KEY)

    while True:
        trip_steps = []
        
        # Calculate if we have time for a full trip and return
        directions_to_pit = route_segments["start_to_pit"] if current_location != pit_coords else {"duration_seconds": 0}
        directions_pit_to_dump = route_segments["pit_to_dump"]
        directions_dump_to_pit = route_segments["dump_to_pit"]
        directions_dump_to_end = route_segments["dump_to_start"] if dump_coords != end_coords else {"duration_seconds": 0}
        directions_pit_to_end = get_directions(pit_coords, end_coords, GOOGLE_API_KEY) if pit_coords != end_coords else {"duration_seconds": 0}
        
        # Fix the calculations - ensure we're adding these values correctly
        total_trip_time_seconds = (
            (directions_to_pit["duration_seconds"] if directions_to_pit else 0) +
            (LOADING_TIME_MINUTES * 60) +
            directions_pit_to_dump["duration_seconds"] +
            (UNLOADING_TIME_MINUTES * 60) +
            directions_dump_to_pit["duration_seconds"]
        )
        # Apply adjustment to total time
        total_trip_time_seconds = apply_adjustment(total_trip_time_seconds)
        
        # Calculate time to return to base from pit
        return_from_pit_seconds = directions_pit_to_end["duration_seconds"]
        return_from_pit_seconds = apply_adjustment(return_from_pit_seconds)
        
        # Predict when the full trip (including return to base) would end
        predicted_end_time = current_time + timedelta(seconds=(total_trip_time_seconds + return_from_pit_seconds))
        
        print(f"Trip {trip_counter + 1}: Predicted end time: {predicted_end_time.strftime('%H:%M')}, Max allowed: {max_end_time.strftime('%H:%M')}")
        
        # First, check if we can do a full cycle (current -> pit -> dump -> pit)
        # If not, check if we can do a half cycle (current -> pit -> dump -> end)
        # If not, just return to base
        
        if predicted_end_time > max_end_time:
            print(f"Full cycle would exceed max time by {(predicted_end_time - max_end_time).seconds // 60} minutes")
            
            # Fix the half-cycle calculation - ensure we're adding these values correctly
            half_cycle_seconds = (
                (directions_to_pit["duration_seconds"] if directions_to_pit else 0) +
                (LOADING_TIME_MINUTES * 60) +
                directions_pit_to_dump["duration_seconds"] +
                (UNLOADING_TIME_MINUTES * 60) +
                (directions_dump_to_end["duration_seconds"] if directions_dump_to_end else 0)
            )
            # Apply adjustment to half cycle time
            half_cycle_seconds = apply_adjustment(half_cycle_seconds)
            
            half_cycle_end_time = current_time + timedelta(seconds=half_cycle_seconds)
            
            print(f"Half cycle would end at: {half_cycle_end_time.strftime('%H:%M')}")
            
            if half_cycle_end_time <= max_end_time:
                print(f"Will do half cycle and return to base")
                # We can do a half cycle and return to base
                
                # STEP 1: Go to pit
                if current_location != pit_coords:
                    pit_travel_seconds = apply_adjustment(directions_to_pit["duration_seconds"])
                    arrival_at_pit = current_time + timedelta(seconds=pit_travel_seconds)
                    trip_steps.append({
                        "action": f"Travel to {pit_name or 'Pit Site'}",
                        "time_taken": directions_to_pit["duration"],
                        "arrival_time": arrival_at_pit.strftime("%H:%M"),
                        "distance": directions_to_pit["distance"],
                        "distance_km": directions_to_pit["distance_km"],
                        "route_url": directions_to_pit["route_url"],
                        "time_format": directions_to_pit["time_format"]
                    })
                    current_time = arrival_at_pit
                
                # STEP 2: Load at pit
                loading_seconds = apply_adjustment(LOADING_TIME_MINUTES * 60)
                load_complete_time = current_time + timedelta(seconds=loading_seconds)
                trip_steps.append({
                    "action": f"Load at {pit_name or 'Pit Site'}",
                    "time_taken": f"{LOADING_TIME_MINUTES} minutes",
                    "arrival_time": load_complete_time.strftime("%H:%M"),
                })
                current_time = load_complete_time
                
                # STEP 3: Go to dump
                dump_travel_seconds = apply_adjustment(directions_pit_to_dump["duration_seconds"])
                arrival_at_dump = current_time + timedelta(seconds=dump_travel_seconds)
                trip_steps.append({
                    "action": "Travel to Dump Site",
                    "time_taken": directions_pit_to_dump["duration"],
                    "arrival_time": arrival_at_dump.strftime("%H:%M"),
                    "distance": directions_pit_to_dump["distance"],
                    "distance_km": directions_pit_to_dump["distance_km"],
                    "route_url": directions_pit_to_dump["route_url"],
                    "time_format": directions_pit_to_dump["time_format"]
                })
                current_time = arrival_at_dump
                
                # STEP 4: Unload at dump
                unloading_seconds = apply_adjustment(UNLOADING_TIME_MINUTES * 60)
                unload_complete_time = current_time + timedelta(seconds=unloading_seconds)
                trip_steps.append({
                    "action": "Unload at Dump Site",
                    "time_taken": f"{UNLOADING_TIME_MINUTES} minutes",
                    "arrival_time": unload_complete_time.strftime("%H:%M"),
                })
                current_time = unload_complete_time
                
                # STEP 5: Return to base
                end_travel_seconds = apply_adjustment(directions_dump_to_end["duration_seconds"] if directions_dump_to_end else 0)
                arrival_at_base = current_time + timedelta(seconds=end_travel_seconds)
                trip_steps.append({
                    "action": "Return to Base",
                    "time_taken": directions_dump_to_end["duration"] if directions_dump_to_end else "0 mins",
                    "arrival_time": arrival_at_base.strftime("%H:%M"),
                    "distance": directions_dump_to_end["distance"] if directions_dump_to_end else "0 km",
                    "distance_km": directions_dump_to_end["distance_km"] if directions_dump_to_end else 0,
                    "route_url": directions_dump_to_end["route_url"] if directions_dump_to_end else "",
                    "time_format": directions_dump_to_end["time_format"] if directions_dump_to_end else "00:00"
                })
                current_time = arrival_at_base
                
                # Add the completed trip to results
                results.append({
                    "trip": trip_counter + 1,
                    "steps": trip_steps,
                    "type": "final_trip"
                })
                
                trip_counter += 1
                break
                
            else:
                print(f"Half cycle exceeds max time. Will return to base directly.")
                # Can't do a half cycle either, just return to base
                if current_location != end_coords:
                    if current_location == pit_coords:
                        directions_to_end = directions_pit_to_end
                    else:  # current_location == dump_coords
                        directions_to_end = directions_dump_to_end
                        
                    return_seconds = apply_adjustment(directions_to_end["duration_seconds"] if directions_to_end else 0)
                    arrival_time = current_time + timedelta(seconds=return_seconds)
                    
                    trip_steps.append({
                        "action": "Return to Base",
                        "time_taken": directions_to_end["duration"] if directions_to_end else "0 mins",
                        "arrival_time": arrival_time.strftime("%H:%M"),
                        "distance": directions_to_end["distance"] if directions_to_end else "0 km",
                        "distance_km": directions_to_end["distance_km"] if directions_to_end else 0,
                        "route_url": directions_to_end["route_url"] if directions_to_end else "",
                        "time_format": directions_to_end["time_format"] if directions_to_end else "00:00"
                    })
                    
                    results.append({
                        "trip": trip_counter + 1,
                        "steps": trip_steps,
                        "type": "return_to_base"
                    })
                    
                    current_time = arrival_time
                break
        
        print(f"Trip {trip_counter + 1}: Will perform full cycle")
        # We have time for another trip
        # STEP 1: Go from current location to pit (if needed)
        if current_location != pit_coords:
            pit_travel_seconds = apply_adjustment(directions_to_pit["duration_seconds"])
            arrival_at_pit = current_time + timedelta(seconds=pit_travel_seconds)
            trip_steps.append({
                "action": f"Travel to {pit_name or 'Pit Site'}",
                "time_taken": directions_to_pit["duration"],
                "arrival_time": arrival_at_pit.strftime("%H:%M"),
                "distance": directions_to_pit["distance"],
                "distance_km": directions_to_pit["distance_km"],
                "route_url": directions_to_pit["route_url"],
                "time_format": directions_to_pit["time_format"]
            })
            current_time = arrival_at_pit
        
        # STEP 2: Load at pit (20 minutes)
        loading_seconds = apply_adjustment(LOADING_TIME_MINUTES * 60)
        load_complete_time = current_time + timedelta(seconds=loading_seconds)
        trip_steps.append({
            "action": f"Load at {pit_name or 'Pit Site'}",
            "time_taken": f"{LOADING_TIME_MINUTES} minutes",
            "arrival_time": load_complete_time.strftime("%H:%M"),
        })
        current_time = load_complete_time
        
        # STEP 3: Go from pit to dump
        dump_travel_seconds = apply_adjustment(directions_pit_to_dump["duration_seconds"])
        arrival_at_dump = current_time + timedelta(seconds=dump_travel_seconds)
        trip_steps.append({
            "action": "Travel to Dump Site",
            "time_taken": directions_pit_to_dump["duration"],
            "arrival_time": arrival_at_dump.strftime("%H:%M"),
            "distance": directions_pit_to_dump["distance"],
            "distance_km": directions_pit_to_dump["distance_km"],
            "route_url": directions_pit_to_dump["route_url"],
            "time_format": directions_pit_to_dump["time_format"]
        })
        current_time = arrival_at_dump
        
        # STEP 4: Unload at dump (20 minutes)
        unloading_seconds = apply_adjustment(UNLOADING_TIME_MINUTES * 60)
        unload_complete_time = current_time + timedelta(seconds=unloading_seconds)
        trip_steps.append({
            "action": "Unload at Dump Site",
            "time_taken": f"{UNLOADING_TIME_MINUTES} minutes",
            "arrival_time": unload_complete_time.strftime("%H:%M"),
        })
        current_time = unload_complete_time
        
        # STEP 5: Go back to pit for next load
        pit_return_seconds = apply_adjustment(directions_dump_to_pit["duration_seconds"])
        arrival_back_at_pit = current_time + timedelta(seconds=pit_return_seconds)
        trip_steps.append({
            "action": f"Return to {pit_name or 'Pit Site'}",
            "time_taken": directions_dump_to_pit["duration"],
            "arrival_time": arrival_back_at_pit.strftime("%H:%M"),
            "distance": directions_dump_to_pit["distance"],
            "distance_km": directions_dump_to_pit["distance_km"],
            "route_url": directions_dump_to_pit["route_url"],
            "time_format": directions_dump_to_pit["time_format"]
        })
        current_time = arrival_back_at_pit
        
        # Add the completed trip to results
        results.append({
            "trip": trip_counter + 1,
            "steps": trip_steps,
            "type": "work_cycle"
        })
        
        # Update for next iteration
        current_location = pit_coords
        trip_counter += 1
    
    # Calculate if the actual end time is after the scheduled end time
    overtime_minutes = 0
    if current_time > scheduled_end_time:
        overtime_delta = current_time - scheduled_end_time
        overtime_minutes = overtime_delta.seconds // 60
        print(f"Overtime: {overtime_minutes} minutes")
    
    print(f"Final end time: {current_time.strftime('%H:%M')}")
    
    # Create a dictionary of route segments for easy access in the frontend
    route_info = {
        "start_to_pit": {
            "distance_km": route_segments["start_to_pit"]["distance_km"] if route_segments["start_to_pit"] else 0,
            "time_format": route_segments["start_to_pit"]["time_format"] if route_segments["start_to_pit"] else "00:00",
            "route_url": route_segments["start_to_pit"]["route_url"] if route_segments["start_to_pit"] else ""
        },
        "pit_to_dump": {
            "distance_km": route_segments["pit_to_dump"]["distance_km"],
            "time_format": route_segments["pit_to_dump"]["time_format"],
            "route_url": route_segments["pit_to_dump"]["route_url"]
        },
        "dump_to_pit": {
            "distance_km": route_segments["dump_to_pit"]["distance_km"],
            "time_format": route_segments["dump_to_pit"]["time_format"],
            "route_url": route_segments["dump_to_pit"]["route_url"]
        },
        "dump_to_start": {
            "distance_km": route_segments["dump_to_start"]["distance_km"] if route_segments["dump_to_start"] else 0,
            "time_format": route_segments["dump_to_start"]["time_format"] if route_segments["dump_to_start"] else "00:00",
            "route_url": route_segments["dump_to_start"]["route_url"] if route_segments["dump_to_start"] else ""
        }
    }
    print("calculate pit routes ended")

    return {
        "routes": results,
        "actual_end_time": current_time.strftime("%H:%M"),
        "overtime_minutes": overtime_minutes,
        "total_trips": trip_counter,
        "route_info": route_info
    }