# Test report

Only commands that were actually executed are listed, with their real results. Environment: Windows 11 host, Docker Desktop
(all tooling in containers), dates 2026-10-08 / 2026-10-09.

## Summary

| Suite | Command | Result |
|---|---|---|
| Backend unit + integration (pytest) | `docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm --no-deps api python -m pytest -p no:warnings tests` | **98 passed** in 23.3 s |
| Same suite inside the production API image | `docker compose -p plasticloop-verify exec -T api python -m pytest -q -p no:warnings` | **98 passed** |
| Frontend unit (vitest) | `npx vitest run` (web-dev container) | **12 passed** (2 files) |
| Type check | `npx tsc --noEmit` | no errors |
| Lint | `npx eslint src tests` | no errors, no warnings |
| Translations | `node scripts/check-i18n.mjs` | OK — 1 236 keys × 3 locales (EN/HI/TE), 848 keys referenced, placeholders match |
| Production web build | `docker compose build web` (`next build`, standalone) | success, all routes compiled |
| Clean stack from scratch | `docker compose -p plasticloop-verify up --build -d` + `seed_demo` | db, mosquitto, api, web healthy; worker running and connected to MQTT; seed created 3 villages, 40 points, 674 collections, 4 devices / 186 readings, 2 routes, 114 intakes, 111 sortings, 3 transfers, 1 outcome, 1 sale, 13 expenses |
| End-to-end (Playwright, Chromium) against the production build | `sh infra/scripts/e2e.sh` (stack on port 3100) | **7 passed** in 56 s |
| ESP32 firmware build | `arduino-cli compile --fqbn esp32:esp32:esp32 firmware/esp32/plasticloop_node` (core 3.0.0) | success — 1 121 881 B flash (85 %), 46 004 B RAM (14 %) |
| Backup / restore round trip | `sh infra/scripts/backup.sh` → delete rows → `restore.sh` | complaints 8 → 0 → **8 restored**; API healthy after restore |
| Guided demo (12 steps) against the dev database | `POST /api/v1/demo/walkthrough/1..12` as evaluator | all 12 succeeded |

## Backend tests by area (98)

| File | Covers |
|---|---|
| `test_auth.py` (12) | Argon2id hashing, httpOnly refresh cookie, indistinguishable invalid credentials, CSRF header on refresh, **refresh rotation + reuse revokes the family**, logout, expired / tampered tokens, citizen registration (consent, strong password), invitation ceilings, login rate limit |
| `test_permissions.py` (8) | unauthenticated rejection, scoped listings, **cross-tenant reads/writes return 404**, collector cannot administer, evaluator read-only, user directory scoped, household sees only own records, PII redacted for evaluator |
| `test_collections_sync.py` (18, incl. parametrised validation cases) | unique point codes/QR, PostGIS nearby search, idempotent online create, **offline retry creates no duplicates**, changed payload with same id → conflict (original kept), invalid / future events rejected, one bad event does not roll back the others, out-of-scope collector rejected, unassigned collector flagged, offline task bundle |
| `test_db_constraints.py` (4) | positive weights, unique QR codes, **append-only audit log**, enum values enforced by the database |
| `test_devices.py` (14) | registration (key once, hashes only), HTTPS ingestion idempotency, wrong key / mismatched device, key rotation, quality flags, fill/battery/offline alerts, clock skew, tenant isolation, scale reading → `device_measured`, MQTT worker handler, calibration results, commands, simulator restrictions|
| `test_routing.py` (17) | 13 OR-Tools fixtures: empty, no vehicles, single vehicle, capacity split, insufficient capacity (priority), oversize stop, unreachable stop, time windows, max shift, emergency stop, unload at facility, baseline; plus planner preview/save, driver workflow, tenant scoping|
| `test_inventory.py` (12) | intake, sorting with kept difference, outputs > input rejected, **over-draw prevention**, stale version, split/merge, incompatible merge, **MLP verification needs evidence**, **ledger append-only**, batch = ledger sum, tenant/role isolation|
| `test_vision.py` (7) | metrics (confusion, P/R/F1), reproducible stratified split, heuristic output, trained mode never silently falls back, suggestion vs review stored separately, permissions, non-image rejected|
| `test_recovery.py` (5) | full transfer lifecycle with discrepancy and returned material, **evidence required for recycling claims**, processor cannot review own evidence, self-reported never counted, marketplace offer → sale → stock out, payments/overpayment, expenses estimates, CSV + PDF reports|
| `test_demo_walkthrough.py` (1) | seeds the full demo dataset inside the test transaction and runs all 12 guided-demo steps|

## End-to-end tests (7, Playwright 1.64, production build with service worker)

1. **Offline collector** (390 px): cache stops online → go offline → record a collection → reload offline (service worker) →
   record still queued → open the offline queue page offline → back online → sync → sync again → API shows **exactly one**
   event with that weight, flagged `offline_captured`.
2. Every one of the 8 demo roles signs in and lands on a working page.
3. API enforces roles (collector gets 403 on users/finance; evaluator can read analytics but cannot create vehicles).
4–6. No horizontal overflow at **360, 768 and 1440 px** on the public page and 7 app pages.
7. **axe-core**: 0 critical and 0 serious violations on login, dashboard and collection points.

## Defects found by these tests and fixed

* Offline queue page failed to load offline (its JS chunk was never cached) → the service worker now caches the static
  assets referenced by every cached page.
* axe: dark-sidebar text contrast 3.75:1, demo-password and shortcut-hint contrast 4.34:1, 16 unnamed progress bars → fixed
  (sidebar muted token, foreground colour, default accessible names).
* Transfer acceptance failed when the displayed (rounded) weight was typed → exact weights shown and pre-filled.
* SSE request kept a database transaction open for the life of the stream (blocked a reset) → session released before
  streaming; Next.js gzip buffering of SSE → `Cache-Control: no-transform`.
* Repeated E2E runs within 5 minutes hit the login rate limiter (working as designed) → documented in `e2e.sh`.

## Manually verified (not automated)

* Simulator → Mosquitto → worker → database over real MQTT; wrong key refused; **cross-device publish dropped by the ACL**;
  `calibrate` command delivered to the device and its result stored.
* Server-sent events delivered through the Next.js proxy to the browser.
* Browser checks of collector, devices, planner (map), facility, inventory sort, processing transfer, analytics,
  classification pages.
* First super-admin creation snippet from `DEPLOYMENT.md` (login succeeded with role `super_admin`).

## Not tested (no claims made)

* ESP32 firmware on physical hardware (compiled only); real load-cell accuracy or calibration drift.
* Any trained vision model — none is shipped; no accuracy figure exists.
* OSRM road distances (no OSRM server was run); route savings were only measured on haversine estimates.
* TLS deployment (Caddy, MQTT 8883) and behaviour on a public VPS.
* Real Android/iOS devices, camera QR scanning on hardware, low-end phone performance, screen readers.
* Load or concurrency testing beyond the per-request row locking covered by tests.
* Hindi and Telugu translations by native speakers.
