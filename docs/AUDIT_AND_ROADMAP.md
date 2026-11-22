# TURA — Audit & Delivery Roadmap

_Last updated: 2026-11-22_

This document records what was audited, what is real vs. simulated, the security
findings, and the module-by-module plan used to finish the app.

## 1. Codebase inventory

| Path | What it is | Status |
|---|---|---|
| `TURA/TURA/` (nested, git repo) | **Active product**: FastAPI + SQLite + vanilla HTML/CSS/JS SPA + PWA | Source of truth |
| `TURA/app/` (outer copy) | Partial backend copy, no frontend | Stale — do not edit |
| `rebuild-tura-web-system/` | Next.js App Router + Drizzle/Postgres rebuild (passenger + staff/driver consoles) | Reference only |
| `redesign-tura-web-application (1)/` | Next.js public marketing/booking variant (search, trips, checkout, verify, legal) | Reference only |

**Decision:** keep the vanilla stack (FastAPI + HTML/CSS/JS). Port only the
Next.js ideas that add value; do not migrate the runtime.

## 2. Real vs. simulated features (be honest in the UI)

| Feature | Reality |
|---|---|
| Seat map & locking | Real, server-authoritative, 120 s locks |
| Booking & totals | Real |
| Payments | **Mock provider only.** No money moves. Live mode returns 503 |
| QR ticket | Real HMAC-signed token + QR PNG, server-side single-use validation |
| Live tracking | **Simulated corridor waypoints**, not GPS |
| SOS | **Internal ops alert only.** Never contacts police/emergency services |
| Settlements | Real arithmetic, `provider="mock"` |
| Offline | Cached tickets/itinerary only; booking/validation need network |
| i18n | English complete; Luganda draft |

## 3. Security findings

### Fixed in this pass (Module 1)

1. **Rate limiter collapsed all clients behind a reverse proxy** into one bucket
   (60 req/min total). Added `TRUST_PROXY` + per-route auth limits.
2. **No per-account login throttling** → online password guessing. Added
   failure window + lockout, plus constant-time dummy hash for unknown phones.
3. **JWT decode did not require `exp`/`sub`** and could 500 on a malformed
   subject. Hardened claims and error handling.
4. **`get_optional_user` accepted disabled accounts.** Now checks `status`.
5. **Operators could download the full SQLite database** (password hashes, PII).
   Backup create/download is now **admin-only**.
6. **SOS acknowledge crashed with 500** on a missing alert. Now 404.
7. **Ticket numbers used `COUNT()+1`** → collisions/races. Now derived from the
   inserted row id after flush.
8. **Passenger email was unvalidated.** Now format-checked server-side.
9. **Tracked SQLite databases in git** (`data/*.db` were committed before being
   ignored). Untracked; history still needs a rewrite/rotation (see §6).

### Remaining / accepted risks

- Double-booking race: SQLite serialises writes, but there is no unique
  `(trip_id, seat_id)` constraint. Mitigated by lock + conflict check.
- In-memory rate limiter and WebSocket rooms are single-process only.
- Google Maps browser key is public by design; restrict it by HTTP referrer.
- Demo login grants role access without a password when `DEMO_MODE=true`.
  Never expose a demo instance with real data.
- No password reset / email verification yet (Module 5).
- CSP allows `'unsafe-inline'` styles. Tighten when inline styles are removed.

## 4. Module plan (one at a time, each verified)

| # | Module | Deliverable | Verify |
|---|---|---|---|
| 0 | Baseline | Python 3.13 venv, `pytest` green | 10/10 tests |
| 1 | Security hardening | Findings 1–9 above | tests + manual probes |
| 2 | PWA & updates | Install prompt, icons, update check, offline shell | Lighthouse / manual |
| 3 | Public pages | Help, legal, requirements, robots, sitemap | open pages |
| 4 | Public ticket verify | `POST /api/tickets/verify` + `/pages/verify.html` | scan/verify flow |
| 5 | Account & guest booking | Password reset, guest reference lookup | flow tests |
| 6 | UI polish | Align SPA visuals with Next.js design tokens | screenshots |
| 7 | Release | Render deploy, backup/restore drill, runbook | checklist |

## 5. PWA install & update

- Manifest: `/manifest.webmanifest` (192/512 icons, maskable, shortcuts).
- Service worker: `/sw.js`, cache `tura-shell-v13`, network-first with cache
  fallback for the app shell.
- In-app: install card on splash/More; `beforeinstallprompt` captured;
  iOS "Add to Home Screen" instructions.
- Updates: `controllerchange` shows a "Refresh app" notice; the page also polls
  `registration.update()` every 30 minutes and on focus.

## 6. Release notes

- Rotate `SECRET_KEY`, `TICKET_HMAC_SECRET`, and any credentials that ever
  appeared in a committed database.
- `git rm --cached` the tracked DB files (done) and consider rewriting history
  before publishing the repository.
- Backups are admin-only and disabled in demo mode.
