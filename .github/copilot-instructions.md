# FlightData — Copilot Instructions

## Architecture

Three independent processes — do not merge them:

| Process | Entry point | Runtime |
|---|---|---|
| API server | `api.py` | FastAPI + asyncpg (async) |
| Flight poller | `flight_data_updater.py` | asyncio, runs separately |
| Frontend | `flightui/` | Next.js 16 / React 19 / TypeScript 5 |

Database access uses **asyncpg** in `api.py` (async pool on `app.state.pool`) and **psycopg 3** (sync) only in `db_schema.py`.

## Backend Conventions

- Python 3.14 — use modern type hints (`str | None`, not `Optional[str]`).
- `load_dotenv()` must be called **before** any import that reads env vars (top of `api.py` and `backend/auth.py`).
- Never reuse an asyncpg connection across separate `asyncio.run()` calls — wrap each batch of async operations in a single coroutine.
- Password hashing: use `bcrypt` directly (passlib removed — incompatible with bcrypt 4+). Passwords are SHA-256 pre-hashed before bcrypt to handle arbitrary length. See `backend/auth.py`.
- JWT: access tokens expire in 30 min (HS256). Refresh tokens are `secrets.token_urlsafe(48)`, stored as SHA-256 hex in `refresh_tokens` table.
- All endpoints (except `/auth/register` and `/auth/token`) require `Depends(get_current_user)`.
- Add `ON CONFLICT DO NOTHING` to bulk inserts in `db_schema.py`.

## Database

Tables: `planes`, `download_batch`, `flight_data`, `users`, `refresh_tokens`.  
See `db_schema.py` for full schema. `planes.icao24` is the primary key and should always be lowercased before lookup.

The `/flights` endpoint filters by the **latest completed** `download_batch` entry and a map bounding box (`$1`–`$4`).

## Frontend Conventions

- Leaflet map is SSR-disabled via `next/dynamic`. Always guard map init with `if (cancelled || mapRef.current) return` to handle React StrictMode double-mount.
- Clean up Leaflet by deleting `containerRef.current._leaflet_id` in the `useEffect` cleanup.
- Access token is stored **in memory only**. Refresh token goes in `localStorage` under key `"refresh_token"`.
- `API_BASE` comes from `process.env.NEXT_PUBLIC_API_URL` (set in `flightui/.env.local`).
- Plane metadata is fetched lazily on marker click via `api.plane(icao24, token)` — do not prefetch for all visible aircraft.
- The ✈ emoji points east by default — rotate icon by `(true_track - 90)deg` to align with heading.

## Key Files

- `backend/auth.py` — JWT + bcrypt utilities, `get_current_user` dependency
- `backend/users.py` — all auth and user management routes
- `flightui/app/lib/api.ts` — typed fetch client for all backend endpoints
- `flightui/app/lib/auth-context.tsx` — React auth context with proactive token refresh
- `flightui/app/components/FlightMap.tsx` — Leaflet map component

## Packages

Backend managed with **uv** (`uv add <package>`). Do not edit `pyproject.toml` manually for dependencies.  
Frontend managed with **npm**.

## Contributing

All changes require a pull request. See `CONTRIBUTING.md`.
