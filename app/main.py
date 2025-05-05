import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.models import MultiPitRequest
from app.api.routes import get_multi_pit_route

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("app")

app = FastAPI()

# Allow all origins for CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
)

@app.get("/")
async def root():
    """
    Root endpoint for health check
    """
    return {"message": "Route planning API is running"}

@app.post("/get-multi-pit-route")
async def route_multi_pit(data: MultiPitRequest):
    """
    Calculate routes for multiple pit locations
    """
    return await get_multi_pit_route(data)
