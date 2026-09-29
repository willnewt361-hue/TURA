# TURA

TURA is an offline-first bus booking and operations demo built with FastAPI, SQLite, WebSockets, HTML, CSS, and vanilla JavaScript.

## Run locally

From this project directory, install Python requirements and start the app:

```powershell
python -m pip install -r requirements.txt
python main.py
```

Open <http://127.0.0.1:8000/> for the demo landing page. The API-backed application is at <http://127.0.0.1:8000/app/>. Do not start Python from inside the `app` directory; run the root launcher from this project directory so the `app` package resolves correctly.

## Render start command

Use the repository root as Render's **Root Directory** (leave it blank when this repository itself is the project root). The Blueprint start command is:

```text
python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1
```

For a service configured manually to run `python main.py`, the root-level launcher also binds to `0.0.0.0` when Render provides `PORT`. Do not set the Root Directory to `app`; `app` is the Python package, not the project root. Keep one worker while the service uses SQLite and in-memory WebSocket state.

## V1 boundaries

Payments are mocked, the sample ticket/gallery QR is not valid for travel, and trip tracking is illustrative. Do not use the public demo with real passenger data.
