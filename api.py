import os
import asyncio

import asyncpg
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
from backend.users import router as users_router
from backend.auth import get_current_user
from backend.services.flight_route import get_flight_route
from dotenv import load_dotenv

load_dotenv()  # must run before any module that reads env vars at import time
db_connection_params = {
    "user": os.getenv("DBUSER"),
    "password": os.getenv("DBPASS"),
    "database": os.getenv("DBASE"),
    "host": os.getenv("DBHOST"),
    "port": int(os.getenv("DBPORT", 5432)),
}


class FlightResponse(BaseModel):
    icao24: str
    timestamp: datetime
    callsign: str | None = None
    origin_country: str | None = None
    longitude: float | None = None
    latitude: float | None = None
    baro_altitude: float | None = None
    on_ground: bool | None = None
    velocity: float | None = None
    true_track: float | None = None
    vertical_rate: float | None = None
    geo_altitude: float | None = None
    squawk: str | None = None
    position_source: int | None = None


class PlaneResponse(BaseModel):
    icao24: str
    timestamp: datetime | None = None
    acars: int | None = None
    adsb: int | None = None
    built: int | None = None
    categoryDescription: str | None = None
    country: str | None = None
    engines: int | None = None
    firstFlightDate: str | None = None
    firstSeen: datetime | None = None
    icaoAircraftClass: str | None = None
    lineNumber: str | None = None
    manufacturerIcao: str | None = None
    manufacturerName: str | None = None
    model: str | None = None
    modes: str | None = None
    nextReg: str | None = None
    notes: str | None = None
    operator: str | None = None
    operatorCallsign: str | None = None
    operatorIata: str | None = None
    operatorIcao: str | None = None
    owner: str | None = None
    prevReg: str | None = None
    regUntil: str | None = None
    registered: str | None = None
    registration: str | None = None
    selCal: str | None = None
    serialNumber: str | None = None
    status: str | None = None
    typecode: str | None = None
    vdl: int | None = None


class RouteFlight(BaseModel):
    is_live: bool = False
    callsign: str | None = None
    departure_airport: str | None = None
    arrival_airport: str | None = None
    first_seen: str | None = None
    last_seen: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await asyncpg.create_pool(**db_connection_params)
    yield
    await app.state.pool.close()


app = FastAPI(title="Flight Data API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users_router)


@app.get("/flights", response_model=list[FlightResponse])
async def get_flights_in_extent(
    min_lon: float = Query(..., description="West boundary (longitude)"),
    min_lat: float = Query(..., description="South boundary (latitude)"),
    max_lon: float = Query(..., description="East boundary (longitude)"),
    max_lat: float = Query(..., description="North boundary (latitude)"),
    current_user: dict = Depends(get_current_user),
):
    """Return the most recent position for each aircraft within the given bounding box."""
    if min_lon >= max_lon or min_lat >= max_lat:
        raise HTTPException(
            status_code=400,
            detail="Invalid bounding box: min values must be less than max values",
        )
    if not (-180 <= min_lon <= 180 and -180 <= max_lon <= 180):
        raise HTTPException(
            status_code=400, detail="Longitude must be between -180 and 180"
        )
    if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
        raise HTTPException(
            status_code=400, detail="Latitude must be between -90 and 90"
        )

    query = """
        SELECT DISTINCT ON (fd.icao24)
            fd.icao24, fd.timestamp, fd.callsign, fd.origin_country,
            fd.longitude, fd.latitude, fd.baro_altitude, fd.on_ground,
            fd.velocity, fd.true_track, fd.vertical_rate, fd.geo_altitude,
            fd.squawk, fd.position_source
        FROM flight_data fd
        WHERE
            fd.batch_id = (
                SELECT batch_id FROM download_batch
                WHERE status = 'completed'
                ORDER BY timestamp DESC
                LIMIT 1
            )
            AND fd.longitude BETWEEN $1 AND $2
            AND fd.latitude BETWEEN $3 AND $4
            AND fd.longitude IS NOT NULL
            AND fd.latitude IS NOT NULL
        ORDER BY fd.icao24, fd.timestamp DESC
    """
    async with app.state.pool.acquire() as conn:
        rows = await conn.fetch(query, min_lon, max_lon, min_lat, max_lat)

    return [FlightResponse(**dict(row)) for row in rows]


@app.get("/planes/{icao24}", response_model=PlaneResponse)
async def get_plane(icao24: str, current_user: dict = Depends(get_current_user)):
    """Return static aircraft metadata from the planes table."""
    async with app.state.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM planes WHERE icao24 ILIKE $1",
            icao24.lower(),
        )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Plane '{icao24}' not found")
    return PlaneResponse(**dict(row))


@app.get("/route/{icao24}", response_model=list[RouteFlight])
async def get_route(icao24: str, current_user: dict = Depends(get_current_user)):
    """Return recent flight routes for an aircraft from the OpenSky Network (last 1 day)."""
    import httpx
    try:
        flights = await asyncio.to_thread(get_flight_route, icao24)
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"OpenSky returned {e.response.status_code}: {e.response.text[:200]}",
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="OpenSky request timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not fetch route data: {e}")
    return [RouteFlight(**f) for f in flights]
