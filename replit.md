# GIT Civic

GIT Civic helps residents find public meetings and keep a private, evidence-labeled record of participation.

## Run and operate

- Start `artifacts/git-civic: web` for the original website at `/`. Its managed `PORT` is passed to the unchanged Flask app.
- Python 3.13 dependencies: `bash artifacts/git-civic/install-deps.sh`; lockfile is in `artifacts/git-civic/uv.lock`.
- Tests: `cd artifacts/git-civic && python3 -m unittest discover -s tests`.
- SQLite data: `artifacts/git-civic/civic.db`, or override with `CIVIC_DB_PATH`. Do not migrate it to the scaffold PostgreSQL service.
- `artifacts/api-server` is unused scaffold code mounted at `/__scaffold-api`, leaving `/api` to Flask.
- The root website is deliberately Flask + static HTML/CSS/JS. Do not replace it with the generated React scaffold when adding a slides artifact.

## Product and sources

The original site, services, and data are in `artifacts/git-civic/`. Read its `README.md` for source-labeling, Legistar fallback, demo events, AI brief limitations, and privacy details. A deck can be created separately with its own preview path.