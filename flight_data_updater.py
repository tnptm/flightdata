"""
This should get the latest flight data from the OpenSky Network API and update the database with the new information.
When running it will get the latest flight data every 10 seconds.
this uses httpx library to make HTTP requests and uses asyncio for asynchronous operations.
API credentials for the bearer token should be read from opensky-credentials.json file.
Data is stored into a PostgreSQL database using asyncpg library so that data is appended by timestamp and not overwritten.
"""

import asyncio
import os
import time
import httpx
import asyncpg
from loguru import logger
from datetime import datetime

# from db_schema import list_of_table_sqls, parse_table_name_from_sql, db_connection_params
from dotenv import load_dotenv
from token_manager import TokenManager, TokenInitialization
from pydantic import BaseModel, Field

# from typing import LiteralString
load_dotenv()

TOKEN_URL = os.getenv(
    "TOKEN_URL",
    "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token",
)
TOKEN_CREDENTIALS_FILE = os.getenv("TOKEN_CREDENTIALS_FILE", "token_credentials.json")

# database connection parameters for asyncpg
db_connection_params = {
    "user": os.getenv("DBUSER"),
    "password": os.getenv("DBPASS"),
    "database": os.getenv("DBASE"),
    "host": os.getenv("DBHOST"),
    "port": int(os.getenv("DBPORT", 5432)),
}

logger.add(
    "flight_data_updater.log", rotation="1 day", retention="7 days", level="INFO"
)


class FlightData(BaseModel):
    icao24: str
    timestamp: datetime
    callsign: str | None = None
    origin_country: str | None = None
    time_position: datetime | None = None
    last_contact: datetime | None = None
    longitude: float | None = None
    latitude: float | None = None
    baro_altitude: float | None = None
    on_ground: bool | None = None
    velocity: float | None = None
    true_track: float | None = None
    vertical_rate: float | None = None
    sensors: list[str] | None = Field(default_factory=list)
    geo_altitude: float | None = None
    squawk: str | None = None
    spi: bool | None = None
    position_source: int | None = None


async def get_flight_data(bearer_token: str) -> list[dict]:
    url = "https://opensky-network.org/api/states/all"
    headers = {"Authorization": f"Bearer {bearer_token}"}
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        if response.status_code == 200:
            return response.json().get("states", [])
        else:
            logger.error(
                f"Failed to fetch flight data: {response.status_code} - {response.text}"
            )
            return []


async def save_flight_data_to_db(flight_data: list[list], batch_id: int) -> bool:
    conn = await asyncpg.connect(**db_connection_params)
    time_now = datetime.now()
    skipped = 0
    try:
        for flight in flight_data:
            try:
                flight_obj = FlightData(
                    icao24=flight[0],
                    timestamp=time_now,
                    callsign=flight[1],
                    origin_country=flight[2],
                    time_position=datetime.fromtimestamp(flight[3])
                    if flight[3]
                    else None,
                    last_contact=datetime.fromtimestamp(flight[4])
                    if flight[4]
                    else None,
                    longitude=flight[5],
                    latitude=flight[6],
                    baro_altitude=flight[7],
                    on_ground=flight[8],
                    velocity=flight[9],
                    true_track=flight[10],
                    vertical_rate=flight[11],
                    sensors=flight[12],
                    geo_altitude=flight[13],
                    squawk=flight[14],
                    spi=flight[15],
                    position_source=flight[16],
                )
            except Exception as e:
                logger.warning(
                    f"Skipping malformed flight row {flight[0] if flight else '?'}: {e}"
                )
                skipped += 1
                continue
            data = flight_obj.model_dump()
            try:
                await conn.execute(
                    """
                INSERT INTO flight_data (batch_id, icao24, timestamp, callsign, origin_country, time_position, last_contact, longitude, latitude, baro_altitude, on_ground, velocity, true_track, vertical_rate, sensors, geo_altitude, squawk, spi, position_source)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
                ON CONFLICT (icao24, timestamp) DO UPDATE SET
                    batch_id = EXCLUDED.batch_id,
                    callsign = EXCLUDED.callsign,
                    origin_country = EXCLUDED.origin_country,
                    time_position = EXCLUDED.time_position,
                    last_contact = EXCLUDED.last_contact,
                    longitude = EXCLUDED.longitude,
                    latitude = EXCLUDED.latitude,
                    baro_altitude = EXCLUDED.baro_altitude,
                    on_ground = EXCLUDED.on_ground,
                    velocity = EXCLUDED.velocity,
                    true_track = EXCLUDED.true_track,
                    vertical_rate = EXCLUDED.vertical_rate,
                    sensors = EXCLUDED.sensors,
                    geo_altitude = EXCLUDED.geo_altitude,
                    squawk = EXCLUDED.squawk,
                    spi = EXCLUDED.spi,
                    position_source = EXCLUDED.position_source
            """,
                    batch_id,
                    data["icao24"],
                    data["timestamp"],
                    data["callsign"],
                    data["origin_country"],
                    data["time_position"],
                    data["last_contact"],
                    data["longitude"],
                    data["latitude"],
                    data["baro_altitude"],
                    data["on_ground"],
                    data["velocity"],
                    data["true_track"],
                    data["vertical_rate"],
                    data["sensors"],
                    data["geo_altitude"],
                    data["squawk"],
                    data["spi"],
                    data["position_source"],
                )
            except Exception as e:
                logger.warning(f"DB insert failed for {data.get('icao24', '?')}: {e}")
                skipped += 1
        if skipped:
            logger.warning(
                f"Batch {batch_id}: skipped {skipped}/{len(flight_data)} rows due to errors."
            )
        return True
    except Exception as e:
        logger.error(f"Fatal error saving batch {batch_id}: {e}")
        return False
    finally:
        await conn.close()


