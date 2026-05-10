# FlightData — Full-Stack Live Flight Tracker

Real-time aircraft tracking app. A background poller fetches live position data from the [OpenSky Network](https://opensky-network.org/) API every 10 seconds and stores it in PostgreSQL. A FastAPI backend serves the data over a JWT-authenticated REST API. A Next.js frontend displays aircraft positions on an interactive Leaflet map, updating every 15 seconds.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI 0.136+, Python 3.14, asyncpg |
| Authentication | JWT (PyJWT 2.x, bcrypt 5.x) — access + refresh token rotation |
| Database | PostgreSQL (psycopg 3 for schema/import, asyncpg for API) |
| Data poller | `flight_data_updater.py` (httpx, loguru) |
| Frontend | Next.js 16, React 19, TypeScript 5, Tailwind CSS 4 |
| Map | Leaflet 1.9.4 (SSR-disabled, OpenStreetMap tiles) |

## Project Structure

```
flightdata/
├── api.py                   # FastAPI app — /flights and /planes/{icao24} endpoints
├── backend/
│   ├── auth.py              # JWT creation/validation, bcrypt password hashing
│   └── users.py             # Auth & user management router (/auth/*, /users/*)
├── db_schema.py             # Table creation + aircraft CSV importer
├── flight_data_updater.py   # Background OpenSky poller (runs independently)
├── token_manager.py         # OpenSky OAuth2 token manager
├── pyproject.toml
├── .env                     # Local secrets (not committed)
└── flightui/                # Next.js frontend
    └── app/
        ├── lib/             # api.ts (typed fetch client), auth-context.tsx
        ├── components/      # FlightMap.tsx (Leaflet map)
        ├── dashboard/       # Protected dashboard — live map + aircraft count
        └── (auth)/          # Login and register pages
```

## Prerequisites

- Python 3.14+ and [uv](https://github.com/astral-sh/uv)
- Node.js 20+
- PostgreSQL 14+
- OpenSky Network account (for the live data poller)

## Setup

### 1. Environment variables

Create a `.env` file in the project root:

```env
DBASE=flightdata
DBUSER=your_db_user
DBPASS=your_db_password
DBHOST=localhost
DBPORT=5432
SECRET_KEY=change-me-to-a-long-random-string
CORS_ORIGINS=http://localhost:3000
```

### 2. Python backend

```bash
uv sync
python db_schema.py          # create all tables
```

### 3. Import aircraft database (optional but recommended)

Download the metadata CSV from [OpenSky datasets](https://opensky-network.org/datasets/#metadata/) and import it:

```bash
python db_schema.py --upload-planes aircraft-database-complete-2025-08.csv
```

### 4. Frontend

```bash
cd flightui
npm install
cp .env.local.example .env.local   # set NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Running

Start each process in a separate terminal:

```bash
# 1. API server
uvicorn api:app --host 0.0.0.0 --port 8000

# 2. Live flight data poller
python flight_data_updater.py

# 3. Frontend dev server
cd flightui && npm run dev
```

Open [http://localhost:3000](http://localhost:3000), register an account, and log in to see the live map.

## API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/register` | — | Create account |
| `POST` | `/auth/token` | — | Login, returns access + refresh token |
| `POST` | `/auth/refresh` | — | Rotate refresh token |
| `POST` | `/auth/logout` | — | Revoke refresh token |
| `GET` | `/users/me` | JWT | Current user profile |
| `PUT` | `/users/me` | JWT | Update email / password |
| `GET` | `/users` | Admin JWT | List all users |
| `DELETE` | `/users/{id}` | Admin JWT | Delete user |
| `GET` | `/flights` | JWT | Latest aircraft positions in map bounding box |
| `GET` | `/planes/{icao24}` | JWT | Static aircraft metadata |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). All changes require a pull request.

## License

[MIT](LICENSE) © 2026 Toni Patama
