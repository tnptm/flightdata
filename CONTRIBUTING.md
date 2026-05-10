# Contributing to FlightData

Thank you for considering contributing! Here's how to get involved.

## Code of Conduct

Be respectful and constructive in all interactions.

## Getting Started

1. **Fork** the repository and create a branch from `master`:
   ```bash
   git checkout -b feat/your-feature-name
   ```
2. **Set up** the Python environment:
   ```bash
   uv sync
   cp .env.example .env  # fill in your database credentials
   python db_schema.py   # create tables
   ```
3. **Set up** the frontend:
   ```bash
   cd flightui
   npm install
   ```

## Development Workflow

### Backend (FastAPI)
```bash
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend (Next.js)
```bash
cd flightui && npm run dev
```

### Data updater
```bash
python flight_data_updater.py
```

### Upload aircraft database
```bash
python db_schema.py --upload-planes aircraft-database-complete-2025-08.csv
```

## Making Changes

- Keep commits small and focused on a single concern.
- Use [Conventional Commits](https://www.conventionalcommits.org/) style:
  - `feat:` — new feature
  - `fix:` — bug fix
  - `refactor:` — code restructure without behaviour change
  - `docs:` — documentation only
  - `chore:` — build/config/tooling changes
- Do **not** commit secrets, `.env` files, or the aircraft CSV (it is in `.gitignore`).

## Pull Requests

**All changes must go through a pull request — direct pushes to `master` are not allowed.**

1. Open a PR against `master` from your feature branch.
2. Describe **what** changed and **why**.
3. Make sure the backend starts without errors and the frontend builds (`npm run build`).
4. Every PR will be reviewed and merged by the maintainer (@tnptm). Do not merge your own PR.

## Reporting Bugs

Open a GitHub Issue and include:
- Steps to reproduce
- Expected vs. actual behaviour
- Relevant log output or error messages
- Python / Node.js versions (`python --version`, `node --version`)

## Project Structure

```
flightdata/
├── api.py                  # FastAPI app & endpoints
├── backend/
│   ├── auth.py             # JWT + password hashing
│   └── users.py            # Auth & user management router
├── db_schema.py            # Table creation & CSV import
├── flight_data_updater.py  # OpenSky poller (runs separately)
├── token_manager.py        # OpenSky OAuth2 token manager
├── pyproject.toml
└── flightui/               # Next.js frontend
    └── app/
        ├── lib/            # API client & auth context
        ├── components/     # FlightMap (Leaflet)
        ├── dashboard/      # Protected dashboard page
        └── (auth)/         # Login / register pages
```

## License

By contributing you agree that your changes will be licensed under the [MIT License](LICENSE).