async def create_download_batch_entry() -> int:
    conn = await asyncpg.connect(**db_connection_params)
    try:
        result = await conn.fetchrow(
            """
            INSERT INTO download_batch (status, details)
            VALUES ($1, $2)
            RETURNING batch_id
        """,
            "in_progress",
            "Batch started",
        )
        return result["batch_id"]
    finally:
        await conn.close()


def main_loop():
    """Main loop to continuously fetch flight data and update the database."""
    update_interval = 10  # seconds
    token_creds = TokenInitialization(TOKEN_CREDENTIALS_FILE)
    tokens = TokenManager(
        token_url=TOKEN_URL,
        # credentials_file=os.getenv("TOKEN_CREDENTIALS_FILE")
        credentials=token_creds,
    )

    while True:
        # Get the latest flight data from the OpenSky Network API asynchronously

        flight_data = asyncio.run(get_flight_data(tokens.get_token()))

        # Create a new download batch entry
        batch_id = asyncio.run(create_download_batch_entry())

        # Process and store flight data in the database
        # This is where you would implement the logic to insert or update the flight data in your database
        logger.info(f"Retrieved {len(flight_data)} flights at {datetime.now()}")

        # save flight data to database asynchronously
        async def update_batch(bid: int, count: int, status: str, detail: str) -> None:
            conn = await asyncpg.connect(**db_connection_params)
            try:
                await conn.execute(
                    """
                        UPDATE download_batch
                        SET status = $1, details = $2
                        WHERE batch_id = $3
                    """,
                    status,
                    detail,
                    bid,
                )
            finally:
                await conn.close()

        try:
            insert_ok = asyncio.run(save_flight_data_to_db(flight_data, batch_id))
            if insert_ok:
                asyncio.run(
                    update_batch(
                        batch_id,
                        len(flight_data),
                        "completed",
                        f"Batch completed with {len(flight_data)} flights",
                    )
                )
            else:
                asyncio.run(update_batch(batch_id, 0, "failed", "Save returned False"))
                logger.error(f"Failed to save flight data for batch {batch_id}.")
        except Exception as e:
            logger.error(f"Unhandled error in poll cycle (batch {batch_id}): {e}")
            try:
                asyncio.run(update_batch(batch_id, 0, "failed", str(e)))
            except Exception:
                pass  # don't let batch-status update failure hide the original error

        time.sleep(update_interval)


if __name__ == "__main__":
    # Load API credentials from opensky-credentials.json
    # with open("opensky-credentials.json", "r") as f:
    #    credentials = json.load(f)
    # bearer_token = credentials.get("bearer_token")

    # Create tables if they don't exist
    # async def create_tables():
    #    conn = await asyncpg.connect(**db_connection_params)
    #    for table_sql in list_of_table_sqls:
    #        await conn.execute(table_sql)
    #    await conn.close()

    # asyncio.run(create_tables())
    # Start the main loop to get flight data and update the database
    main_loop()
