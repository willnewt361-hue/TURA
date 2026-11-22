# TURA team workstreams

The NEXUS task board is seeded with these four independent assignments. Assign one owner per workstream and use separate branches. Keep the existing API and database contracts stable while work is in parallel.

## Shared working rules

- Stack for new work: HTML, CSS, vanilla JavaScript, and Python. Keep the existing FastAPI/SQLAlchemy structure; do not add a second frontend framework.
- Each owner changes only the files listed for their task and adds tests in the task-specific test file.
- Do not edit `app/db/models.py`, `app/main.py`, `app/api/deps.py`, or `tests/test_core.py` independently. Send shared schema, auth, routing, or contract changes to Newt for integration.
- Preserve existing JSON shapes, CSRF requirements, role checks, idempotency keys, and WebSocket event names unless the integration owner approves a versioned change.
- Before merge: run the task-specific tests, then the full `python -m pytest` regression suite. Record the command and result in the pull request.
- Use mock payments only. Do not put real passenger data, payment credentials, or network secrets into test fixtures.

## 1. Booking and seat consistency

**Owner:** Member 1 — backend booking developer  
**Owns:** `app/api/trips.py`, `app/api/bookings.py`, `app/services/booking_service.py`, new `tests/test_booking.py`

**Deliverable:** route search, server-authoritative seat availability/locks, booking creation/cancellation, expiry cleanup, and idempotent retry behavior.

**Acceptance checks:**

- Two customers cannot book the same seat.
- Expired locks are released and live `seat.released` updates are emitted once.
- Repeating an operation with the same idempotency key does not duplicate a booking.
- Invalid trip/seat combinations return the existing conflict/validation response.
- `python -m pytest tests/test_booking.py` passes.

## 2. Payments and ticket integrity

**Owner:** Member 2 — payments/tickets developer  
**Owns:** `app/api/payments.py`, `app/api/tickets.py`, `app/services/payment_service.py`, `app/services/ticket_service.py`, `app/security/signing.py`, new `tests/test_tickets.py`

**Deliverable:** mock payment adapter, booking settlement, signed ticket issue/revocation/expiry, QR payload validation, and audit events. Use the existing booking contract; coordinate any contract change with Member 1 and Newt.

**Acceptance checks:**

- A payment retry is idempotent and a failed mock charge releases its pending seat.
- A valid signed ticket validates; tampered, expired, revoked, or wrong-trip tickets are rejected.
- No secret is included in QR data, browser code, or logs.
- `python -m pytest tests/test_tickets.py` passes.

## 3. Operations and live trip events

**Owner:** Member 3 — operations/realtime developer  
**Owns:** `app/api/operations.py`, `app/api/luggage.py`, `app/api/sos.py`, `app/services/tracking_service.py`, `app/services/luggage_service.py`, `app/services/sos_service.py`, `app/realtime/`, new `tests/test_operations.py`

**Deliverable:** assigned-driver/operator actions, trip-position/status events, luggage custody changes, and clearly labelled local/demo SOS workflow.

**Acceptance checks:**

- Unassigned drivers cannot read or change another trip.
- Authorised state changes broadcast only to authorised rooms and do not duplicate events.
- Luggage status follows its allowed state transitions.
- SOS is labelled `Demo/Local alert`; it never claims real emergency dispatch.
- `python -m pytest tests/test_operations.py` passes.

## 4. PWA, offline flow, and integration QA

**Owner:** Member 4 — frontend/integration QA  
**Owns:** `frontend/index.html`, `frontend/js/`, `frontend/css/`, `frontend/sw.js`, new `tests/test_frontend.py`

**Deliverable:** responsive passenger/operator/driver experience, explicit online/offline/sync state, safe cached journey data, and focused browser/API regression tests. Do not change backend feature modules; report missing API behavior to the relevant owner.

**Acceptance checks:**

- The app shell opens after install while offline; stale ticket data is clearly read-only.
- No unsafe queued booking/payment action is replayed as if it succeeded.
- Navigation and the critical search → seat → mock payment → ticket journey work at mobile and desktop widths.
- `python -m pytest tests/test_frontend.py` passes, followed by the full regression suite.

## Integration order

Keep the current routes, models, and response schemas as the frozen interface. Members 1–3 can implement and test in parallel against those interfaces. Member 4 tests/integrates without editing their modules. Newt reviews shared changes, merges one workstream at a time, and runs the full regression suite before the team marks a task complete.
