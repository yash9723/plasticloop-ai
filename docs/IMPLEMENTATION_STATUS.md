# Implementation status

Legend: ✅ done and verified · 🟡 done with a stated limit · ⬜ not started. "Verified" means exercised by an executed test or a
recorded manual run (see [TEST_REPORT.md](TEST_REPORT.md)).

_Last updated: 2026-10-09._

| Phase | Module | Status | Evidence / notes |
|---|---|---|---|
| A | Monorepo, Docker Compose (db, mosquitto, api, worker, web) with healthchecks | ✅ | Clean `docker compose up --build` from scratch: all services healthy |
| A | PostgreSQL/PostGIS schema (48 tables), Alembic migrations, append-only triggers, CHECK constraints, optimistic locking | ✅ | `test_db_constraints.py`; migrations run on every API start |
| A | Auth (Argon2id, short JWT, rotating refresh cookie with reuse detection, CSRF header, invitations, citizen registration, rate limits) | ✅ | `test_auth.py` |
| A | RBAC + tenant scoping (`AccessScope`, cross-tenant 404) | ✅ | `test_permissions.py`, E2E roles test |
| A | Frontend shell, UI kit, light/dark, i18n EN/HI/TE (1 236 keys × 3) | 🟡 | tsc/eslint/i18n clean; HI/TE need native-speaker review |
| B | Villages, households (PII minimisation, erasure), QR collection points (PostGIS), pickup requests, complaints | ✅ | `test_collections_sync.py`, `test_permissions.py` |
| B | Collections + idempotent offline sync + conflict resolution | ✅ | `test_collections_sync.py`, E2E offline test (exactly one server row) |
| B | Offline-first collector PWA (Dexie queue, backoff, service worker caching incl. page assets, icons, manifest) | 🟡 | vitest + E2E; foreground sync only (Background Sync not used) |
| C | Devices, keys, HTTPS + MQTT ingestion, quality flags, alerts, commands, calibration, SSE live updates, simulator (CLI + web) | ✅ | `test_devices.py` (14); real broker checks (wrong key refused, ACL drop, command round trip) |
| C | ESP32 firmware (HX711, HC-SR04, serial provisioning into NVS, MQTT/HTTPS, LWT, ring buffer, commands) | 🟡 | Compiles with arduino-cli (85 % flash); **not run on physical hardware** |
| D | OR-Tools routing, planner, route execution, vehicles; fixed-order baseline; labelled distance basis | 🟡 | `test_routing.py` (17); OSRM road distances not tested |
| D | MRF intake, sorting, split/merge, adjustments, MLP evidence review, append-only ledger, mass balance | ✅ | `test_inventory.py` (12) |
| E | Vision adapters (trained/heuristic/manual), review queue, evaluation + training scripts | 🟡 | `test_vision.py` (7); **no trained model or dataset shipped, no accuracy claimed** |
| E | Analytics + notifications | 🟡 | Browser + demo; notifications are in-app only |
| F | Processors, transfers, evidence-gated outcomes, marketplace, finance, CSV/PDF reports | ✅ | `test_recovery.py` (5) |
| G | 12-step guided demo, audit log, synthetic seed through real services | ✅ | `test_demo_walkthrough.py`; all 12 steps run against the dev DB |
| G | Responsive + accessibility | 🟡 | E2E: no overflow at 360/768/1440 px; axe 0 critical/serious on 3 pages; screen readers and real phones not tested |
| H | Tests: backend 98 (dev + production image), frontend unit 12, E2E 7 (production build) | ✅ | [TEST_REPORT.md](TEST_REPORT.md) |
| H | Docs: README, architecture, API reference (generated, 161 operations), ESP32, traceability, test report, demo script, deployment | ✅ | `docs/` |
| H | Backup / restore scripts | ✅ | Round trip tested locally (8 → 0 → 8 rows) |
| H | Public VPS deployment with TLS (Caddy, MQTT 8883) | 🟡 | Guide written; not executed against a public server |

## Not implemented (honest list)

* Trained packaging classifier and labelled dataset (pipeline exists; needs real photos).
* OSRM routing server (supported via `OSRM_URL`, not run in this project).
* SMS / WhatsApp / web-push notifications (in-app only).
* Background Sync API (the PWA syncs while open: on reconnect, on start, every 30 s and on demand).
* ESP32 bench test on hardware; native-speaker review of Hindi and Telugu.

## Build notes for this machine

* Everything runs in Docker (the workspace path exceeds Windows' path limit for native Python/Node modules).
* API dev: `docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm --no-deps api <cmd>`.
* Web dev: service `web-dev`. Turbopack does not see bind-mount changes on Windows — restart `web-dev` after frontend edits.
* Git Bash rewrites `/paths` in docker arguments: prefix commands with `MSYS_NO_PATHCONV=1` (the scripts do this).
* Regenerate the API reference: `docker compose exec -T api python -m app.scripts.api_reference > docs/API_REFERENCE.md`.

## Known deviations

* No `repositories/` layer: services use the SQLAlchemy session directly.
* Login rate limiting is in-process (per API instance); move to Redis before running several API replicas.
