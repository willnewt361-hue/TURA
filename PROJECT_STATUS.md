# TURA / NEXUS project status

## Current delivery

NEXUS is mounted at `/nexus/` in the existing FastAPI app and uses the requested HTML, CSS, vanilla JavaScript, and Python stack. It provides:

- A local passphrase vault; message bodies are encrypted with AES-GCM in each browser's IndexedDB.
- Manual WebRTC invite/answer exchange, a public-STUN disclosure, out-of-band safety-code comparison, and direct peer chat/task transfer.
- Per-device message history with 30-day expiry cleanup on startup, focus, and hourly while open.
- A four-workstream TURA task board with local persistence and peer updates.
- A scoped service-worker shell for offline opening and installable PWA metadata.
- Team ownership boundaries and acceptance criteria in [TEAM_TASKS.md](./TEAM_TASKS.md).

## Scope reconciliation

The attached NEXUS master directive specifies Next.js/TypeScript, Supabase, Vercel, hosted accounts/storage/realtime, and a production deployment. That stack conflicts with the earlier explicit requirement to use only HTML/CSS/JavaScript/Python and not host the app. This implementation preserves the earlier local-first constraints; it does not claim to satisfy the attached directive's production release criteria.

The attached directive's broader features remain unimplemented: invite-based accounts and owner/admin controls, hosted multi-channel messaging and multi-device E2E key management, secure file/project/version workflows, isolated code execution, AI integrations, network inventory/monitoring, collaborative diagramming, investigations, and knowledge base. The local task board and direct chat are not substitutes for those services. Reliable international access, accounts, central persistence, or TURN relaying require hosted infrastructure and a deliberate change to the no-hosting constraint.

## Verification state

The NEXUS static-route tests are present in `tests/test_nexus.py`, and existing regression tests remain in `tests/test_core.py`. **The test suite and JavaScript syntax check have not been executed in this session:** the local PowerShell runner is unavailable and the delegated command runner did not start. The local browser check also could not run because no TURA server was listening on localhost. Do not treat the new code as runtime-verified until these commands pass from the project root:

```powershell
python -m pytest tests/test_nexus.py -q
node --check frontend/nexus/app.js
python -m pytest
```

Browser verification is also outstanding: install/offline reopen, vault lock/unlock, message persistence/expiry, task persistence, and a two-browser peer invite → answer → matching safety code → chat/task exchange.

## Important boundaries

- There is no hosted chat database, account provider, global room discovery, or server-mediated message queue.
- Peers must exchange signaling codes privately and be online together. Public STUN can see network metadata; some networks require a hosted TURN relay and will not connect without one.
- A vault passphrase protects messages on one device; it is not a shared identity/account or a recovery key. Task metadata is not encrypted at rest.
- The browser cannot run expiry cleanup while completely closed.
- NEXUS does not upload project files, execute code, run AI review, generate network topology, scan networks, or provide hack/exploit recommendations.
- TURA's existing payment, booking, and tracking features retain their documented demo boundaries.
