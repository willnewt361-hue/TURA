# TURA

TURA is an offline-first bus booking and operations demo built with FastAPI, SQLite, WebSockets, HTML, CSS, and vanilla JavaScript.

## Run locally

From this project directory, install Python requirements and start the app:

```powershell
python -m pip install -r requirements.txt
python main.py
```

Open <http://127.0.0.1:8000/> for the demo landing page. The API-backed application is at <http://127.0.0.1:8000/app/>. Do not start Python from inside the `app` directory; run the root launcher from this project directory so the `app` package resolves correctly.

## Frontend pages and brand assets

The root page serves `frontend/pages/index.html`, which links the ordered walkthrough in `frontend/pages/`. The supplied-reference gallery at `/screens/` is a visual prototype; `/app/` is the connected, backend-backed application. Both frontend experiences use `frontend/assets/logo.svg` as the canonical TURA logo.

## Google Maps route map (optional)

Set `GOOGLE_MAPS_API_KEY` in the local `.env` file (copy `.env.example`) or in the Render service environment to enable the route map on `/pages/map-interface.html`, the tracking preview, and connected-app tracking. The map uses Google Maps JavaScript API and its current Routes library, not the legacy Directions service. In local development, the map config endpoint re-reads this single setting when the `.env` file changes, so save `.env` and press **Reload map** (or refresh the page). Other application settings still need a server restart. Render environment changes require a service redeploy/restart before refreshing the map. Enable the Google Maps JavaScript API and Routes API for the key, and ensure billing is enabled if Google requires it. For Google Cloud **Website restrictions**, allow both `http://localhost:8000/*` and `http://127.0.0.1:8000/*` when using those local addresses, plus `https://<your-render-host>/*` after deployment. Restrict the key to the Maps JavaScript API and Routes API. The browser must receive this key to load Google Maps, so it is **not a secret**; do not use a server-only credential as this browser key. Leave the setting empty to run the rest of TURA without Google Maps; map screens display a clear setup message.

## Render start command

Use the repository root as Render's **Root Directory** (leave it blank when this repository itself is the project root). The Blueprint start command is:

```text
python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1
```

For a service configured manually to run `python main.py`, the root-level launcher also binds to `0.0.0.0` when Render provides `PORT`. Do not set the Root Directory to `app`; `app` is the Python package, not the project root. Keep one worker while the service uses SQLite and in-memory WebSocket state.

## V1 boundaries

Payments are mocked, the sample ticket/gallery QR is not valid for travel, and trip tracking is illustrative. Do not use the public demo with real passenger data.
