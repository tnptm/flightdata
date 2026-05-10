import os
import httpx
from datetime import datetime, timedelta
from token_manager import TokenManager, TokenInitialization

# Lazy singleton — mirrors how flight_data_updater.py handles credentials.
# Initialized on first call so missing credentials fail at request time, not import time.
_tokens: TokenManager | None = None


def _get_tokens() -> TokenManager | None:
    """Return a shared TokenManager, or None if credentials file is not configured."""
    global _tokens
    if _tokens is not None:
        return _tokens
    credentials_file = os.getenv("TOKEN_CREDENTIALS_FILE", "token_credentials.json")
    token_url = os.getenv(
        "TOKEN_URL",
        "https://auth.opensky-network.org/auth/realms/opensky-network"
        "/protocol/openid-connect/token",
    )
    try:
        creds = TokenInitialization(credentials_file)
        _tokens = TokenManager(token_url=token_url, credentials=creds)
        return _tokens
    except (FileNotFoundError, KeyError):
        return None


def _opensky_headers() -> dict:
    """Return Authorization header using the shared TokenManager, or {} if unavailable."""
    tokens = _get_tokens()
    return tokens.headers() if tokens else {}


def _fmt(ts: int | None) -> str | None:
    return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%SZ") if ts else None


def get_flight_route(icao24: str) -> list[dict]:
    """
    1. Try /tracks/all?time=0 — returns live track for a currently-airborne aircraft.
       (The /flights/aircraft endpoint is batch-processed nightly and won't contain
       flights that are happening right now.)
    2. Fall back to /flights/aircraft for the last 2 days (historical completed flights).

    Requires OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET env vars for OAuth2.
    Returns a list of dicts with keys:
        is_live, callsign, departure_airport, arrival_airport, first_seen, last_seen
    """
    icao24 = icao24.lower().strip()
    headers = _opensky_headers()

    end_ts = int(datetime.utcnow().timestamp())
    begin_ts = int((datetime.utcnow() - timedelta(days=2)).timestamp())

    # Fetch live track and historical flights concurrently
    with httpx.Client(timeout=15) as client:
        track_r = client.get(
            "https://opensky-network.org/api/tracks/all",
            params={"icao24": icao24, "time": 0},
            headers=headers,
        )
        hist_r = client.get(
            "https://opensky-network.org/api/flights/aircraft",
            params={"icao24": icao24, "begin": begin_ts, "end": end_ts},
            headers=headers,
        )

    # Parse historical flights (404 = no data, not an error)
    historical: list[dict] = []
    if hist_r.status_code == 200:
        historical = hist_r.json() or []
    elif hist_r.status_code not in (404, 400):
        hist_r.raise_for_status()

    # Most recent historical flight — used to supplement live track with airport info
    last_hist = historical[-1] if historical else None

    # Live track takes priority when the aircraft is currently airborne
    if track_r.status_code == 200:
        data = track_r.json()
        if data and data.get("path"):
            return [{
                "is_live": True,
                "callsign": (data.get("callsign") or "").strip() or None,
                # Airport data isn't in the live track; pull from most recent historical leg
                "departure_airport": last_hist.get("estDepartureAirport") if last_hist else None,
                "arrival_airport": last_hist.get("estArrivalAirport") if last_hist else None,
                "first_seen": _fmt(data.get("startTime")),
                "last_seen": _fmt(data.get("endTime")),
            }]

    # No live track — return historical completed flights
    return [
        {
            "is_live": False,
            "callsign": (f.get("callsign") or "").strip() or None,
            "departure_airport": f.get("estDepartureAirport") or None,
            "arrival_airport": f.get("estArrivalAirport") or None,
            "first_seen": _fmt(f.get("firstSeen")),
            "last_seen": _fmt(f.get("lastSeen")),
        }
        for f in historical[-3:]  # most recent 3
    ]