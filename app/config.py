import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API settings
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "YOUR_DEFAULT_API_KEY")

# Constants for time calculations
LOADING_TIME_MINUTES = 20
UNLOADING_TIME_MINUTES = 20
WORK_HOURS = 10  # Default work hours
OVERTIME_ALLOWANCE_MINUTES = 50  # Allow trips that go up to 10 minutes over the end time