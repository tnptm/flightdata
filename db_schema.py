import psycopg
import csv
import re
import os
import sys

from psycopg import sql
from typing import LiteralString
from dotenv import load_dotenv

load_dotenv()
db_connection_params = {
    k: v for k, v in {
        "dbname": os.getenv("DBASE"),
        "user": os.getenv("DBUSER"),
        "password": os.getenv("DBPASS"),
        "host": os.getenv("DBHOST"),
        "port": int(os.getenv("DBPORT", 5432)) if os.getenv("DBPORT") else None,
    }.items() if v is not None
}



# Datasamble to create sql for creating tables
# planes from https://opensky-network.org/datasets/#metadata/: 
# 'icao24','timestamp','acars','adsb','built','categoryDescription','country','engines','firstFlightDate','firstSeen','icaoAircraftClass','lineNumber','manufacturerIcao','manufacturerName','model','modes','nextReg','notes','operator','operatorCallsign','operatorIata','operatorIcao','owner','prevReg','regUntil','registered','registration','selCal','serialNumber','status','typecode','vdl'
# '000000','2017-10-19 18:30:18',0,0,,'',,'',,,'','','','',unknow,0,'','','','','','','','',,,'','','','','',0
planes_sql: LiteralString = """CREATE TABLE IF NOT EXISTS planes (
    icao24 TEXT PRIMARY KEY,
    timestamp TIMESTAMPTZ,
    acars INTEGER,
    adsb INTEGER,
    built INTEGER,
    categoryDescription TEXT,
    country TEXT,
    engines INTEGER,
    firstFlightDate DATE,
    firstSeen TIMESTAMPTZ,
    icaoAircraftClass TEXT,
    lineNumber TEXT,
    manufacturerIcao TEXT,
    manufacturerName TEXT,
    model TEXT,
    modes TEXT,
    nextReg TEXT,
    notes TEXT,
    operator TEXT,
    operatorCallsign TEXT,
    operatorIata TEXT,
    operatorIcao TEXT,
    owner TEXT,
    prevReg TEXT,
    regUntil TEXT,
    registered TEXT,
    registration TEXT,
    selCal TEXT,
    serialNumber TEXT,
    status TEXT,
    typecode TEXT,
    vdl INTEGER
);
"""


download_batch_sql: LiteralString = """CREATE TABLE IF NOT EXISTS download_batch (
    batch_id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    status TEXT,
    details TEXT
);
"""

# flight data from https://opensky-network.org/api/states/all
flight_data_sql: LiteralString = """CREATE TABLE IF NOT EXISTS flight_data (
    batch_id INTEGER REFERENCES download_batch(batch_id),
    icao24 TEXT,
    timestamp TIMESTAMPTZ,
    callsign TEXT,
    origin_country TEXT,
    time_position TIMESTAMPTZ,
    last_contact TIMESTAMPTZ,
    longitude DOUBLE PRECISION,
    latitude DOUBLE PRECISION,
    baro_altitude DOUBLE PRECISION,
    on_ground BOOLEAN,
    velocity DOUBLE PRECISION,
    true_track DOUBLE PRECISION,
    vertical_rate DOUBLE PRECISION,
    sensors TEXT,
    geo_altitude DOUBLE PRECISION,
    squawk TEXT,
    spi BOOLEAN,
    position_source INTEGER,
    PRIMARY KEY (icao24, timestamp)
);
"""


