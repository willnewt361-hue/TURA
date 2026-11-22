# TURA

TURA is an offline-first bus booking and operations demo built with FastAPI, SQLite, WebSockets, HTML, CSS, and vanilla JavaScript.

## Run locally

From this project directory, install Python requirements and start the app:

```powershell
python -m pip install -r requirements.txt
python main.py
```

Open <http://127.0.0.1:8000/> for the demo landing page. The API-backed application is at <http://127.0.0.1:8000/app/>. Do not start Python from inside the `app` directory; run the root launcher from this project directory so the `app` package resolves correctly.

## Physical and software requirements

### Development

- A Windows, macOS, or Linux computer with a modern 64-bit CPU, at least 8 GB RAM, and about 2 GB of free disk space for Python and dependencies.
- Python 3.13 and `pip`. The frontend is plain HTML, CSS, and JavaScript; Node.js is not required to run it.
- A current Chrome, Edge, Firefox, or Safari browser. For install checks, use an Android phone with Chrome or an iPhone/iPad with Safari. No special hardware is needed.
- Internet access to install dependencies and use live server features. Booking, seat availability, sign-in, and live updates need a reachable server.

### Hosting and real-device PWA installation

- A public HTTPS URL and a host that can run the Python ASGI app. HTTPS (or localhost during development) is required for service workers and PWA installation.
- Set independent, strong `SECRET_KEY` and `TICKET_HMAC_SECRET` values, `TURA_ENV=production`, `SESSION_COOKIE_SECURE=true`, and appropriate `DEMO_MODE` / `DEMO_INSTANCE` values in the host's secret environment. Never publish `.env` or local database files.
- The current SQLite deployment is configured for one worker and persistent disk. Keep one worker with this setup; in-memory WebSocket state is not shared across multiple workers. Before increasing traffic or workers, move persistence and shared real-time state to production services and validate backup/restore.
- The app's payment and vehicle-location workflows are demos; connect and verify real payment, dispatch, monitoring, privacy, and recovery services before accepting passengers or money.

## Frontend pages and brand assets

The root page is a static HTML/CSS/JavaScript landing page. Its route search loads published origins, destinations, and configured routes from the API, then passes the selected route into `/app/` before sign-in. `/pages/` contains separate visual journey previews; neither those previews nor the reference images at `/screens/<filename>` are live bookings. `/app/` is the connected, backend-backed application. The frontends use `frontend/assets/logo.svg` as the canonical TURA logo.

The service worker caches the `/app/` shell and its assets on the first online visit. It checks for a newer app shell on later visits, when the app returns to the foreground, and hourly while open; when an update takes control, the app offers a **Refresh app** action so users can load it without interrupting their current screen. Increment the cache version in `frontend/sw.js` when preparing a shell release. Offline navigation falls back to the connected app shell. Open **My Tickets** while online to save each ticket and QR image on that device; the read-only Journey Pack can then be opened offline. Ticket details and QR images can be stale and are not proof that a ticket is unused or unrevoked. Seat availability, payments, ticket validation, driver actions, and live tracking still require a connection.

Use the installation card on the splash screen or under **More**. Supported Android and desktop browsers offer **Install TURA**; otherwise, choose **Show install steps** for browser-specific guidance. On iPhone/iPad, open TURA in Safari and use **Share → Add to Home Screen**. An HTTPS deployment is required for friends to install from their own devices; localhost is only installable on the device running the local server.

The public demo service cannot create or download database backups. Live-service backups remain available to authorized operators and admins.

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

## NEXUS local team room

Run TURA on each teammate's computer with `python main.py`, then open `http://127.0.0.1:8000/nexus/` on that device. NEXUS is a separate local-first workspace: messages are AES-GCM encrypted in that browser's IndexedDB, task cards are stored locally, and verified peers exchange messages/tasks directly over WebRTC. No NEXUS message or task is written to TURA's SQLite database. The page shows the required HTML/CSS/JavaScript/Python-only stack banner.

For a direct connection, both people open **Connect device**, accept the network-address notice, privately exchange the invitation and answer codes, then compare the same safety code out-of-band and select **I verified**. Chat sync starts only after both people confirm. The connection uses Google's public STUN service to help peers cross NAT; STUN receives network metadata, including the public IP. Chat/task content goes peer-to-peer over the browser's encrypted WebRTC data channel. Some carrier, office, and symmetric-NAT networks will not connect without a TURN relay. If that happens, a relay must be hosted; without hosting, there is no reliable fallback. Both devices must be online at the same time to exchange live updates. Offline messages remain local and sync when a verified peer reconnects.

The local passphrase protects messages at rest in one browser only; it is not a shared account or a recovery mechanism. Keep it safe. Message bodies expire after 30 days and are purged at startup, when the page regains focus, and hourly while it is open; browser code cannot run cleanup while the app is fully closed. A teammate needs the project files and a local Python server to install the PWA on their own device. Use HTTPS if you later publish it.

The NEXUS screen includes four non-overlapping TURA workstreams with editable assignees/statuses. See [TEAM_TASKS.md](./TEAM_TASKS.md) for file ownership, shared-contract rules, and acceptance checks. This room is for the small team only; it does not provide production accounts, global discovery, a hosted message archive, file transfer, or sandboxed code execution.
