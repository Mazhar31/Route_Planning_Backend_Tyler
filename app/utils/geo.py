import re
import time
import logging
import requests
from urllib.parse import urlparse, parse_qs
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from app.config import GOOGLE_API_KEY

# Set up logging
logger = logging.getLogger("app.geo")

def unshorten_url(short_url, retries=3, delay=2, wait_time=5):
    """
    Uses a headless browser to fully load a short Google Maps URL
    and extract the final, fully updated URL with accurate coordinates.
    """
    for attempt in range(retries):
        try:
            logger.debug(f"Attempt {attempt + 1}: Trying to unshorten URL via Selenium: {short_url}")

            options = webdriver.ChromeOptions()
            options.add_argument("--headless")
            options.add_argument("--disable-notifications")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")

            driver = webdriver.Chrome(options=options)
            driver.get(short_url)

            time.sleep(wait_time)  # Wait for page to load and URL to update

            final_url = driver.current_url
            logger.debug(f"Selenium unshortened URL: {final_url}")
            driver.quit()

            return final_url

        except Exception as e:
            logger.error(f"[Attempt {attempt + 1}] Selenium failed to unshorten URL: {e}")
            time.sleep(delay)

    return None

def extract_coordinates_or_query(full_url):
    """
    Extract coordinates or location query from a Google Maps URL.
    Returns either a tuple of (lat, lng) or a string query.
    """
    # First, look for coordinates in the format 8m2!3d[lat]!4d[lng]
    place_match = re.search(r'8m2!3d([-.\d]+)!4d([-.\d]+)', full_url)
    if place_match:
        logger.debug(f"Place coordinates found in URL: {place_match.group(1)}, {place_match.group(2)}")
        return float(place_match.group(1)), float(place_match.group(2))
    
    # If no place coordinates, check for view coordinates using the /@lat,lng pattern
    view_match = re.search(r'/@([-.\d]+),([-.\d]+)', full_url)
    if view_match:
        logger.debug(f"View coordinates found in URL: {view_match.group(1)}, {view_match.group(2)}")
        return float(view_match.group(1)), float(view_match.group(2))

    # If no coordinates in URL path, check query parameters
    parsed = urlparse(full_url)
    query = parse_qs(parsed.query)

    if 'q' in query:
        q_value = query['q'][0].strip()
        coord_match = re.match(r'^([-.\d]+),\s*([-.\d]+)$', q_value)
        if coord_match:
            logger.debug(f"Coordinates found in query: {coord_match.group(1)}, {coord_match.group(2)}")
            return float(coord_match.group(1)), float(coord_match.group(2))
        else:
            logger.debug(f"Place name found in query: {q_value}")
            return q_value  # Likely a place name

    # If we still have no coordinates, look for place coordinates in various formats
    # This checks for coordinates directly in the query string
    coords_match = re.search(r'[?&]d=([-.\d]+),([-.\d]+)', full_url)
    if coords_match:
        logger.debug(f"Coordinates found in query parameters: {coords_match.group(1)}, {coords_match.group(2)}")
        return float(coords_match.group(1)), float(coords_match.group(2))

    return None

def get_coordinates_from_place(place, api_key):
    """
    Convert a place name to coordinates using Google Geocoding API.
    """
    logger.debug(f"Getting coordinates for place: {place}")
    endpoint = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": place, "key": api_key}
    response = requests.get(endpoint, params=params)
    data = response.json()
    if data['results']:
        location = data['results'][0]['geometry']['location']
        logger.debug(f"Coordinates for place '{place}': {location['lat']}, {location['lng']}")
        return location['lat'], location['lng']
    logger.warning(f"Could not get coordinates for place: {place}")
    return None

def reverse_geocode(lat, lng, api_key=GOOGLE_API_KEY):
    """
    Convert coordinates to an address using Google Reverse Geocoding API.
    """
    logger.debug(f"Getting address for coordinates: {lat}, {lng}")
    url = f"https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lng}&key={api_key}"
    response = requests.get(url)
    data = response.json()
    if data['results']:
        logger.debug(f"Address for coordinates: {data['results'][0]['formatted_address']}")
        return data['results'][0]['formatted_address']
    logger.warning("Could not reverse geocode coordinates.")
    return "Unknown location"

def get_coordinates(url, api_key=GOOGLE_API_KEY):
    """
    Extract coordinates from a Google Maps URL.
    """
    logger.debug(f"Getting coordinates from URL: {url}")
    # If it's a Google Maps URL, directly extract the coordinates or query
    if url.startswith("https://www.google.com/maps?q="):
        info = extract_coordinates_or_query(url)
        if isinstance(info, tuple):  # Direct coordinates
            logger.debug(f"Direct coordinates extracted from Google Maps URL: {info}")
            return info
        elif isinstance(info, str):  # Place name
            coords = get_coordinates_from_place(info, api_key)
            if coords:
                return coords
    else:
        # Otherwise, unshorten the URL first
        real_url = unshorten_url(url)
        if not real_url:
            raise Exception("Could not unshorten URL.")
        
        # Extract coordinates or query from the unshortened URL
        info = extract_coordinates_or_query(real_url)

        if isinstance(info, tuple):  # Direct coordinates
            return info
        elif isinstance(info, str):  # Place name
            coords = get_coordinates_from_place(info, api_key)
            if coords:
                return coords
    
    raise Exception("Could not extract coordinates.")

def get_directions(start, end, api_key=GOOGLE_API_KEY):
    """
    Get directions between two points using Google Directions API.
    """
    logger.debug(f"Getting directions from {start} to {end}")
    endpoint = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": f"{start[0]},{start[1]}",
        "destination": f"{end[0]},{end[1]}",
        "mode": "driving",
        "avoid": "tolls|ferries",
        "key": api_key
    }
    try:
        response = requests.get(endpoint, params=params)
        data = response.json()

        if data.get("routes"):
            leg = data["routes"][0]["legs"][0]
            
            # Extract original duration in seconds
            original_seconds = leg["duration"]["value"]
            adjusted_seconds = original_seconds
            adjusted_minutes = adjusted_seconds // 60
            adjusted_text = f"{adjusted_minutes} mins"

            # Extract distance in kilometers
            distance_text = leg["distance"]["text"]
            distance_value = leg["distance"]["value"] / 1000  # Convert meters to kilometers
            
            # Format time as HH:MM
            hours = adjusted_minutes // 60
            mins = adjusted_minutes % 60
            time_format = f"{hours:02d}:{mins:02d}"

            logger.debug(f"Original duration: {original_seconds}s, Adjusted: {adjusted_seconds}s, Distance: {distance_text}")
            
            return {
                "distance": distance_text,
                "distance_km": round(distance_value, 1),  # Round to 1 decimal place
                "duration": adjusted_text,
                "duration_seconds": adjusted_seconds,
                "time_format": time_format,
                "route_url": f"https://www.google.com/maps/dir/?api=1&origin={start[0]},{start[1]}&destination={end[0]},{end[1]}&travelmode=driving"
            }
        else:
            error_message = data.get("error_message", "Unknown error")
            logger.error(f"Error from Google Directions API: {error_message}")
            raise Exception(f"Directions API error: {error_message}")
    except Exception as e:
        logger.error(f"Could not get directions: {str(e)}")
        raise Exception(f"Could not get directions: {str(e)}")