users_sql: LiteralString = """CREATE TABLE IF NOT EXISTS users (
    user_id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

refresh_tokens_sql: LiteralString = """CREATE TABLE IF NOT EXISTS refresh_tokens (
    token_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked BOOLEAN NOT NULL DEFAULT FALSE
);
"""

#planes_table_sql = sql.SQL(planes_sql)

list_of_table_sqls = [planes_sql, download_batch_sql, flight_data_sql, users_sql, refresh_tokens_sql]


def parse_table_name_from_sql(table_sql: str) -> LiteralString|None:
    """Extracts table name from a CREATE TABLE SQL statement."""
    # This is a simple implementation and may not cover all edge cases.
    tokens = table_sql.split()
    if "TABLE" in tokens and "IF" not in tokens:
        table_index = tokens.index("TABLE") + 1
        if table_index < len(tokens):
            return tokens[table_index]  # type: ignore
    elif "TABLE" in tokens and "IF" in tokens:
        table_index = tokens.index("TABLE") + 4  # Skip "IF NOT EXISTS"
        if table_index < len(tokens):
            return tokens[table_index]  # type: ignore
    return None

def create_tables():
    with psycopg.connect(**db_connection_params) as conn:
        for table_sql in list_of_table_sqls:
            with conn.cursor() as cur:
                table_name = parse_table_name_from_sql(table_sql)
                if table_name is None:
                    print("Could not parse table name from SQL. Skipping.")
                    continue
                print(f"Creating table name: {table_name}")
                cur.execute(sql.SQL(table_sql))
                conn.commit()
                print(f"Table {table_name} created successfully.")

def read_planes_from_csv(csv_file_path: str) -> list[dict]:
    """Read CSV plane data (single-quote delimited) and return as list of dicts."""
    int_fields = {"acars", "adsb", "built", "engines", "vdl"}
    data: list[dict] = []
    print(f"Reading plane data from {csv_file_path}...")
    with open(csv_file_path, newline="") as f:
        reader = csv.DictReader(f, quotechar="'")
        for row in reader:
            cleaned: dict = {}
            for key, val in row.items():
                if key is None:
                    continue
                v = val.strip() if val else ""
                if not v:
                    cleaned[key] = None
                elif key in int_fields:
                    try:
                        cleaned[key] = int(v)
                    except ValueError:
                        cleaned[key] = None
                else:
                    cleaned[key] = v
            data.append(cleaned)
    print(f"Read {len(data)} rows from CSV.")
    return data

def upload_planes_data(data: list[dict]):
    """read csv plane data as described in planes_sql and insert into planes table"""
    #data: list[dict] = []


    with psycopg.connect(**db_connection_params) as conn:
        with conn.cursor() as cur:
            for row in data:
                try:
                    cur.execute("""
                        INSERT INTO planes (icao24, timestamp, acars, adsb, built, categoryDescription, country, engines, firstFlightDate, firstSeen, icaoAircraftClass, lineNumber,
                        manufacturerIcao, manufacturerName, model, modes, nextReg, notes, operator, operatorCallsign, operatorIata, operatorIcao, owner, prevReg, regUntil,
                        registered, registration, selCal, serialNumber, status, typecode, vdl)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (icao24) DO NOTHING
                    """, (row.get("icao24"), row.get("timestamp"), row.get("acars"), row.get("adsb"), row.get("built"), row.get("categoryDescription"), row.get("country"), row.get("engines"), row.get("firstFlightDate"), row.get("firstSeen"), row.get("icaoAircraftClass"), row.get("lineNumber"),
                        row.get("manufacturerIcao"), row.get("manufacturerName"), row.get("model"), row.get("modes"), row.get("nextReg"), row.get("notes"), row.get("operator"),
                        row.get("operatorCallsign"), row.get("operatorIata"), row.get("operatorIcao"), row.get("owner"), row.get("prevReg"), row.get("regUntil"),
                        row.get("registered"), row.get("registration"), row.get("selCal"), row.get("serialNumber"), row.get("status"), row.get("typecode"),
                        row.get("vdl")))
                except Exception as e:
                    print(f"Error inserting row into database: {e}")
                    continue
            conn.commit()
            print(f"Uploaded {len(data)} rows to planes table successfully.")

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--upload-planes" and re.match(r"^[\w,\s-]+\.csv$", sys.argv[2]):
        print("Uploading planes data from CSV file...")
        try:
            data = read_planes_from_csv(sys.argv[2])
        except Exception as e:
            print(f"Error reading CSV file: {e}")
            sys.exit(1)
        if not data:
            print("No data to upload.")
            sys.exit(1)
        upload_planes_data(data)
        # Here you would implement the logic to read from the CSV file and insert into the planes table
        # This is left as an exercise for the reader, as it may involve additional libraries like pandas or csv
    else:
        create_tables()